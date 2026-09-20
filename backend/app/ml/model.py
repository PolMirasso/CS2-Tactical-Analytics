from __future__ import annotations

import warnings
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import lru_cache

import numpy as np

from app.ml.deepsets import DeepSets, _softmax
from app.ml.features import SITES, TIMINGS, TOKEN_DIM, _attr, round_context, round_tokens

# Below this many rounds (or < 2 distinct sites) we don't fit the net and serve
# the historical base rate instead — too little signal to learn anything.
MIN_ROUNDS = 20
HOLDOUT_FRAC = 0.2
_WEIGHT_DECAY = 1e-4
# Set pooling over the round's utility tokens: mean (baseline), sum (keeps cardinality) or attention (learned per-grenade weights)
_POOLING = "attention"
# How many landing points to draw inside each drawn box at inference. The model
# is point-trained, so the drawn box means "lands somewhere in this area" and the
# time window means "active across this span": we average the prediction over
# (position, time) sampled in them (wider box/window ⇒ broader, less peaked output).
# Past 64 the error stops dropping
_N_SAMPLES = 64


@lru_cache(maxsize=64)
def _low_discrepancy(d: int, n: int, seed: int) -> np.ndarray:
    """n points in [0,1)^d spread evenly by construction (scrambled Sobol),
    where n independent uniform draws would clump and leave holes"""
    from scipy.stats import qmc

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)  # n not a power of two
        points = qmc.Sobol(d=d, scramble=True, seed=seed).random(n)
    points.flags.writeable = False  # shared by every caller
    return points


def _sampled_utility_sets(utility, n: int, seed: int = 0) -> list[list[dict]]:
    """Perturbed copies of ``utility`` with each x/y placed inside its w×h box and
    its throw time inside its [time_from, time_to] window.

    Returns one set when nothing has an area or a time span to sample over, else
    ``n`` sets — a joint draw over every utility's landing point and active
    instant, spread over the whole box/window by ``_low_discrepancy``.
    """
    base = [
        {
            "util_type": _attr(ev, "util_type"),
            "side": _attr(ev, "side") or "t",
            "time_from": _attr(ev, "time_from"),
            "time_to": _attr(ev, "time_to"),
            "round_time_s": _attr(ev, "round_time_s"),
            "region": _attr(ev, "region"),
            "zone": _attr(ev, "zone"),
            "x": _attr(ev, "x"),
            "y": _attr(ev, "y"),
            "w": float(_attr(ev, "w") or 0.0),
            "h": float(_attr(ev, "h") or 0.0),
        }
        for ev in utility or []
    ]

    def _span(b) -> float:
        lo, hi = b["time_from"], b["time_to"]
        return (hi - lo) if lo is not None and hi is not None else 0.0

    # one dimension per thing that varies, so pinned utility costs no points
    dims: list[tuple[int, str]] = []
    for i, b in enumerate(base):
        if b["x"] is not None and b["w"] > 0:
            dims.append((i, "x"))
        if b["y"] is not None and b["h"] > 0:
            dims.append((i, "y"))
        if _span(b) > 0:
            dims.append((i, "t"))
    if not dims:
        return [base]

    u = _low_discrepancy(len(dims), n, seed)
    sets: list[list[dict]] = []
    for r in range(n):
        sample = [dict(b) for b in base]
        for j, (i, axis) in enumerate(dims):
            b = base[i]
            if axis == "x":
                sample[i]["x"] = b["x"] + (u[r, j] - 0.5) * b["w"]
            elif axis == "y":
                sample[i]["y"] = b["y"] + (u[r, j] - 0.5) * b["h"]
            else:
                # collapse the window to that instant so token and context agree
                t = b["time_from"] + u[r, j] * (b["time_to"] - b["time_from"])
                sample[i]["time_from"] = sample[i]["time_to"] = t
        sets.append(sample)
    return sets


def _base_rate(
    contexts: list[dict], targets: list[str], only: set[str] | None = None
) -> tuple[dict[str, str], str]:
    by_key: dict[tuple, Counter] = {}
    overall: Counter = Counter()
    for f, y in zip(contexts, targets, strict=True):
        if only is not None and y not in only:
            continue
        by_key.setdefault((f.get("map"), f.get("team")), Counter())[y] += 1
        overall[y] += 1
    table = {f"{m}|{t}": c.most_common(1)[0][0] for (m, t), c in by_key.items()}
    global_mode = overall.most_common(1)[0][0] if overall else SITES[0]
    return table, global_mode


def _to_array(tokens: list[list[float]]) -> np.ndarray:
    if not tokens:
        return np.zeros((0, TOKEN_DIM))
    return np.asarray(tokens, dtype=float).reshape(-1, TOKEN_DIM)


def _reliability(
    conf: list[float], correct: list[int], n_bins: int = 10
) -> tuple[float, list[dict[str, float]]]:
    """Reliability diagram + ECE for a set of (max-prob confidence, was-it-right).
    ECE = Σ_bins (n_bin/N)·|accuracy - confidence|. Bins are equal-width on [0,1]
    empty ones are dropped 
    """
    c = np.asarray(conf, dtype=float)
    ok = np.asarray(correct, dtype=float)
    n = len(c)
    if n == 0:
        return 0.0, []
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins: list[dict[str, float]] = []
    ece = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (c > lo) & (c <= hi) if lo > 0 else (c >= lo) & (c <= hi)
        cnt = int(m.sum())
        if cnt == 0:
            continue
        acc, avg_conf = float(ok[m].mean()), float(c[m].mean())
        bins.append({"confidence": avg_conf, "accuracy": acc, "count": cnt})
        ece += (cnt / n) * abs(acc - avg_conf)
    return float(ece), bins


def evaluate_rows(
    p3: dict[int, np.ndarray],
    tgt: list[str],
    ctxs: list[dict],
    rows: list[int],
    base: tuple[dict[str, str], str],
    site_base: tuple[dict[str, str], str] | None = None,
) -> dict:

    tbl, gmode = base
    stbl, sgmode = site_base or base
    idx3 = {"A": 0, "B": 1, "NoPlant": 2}
    plant = [i for i in rows if tgt[i] in ("A", "B")]

    def _acc(rs: list[int]) -> float | None:
        return float(np.mean([np.argmax(p3[i]) == idx3[tgt[i]] for i in rs])) if rs else None

    def _site_acc(rs: list[int]) -> float | None:
        return (
            float(np.mean([(0 if p3[i][0] >= p3[i][1] else 1) == idx3[tgt[i]] for i in rs]))
            if rs else None
        )

    def _base_acc(rs: list[int]) -> float | None:
        ok = [int(tbl.get(f"{ctxs[i].get('map')}|{ctxs[i].get('team')}", gmode) == tgt[i]) for i in rs]
        return float(np.mean(ok)) if ok else None

    def _site_base_acc(rs: list[int]) -> float | None:
        ok = [
            int(stbl.get(f"{ctxs[i].get('map')}|{ctxs[i].get('team')}", sgmode) == tgt[i])
            for i in rs
        ]
        return float(np.mean(ok)) if ok else None

    def _map(i: int) -> str:
        return str(ctxs[i].get("map") or "?")

    return {
        "n_rounds": len(rows),
        "n_plant": len(plant),
        "accuracy": _acc(rows),
        "site_accuracy": _site_acc(plant),
        "baseline_accuracy": _base_acc(rows),
        "site_baseline_accuracy": _site_base_acc(plant),
        "per_map": [
            {
                "map_id": m,
                "n_rounds": sum(_map(i) == m for i in rows),
                "n_plant": sum(_map(i) == m for i in plant),
                "accuracy": _acc([i for i in rows if _map(i) == m]),
                "site_accuracy": _site_acc([i for i in plant if _map(i) == m]),
                "baseline_accuracy": _base_acc([i for i in rows if _map(i) == m]),
                "site_baseline_accuracy": _site_base_acc([i for i in plant if _map(i) == m]),
            }
            for m in sorted({_map(i) for i in rows})
        ],
    }


@dataclass(frozen=True)
class TrainConfig:

    pooling: str | None = None
    weight_decay: float | None = None
    h_phi: int = 32
    d_embed: int = 24
    h_rho: int = 32
    phi_depth: int = 2
    rho_depth: int = 2
    activation: str = "relu"
    lr: float = 5e-3
    epochs: int = 500
    patience: int = 50
    seed: int = 0
    train_frac: float = 1.0
    use_intent: bool = True 

    def net_kwargs(self) -> dict:
        return {
            "pooling": self.pooling or _POOLING,
            "weight_decay": self.weight_decay if self.weight_decay is not None else _WEIGHT_DECAY,
            "h_phi": self.h_phi, "d_embed": self.d_embed, "h_rho": self.h_rho,
            "phi_depth": self.phi_depth, "rho_depth": self.rho_depth,
            "activation": self.activation, "lr": self.lr,
            "epochs": self.epochs, "patience": self.patience, "seed": self.seed,
        }

    def label(self) -> str:
        kw = self.net_kwargs()
        return (
            f"phi{self.phi_depth}x{self.h_phi}/{self.d_embed} rho{self.rho_depth}x{self.h_rho} "
            f"{self.activation} {kw['pooling']} lr{self.lr:g} wd{kw['weight_decay']:g}"
        )


@dataclass
class SitePredictor:
    # Two stages, kept apart so context can't drown the position signal: a context-driven gate (plant vs NoPlant) + a position-only site head (A vs B)

    gate_net: DeepSets | None = None  # 0 = plant (A/B), 1 = NoPlant — context + tokens
    gate_vec: object | None = None
    site_net: DeepSets | None = None  # 0 = A, 1 = B
    # execution timing given a plant (rush/default/late)
    timing_net: DeepSets | None = None
    timing_classes: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    trained_at: datetime | None = None
    n_rounds: int = 0
    n_teams: int = 0
    accuracy: float | None = None  # held-out 3-class
    site_accuracy: float | None = None  # held-out A-vs-B given a plant
    timing_accuracy: float | None = None  # rush/default/late given a plant
    timing_baseline_accuracy: float | None = None
    baseline_accuracy: float | None = None 
    site_baseline_accuracy: float | None = None
    # Confidence calibration (temperature scaling)
    ece: float | None = None
    ece_uncalibrated: float | None = None
    reliability: list[dict[str, float]] = field(default_factory=list)
    # metrics per map
    per_map: list[dict] = field(default_factory=list)  
    params: dict[str, str] = field(default_factory=dict)

    @property
    def trained(self) -> bool:
        return self.gate_net is not None and self.site_net is not None

    @classmethod
    def train(
        cls,
        samples: list[dict],
        targets: list[str],
        meta: dict,
        timing_targets: list[str | None] | None = None,
        config: TrainConfig | None = None,
    ) -> SitePredictor:
        """ samples = {"tokens", "context"} dicts"""
        from sklearn.feature_extraction import DictVectorizer

        cfg = config or TrainConfig()
        net_kw = cfg.net_kwargs()

        contexts = [s["context"] for s in samples]
        table, global_mode = _base_rate(contexts, targets)
        correct = sum(
            int(table.get(f"{c.get('map')}|{c.get('team')}", global_mode) == y)
            for c, y in zip(contexts, targets, strict=True)
        )
        baseline_acc = correct / len(targets) if targets else 0.0

        self = cls(
            n_rounds=meta.get("n_rounds", len(samples)),
            n_teams=meta.get("n_teams", 0),
            baseline_accuracy=baseline_acc,
        )

        # both stages need signal: ≥2 plant sites (A & B) for the site head and some NoPlant rounds for the gate
        seen = set(targets)
        classes = [s for s in SITES if s in seen]
        if len(samples) < MIN_ROUNDS or not {"A", "B"} <= seen or "NoPlant" not in seen:
            return self

        keep = [i for i, t in enumerate(targets) if t in set(SITES)]
        tokens = [_to_array(samples[i]["tokens"]) for i in keep]
        ctxs = [contexts[i] for i in keep]
        tgt = [targets[i] for i in keep]
        is_plant = [t in ("A", "B") for t in tgt]
        tim = (
            [timing_targets[i] for i in keep] if timing_targets is not None else [None] * len(keep)
        )
        intents = [samples[i].get("intent") for i in keep]

        # One outer 80/20 holdout for honest, comparable metrics
        rng = np.random.default_rng(cfg.seed)
        order = rng.permutation(len(keep))
        n_val = max(2, round(len(keep) * HOLDOUT_FRAC))
        va, tr = list(order[:n_val]), list(order[n_val:])
        if cfg.train_frac < 1.0:
            tr = tr[: max(MIN_ROUNDS, round(len(tr) * cfg.train_frac))]

        vec = DictVectorizer(sparse=False)
        vec.fit([ctxs[i] for i in tr])  # train-only fit avoids leaking val categories
        x_ctx = vec.transform(ctxs)
        dummy = np.zeros((len(keep), 1))  # site head is position-only (no context)

        # plant (0) vs NoPlant (1), on context + tokens
        y_gate = np.array([0 if p else 1 for p in is_plant])
        gate_net, _, _ = DeepSets.fit(
            [tokens[i] for i in tr], x_ctx[tr], y_gate[tr], 2, **net_kw,
        )
        #  A (0) vs B (1) on plant rounds, map-aware tokens only
        trp = [i for i in tr if is_plant[i]]
        site_rows = list(trp)
        site_y = [0 if tgt[i] == "A" else 1 for i in trp]
        if cfg.use_intent:
            extra = [i for i in tr if not is_plant[i] and intents[i] in ("A", "B")]
            site_rows += extra
            site_y += [0 if intents[i] == "A" else 1 for i in extra]
        y_site = np.array(site_y)
        site_net, _, _ = DeepSets.fit(
            [tokens[i] for i in site_rows], dummy[site_rows], y_site, 2, **net_kw,
        )

        # Temperature scaling on the held-out rows: one scalar per net (NLL fit) never moves a binary argmax (site_accuracy unchanged)
        vap = [i for i in va if is_plant[i]]
        gate_logits = np.array([gate_net.predict_logits(tokens[i], x_ctx[i]) for i in va])
        gate_net.temperature = DeepSets.fit_temperature(gate_logits, y_gate[va])
        if vap:
            site_logits = np.array([site_net.predict_logits(tokens[i], dummy[i]) for i in vap])
            y_site_va = np.array([0 if tgt[i] == "A" else 1 for i in vap])
            site_net.temperature = DeepSets.fit_temperature(site_logits, y_site_va)

        # Third head — execution timing given a plant. Trains only when the plant rounds carry timing labels
        trp_t = [i for i in trp if tim[i] is not None]
        timing_classes = [c for c in TIMINGS if c in {tim[i] for i in trp_t}]
        if len(timing_classes) >= 2 and len(trp_t) >= 10:
            ti = {c: k for k, c in enumerate(timing_classes)}
            timing_net, _, _ = DeepSets.fit(
                [tokens[i] for i in trp_t], dummy[trp_t],
                np.array([ti[tim[i]] for i in trp_t]), len(timing_classes), **net_kw,
            )
            vap_t = [i for i in vap if tim[i] is not None]
            if vap_t:
                t_logits = np.array([timing_net.predict_logits(tokens[i], dummy[i]) for i in vap_t])
                timing_net.temperature = DeepSets.fit_temperature(
                    t_logits, np.array([ti[tim[i]] for i in vap_t])
                )
                self.timing_accuracy = float(np.mean([
                    np.argmax(timing_net.predict_proba(tokens[i], dummy[i])) == ti[tim[i]]
                    for i in vap_t
                ]))
                ttbl, tgmode = _base_rate([ctxs[i] for i in trp_t], [tim[i] for i in trp_t])
                self.timing_baseline_accuracy = float(np.mean([
                    int(ttbl.get(f"{ctxs[i].get('map')}|{ctxs[i].get('team')}", tgmode) == tim[i])
                    for i in vap_t
                ]))
            self.timing_net = timing_net
            self.timing_classes = timing_classes

        idx3 = {"A": 0, "B": 1, "NoPlant": 2}

        def proba3(i, *, calibrated: bool = True):
            if calibrated:
                pg = gate_net.predict_proba(tokens[i], x_ctx[i])  # [plant, NoPlant]
                ps = site_net.predict_proba(tokens[i], dummy[i])  # [A, B]
            else:
                pg = _softmax(gate_net.predict_logits(tokens[i], x_ctx[i]))
                ps = _softmax(site_net.predict_logits(tokens[i], dummy[i]))
            return np.array([pg[0] * ps[0], pg[0] * ps[1], pg[1]])  # A, B, NoPlant

        def _conf_correct(calibrated: bool) -> tuple[list[float], list[int]]:
            conf, ok = [], []
            for i in va:
                p = proba3(i, calibrated=calibrated)
                conf.append(float(p.max()))
                ok.append(int(np.argmax(p) == idx3[tgt[i]]))
            return conf, ok

        # Keep the temperatures only if they cut the held-out ECE (a scalar can misfit a tiny holdout); else T=1, so after is never worse than before
        ece_before, _ = _reliability(*_conf_correct(False))
        ece_after, bins_after = _reliability(*_conf_correct(True))
        if ece_after > ece_before:
            gate_net.temperature = site_net.temperature = 1.0
            ece_after, bins_after = _reliability(*_conf_correct(True))
        self.ece, self.reliability = ece_after, bins_after
        self.ece_uncalibrated = ece_before

        # Measured with the final temperatures (what model_proba serves): gate T can shift the plant/NoPlant boundary, so 3-class acc is post-calibration.
        p3 = {i: proba3(i) for i in va}
        base = _base_rate([ctxs[i] for i in tr], [tgt[i] for i in tr])
        site_base = _base_rate([ctxs[i] for i in tr], [tgt[i] for i in tr], only={"A", "B"})
        held = evaluate_rows(p3, tgt, ctxs, va, base, site_base)
        self.accuracy = held["accuracy"]
        self.site_accuracy = held["site_accuracy"]
        self.baseline_accuracy = held["baseline_accuracy"]
        self.site_baseline_accuracy = held["site_baseline_accuracy"]
        self.per_map = held["per_map"]

        self.gate_net = gate_net
        self.gate_vec = vec
        self.site_net = site_net
        self.classes = classes
        self.params = {
            "gate": gate_net.layers,
            "site": site_net.layers,
            "alpha": f"{net_kw['weight_decay']:g}",
            "pooling": net_kw["pooling"],
            "gate_T": f"{gate_net.temperature:.2f}",
            "site_T": f"{site_net.temperature:.2f}",
        }
        if self.timing_net is not None:
            self.params["timing"] = self.timing_net.layers
            self.params["timing_T"] = f"{self.timing_net.temperature:.2f}"
        self.trained_at = datetime.now(UTC)
        return self

    def model_proba(
        self,
        *,
        map_id: str | None,
        team: str | None,
        opponent: str | None,
        buy_type: str | None,
        equip_value: float | int | None,
        utility,
        opponent_buy_type: str | None = None,
        opponent_equip_value: float | int | None = None,
        team_weapon: str | Iterable[str] | None = None,
        opponent_weapon: str | Iterable[str] | None = None,
        phase: str | None = None,
    ) -> dict[str, float] | None:
        """Per-site probabilities P = [gate·site, gate·site, 1-gate], or None untrained"""
        if self.gate_net is None or self.site_net is None or self.gate_vec is None:
            return None
        # A persisted model trained on a different token layout
        if self.gate_net.token_dim != TOKEN_DIM or self.site_net.token_dim != TOKEN_DIM:
            return None
        # Average over (position, time) sampled inside each utility's box/window
        sets = _sampled_utility_sets(utility, _N_SAMPLES)
        ctx_dicts = [
            round_context(
                map_id=map_id,
                team=team,
                opponent=opponent,
                buy_type=buy_type,
                equip_value=equip_value,
                utility=sampled,
                opponent_buy_type=opponent_buy_type,
                opponent_equip_value=opponent_equip_value,
                team_weapon=team_weapon,
                opponent_weapon=opponent_weapon,
                phase=phase,
            )
            for sampled in sets
        ]
        # the context only moves with the sampled time (never the position), so with
        # no time window every sample shares one dict
        if all(c == ctx_dicts[0] for c in ctx_dicts[1:]):
            row = np.asarray(self.gate_vec.transform(ctx_dicts[:1])[0], dtype=float)
            x_ctxs = [row] * len(ctx_dicts)
        else:
            x_ctxs = [np.asarray(r, dtype=float) for r in self.gate_vec.transform(ctx_dicts)]

        dummy = np.zeros(1)
        proba = np.zeros(3)  # A, B, NoPlant
        for sampled, x_ctx in zip(sets, x_ctxs, strict=True):
            tokens = _to_array(round_tokens(map_id, sampled))
            pg = self.gate_net.predict_proba(tokens, x_ctx)  # [plant, NoPlant]
            ps = self.site_net.predict_proba(tokens, dummy)  # [A, B]
            proba += np.array([pg[0] * ps[0], pg[0] * ps[1], pg[1]])
        proba /= len(sets)

        triple = {"A": proba[0], "B": proba[1], "NoPlant": proba[2]}
        out = {s: float(triple.get(s, 0.0)) for s in SITES}
        total = sum(out.values()) or 1.0
        return {k: v / total for k, v in out.items()}

    def proba3_rows(self, samples: list[dict]) -> list[np.ndarray] | None:

        if self.gate_net is None or self.site_net is None or self.gate_vec is None:
            return None
        x_ctx = self.gate_vec.transform([s["context"] for s in samples])
        dummy = np.zeros(1)
        out: list[np.ndarray] = []
        for s, xc in zip(samples, x_ctx, strict=True):
            tokens = _to_array(s["tokens"])
            pg = self.gate_net.predict_proba(tokens, np.asarray(xc, dtype=float))
            ps = self.site_net.predict_proba(tokens, dummy)
            out.append(np.array([pg[0] * ps[0], pg[0] * ps[1], pg[1]]))
        return out

    def timing_proba(self, *, map_id: str | None, utility) -> dict[str, float] | None:
        """P(rush/default/late) given a plant, from the drawn utility only"""
        if self.timing_net is None or self.timing_net.token_dim != TOKEN_DIM:
            return None
        sets = _sampled_utility_sets(utility, _N_SAMPLES)
        dummy = np.zeros(1)
        acc = np.zeros(len(self.timing_classes))
        for sampled in sets:
            tokens = _to_array(round_tokens(map_id, sampled))
            acc += self.timing_net.predict_proba(tokens, dummy)
        acc /= len(sets)
        out = {c: 0.0 for c in TIMINGS}
        for i, c in enumerate(self.timing_classes):
            out[c] = float(acc[i])
        total = sum(out.values()) or 1.0
        return {k: v / total for k, v in out.items()}
