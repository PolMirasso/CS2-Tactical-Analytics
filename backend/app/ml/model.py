from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from app.ml.deepsets import DeepSets, _softmax
from app.ml.features import SITES, TOKEN_DIM, _attr, round_context, round_tokens

# Below this many rounds (or < 2 distinct sites) we don't fit the net and serve
# the historical base rate instead — too little signal to learn anything.
MIN_ROUNDS = 20
_WEIGHT_DECAY = 1e-4
# Set pooling over the round's utility tokens: mean (baseline), sum (keeps cardinality) or attention (learned per-grenade weights)
_POOLING = "attention"
# How many landing points to draw inside each drawn box at inference. The model
# is point-trained, so the drawn box means "lands somewhere in this area" and the
# time window means "active across this span": we average the prediction over
# (position, time) sampled in them (wider box/window ⇒ broader, less peaked output).
_N_SAMPLES = 24


def _sampled_utility_sets(utility, n: int, seed: int = 0) -> list[list[dict]]:
    """Perturbed copies of ``utility`` with each x/y jittered inside its w×h box
    and its throw time drawn uniformly inside its [time_from, time_to] window.

    Returns one set when nothing has an area or a time span to sample over, else
    ``n`` Monte-Carlo sets — a joint draw over every utility's landing point and
    active instant.
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

    if not any(b["w"] > 0 or b["h"] > 0 or _span(b) > 0 for b in base):
        return [base]

    rng = np.random.default_rng(seed)
    sets: list[list[dict]] = []
    for _ in range(n):
        sample = []
        for b in base:
            d = dict(b)
            if b["x"] is not None and b["w"] > 0:
                d["x"] = b["x"] + rng.uniform(-b["w"] / 2, b["w"] / 2)
            if b["y"] is not None and b["h"] > 0:
                d["y"] = b["y"] + rng.uniform(-b["h"] / 2, b["h"] / 2)
            if _span(b) > 0:
                # Active at a random instant of the window: collapse to that time
                # so both the token and the round context see "present at t".
                t = rng.uniform(b["time_from"], b["time_to"])
                d["time_from"] = d["time_to"] = t
            sample.append(d)
        sets.append(sample)
    return sets


def _base_rate(contexts: list[dict], targets: list[str]) -> tuple[dict[str, str], str]:
    by_key: dict[tuple, Counter] = {}
    overall: Counter = Counter()
    for f, y in zip(contexts, targets, strict=True):
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


@dataclass
class SitePredictor:
    # Two stages, kept apart so context can't drown the position signal: a context-driven gate (plant vs NoPlant) + a position-only site head (A vs B)

    gate_net: DeepSets | None = None  # 0 = plant (A/B), 1 = NoPlant — context + tokens
    gate_vec: object | None = None
    site_net: DeepSets | None = None  # 0 = A, 1 = B 
    classes: list[str] = field(default_factory=list)
    trained_at: datetime | None = None
    n_rounds: int = 0
    n_teams: int = 0
    accuracy: float | None = None  # held-out 3-class
    site_accuracy: float | None = None  # held-out A-vs-B given a plant
    baseline_accuracy: float | None = None
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
    def train(cls, samples: list[dict], targets: list[str], meta: dict) -> SitePredictor:
        """ samples = {"tokens", "context"} dicts"""
        from sklearn.feature_extraction import DictVectorizer

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

        # One outer holdout for honest, comparable metrics
        rng = np.random.default_rng(0)
        order = rng.permutation(len(keep))
        n_val = max(2, len(keep) // 5)
        va, tr = list(order[:n_val]), list(order[n_val:])

        vec = DictVectorizer(sparse=False)
        vec.fit([ctxs[i] for i in tr])  # train-only fit avoids leaking val categories
        x_ctx = vec.transform(ctxs)
        dummy = np.zeros((len(keep), 1))  # site head is position-only (no context)

        # plant (0) vs NoPlant (1), on context + tokens
        y_gate = np.array([0 if p else 1 for p in is_plant])
        gate_net, _, _ = DeepSets.fit(
            [tokens[i] for i in tr], x_ctx[tr], y_gate[tr], 2,
            weight_decay=_WEIGHT_DECAY, pooling=_POOLING,
        )
        #  A (0) vs B (1) on plant rounds, map-aware tokens only
        trp = [i for i in tr if is_plant[i]]
        y_site = np.array([0 if tgt[i] == "A" else 1 for i in trp])
        site_net, _, _ = DeepSets.fit(
            [tokens[i] for i in trp], dummy[trp], y_site, 2,
            weight_decay=_WEIGHT_DECAY, pooling=_POOLING,
        )

        # Temperature scaling on the held-out rows: one scalar per net (NLL fit) never moves a binary argmax (site_accuracy unchanged)
        vap = [i for i in va if is_plant[i]]
        gate_logits = np.array([gate_net.predict_logits(tokens[i], x_ctx[i]) for i in va])
        gate_net.temperature = DeepSets.fit_temperature(gate_logits, y_gate[va])
        if vap:
            site_logits = np.array([site_net.predict_logits(tokens[i], dummy[i]) for i in vap])
            y_site_va = np.array([0 if tgt[i] == "A" else 1 for i in vap])
            site_net.temperature = DeepSets.fit_temperature(site_logits, y_site_va)

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
        tbl, gmode = _base_rate([ctxs[i] for i in tr], [tgt[i] for i in tr])

        def _acc(rows: list[int]) -> float | None:
            return float(np.mean([np.argmax(p3[i]) == idx3[tgt[i]] for i in rows])) if rows else None

        def _site_acc(rows: list[int]) -> float | None:
            return (
                float(np.mean([(0 if p3[i][0] >= p3[i][1] else 1) == idx3[tgt[i]] for i in rows]))
                if rows else None
            )

        def _base_acc(rows: list[int]) -> float | None:
            ok = [int(tbl.get(f"{ctxs[i].get('map')}|{ctxs[i].get('team')}", gmode) == tgt[i]) for i in rows]
            return float(np.mean(ok)) if ok else None

        self.accuracy = _acc(va)
        self.site_accuracy = _site_acc(vap)
        self.baseline_accuracy = _base_acc(va)

        # metrics split per map 
        def _map(i: int) -> str:
            return str(ctxs[i].get("map") or "?")

        self.per_map = [
            {
                "map_id": m,
                "n_rounds": sum(_map(i) == m for i in va),
                "n_plant": sum(_map(i) == m for i in vap),
                "accuracy": _acc([i for i in va if _map(i) == m]),
                "site_accuracy": _site_acc([i for i in vap if _map(i) == m]),
                "baseline_accuracy": _base_acc([i for i in va if _map(i) == m]),
            }
            for m in sorted({_map(i) for i in va})
        ]

        self.gate_net = gate_net
        self.gate_vec = vec
        self.site_net = site_net
        self.classes = classes
        self.params = {
            "gate": gate_net.layers,
            "site": site_net.layers,
            "alpha": f"{_WEIGHT_DECAY:g}",
            "pooling": _POOLING,
            "gate_T": f"{gate_net.temperature:.2f}",
            "site_T": f"{site_net.temperature:.2f}",
        }
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
    ) -> dict[str, float] | None:
        """Per-site probabilities P = [gate·site, gate·site, 1-gate], or None untrained"""
        if self.gate_net is None or self.site_net is None or self.gate_vec is None:
            return None
        # A persisted model trained on a different token layout
        if self.gate_net.token_dim != TOKEN_DIM or self.site_net.token_dim != TOKEN_DIM:
            return None
        # Average over (position, time) sampled inside each utility's box/window;
        # context is recomputed per sample because the sampled time feeds the gate
        sets = _sampled_utility_sets(utility, _N_SAMPLES)
        dummy = np.zeros(1)
        proba = np.zeros(3)  # A, B, NoPlant
        for sampled in sets:
            ctx_dict = round_context(
                map_id=map_id,
                team=team,
                opponent=opponent,
                buy_type=buy_type,
                equip_value=equip_value,
                utility=sampled,
            )
            x_ctx = np.asarray(self.gate_vec.transform([ctx_dict])[0], dtype=float)
            tokens = _to_array(round_tokens(map_id, sampled))
            pg = self.gate_net.predict_proba(tokens, x_ctx)  # [plant, NoPlant]
            ps = self.site_net.predict_proba(tokens, dummy)  # [A, B]
            proba += np.array([pg[0] * ps[0], pg[0] * ps[1], pg[1]])
        proba /= len(sets)

        triple = {"A": proba[0], "B": proba[1], "NoPlant": proba[2]}
        out = {s: float(triple.get(s, 0.0)) for s in SITES}
        total = sum(out.values()) or 1.0
        return {k: v / total for k, v in out.items()}
