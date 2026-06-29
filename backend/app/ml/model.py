from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from app.ml.deepsets import DeepSets
from app.ml.features import SITES, TOKEN_DIM, _attr, round_context, round_tokens

# Below this many rounds (or < 2 distinct sites) we don't fit the net and serve
# the historical base rate instead — too little signal to learn anything.
MIN_ROUNDS = 20
_WEIGHT_DECAY = 1e-4
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


@dataclass
class SitePredictor:
    net: DeepSets | None = None
    vectorizer: object | None = None
    classes: list[str] = field(default_factory=list)
    trained_at: datetime | None = None
    n_rounds: int = 0
    n_teams: int = 0
    accuracy: float | None = None
    baseline_accuracy: float | None = None
    params: dict[str, str] = field(default_factory=dict)

    @property
    def trained(self) -> bool:
        return self.net is not None

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

        classes = [s for s in SITES if s in set(targets)]
        if len(samples) < MIN_ROUNDS or len(classes) < 2:
            return self

        vec = DictVectorizer(sparse=False)
        x_ctx = vec.fit_transform(contexts)
        token_sets = [_to_array(s["tokens"]) for s in samples]
        class_idx = {c: i for i, c in enumerate(classes)}
        y = np.asarray([class_idx[t] for t in targets])

        net, val_acc = DeepSets.fit(
            token_sets, x_ctx, y, len(classes), weight_decay=_WEIGHT_DECAY
        )

        self.net = net
        self.vectorizer = vec
        self.classes = classes
        self.accuracy = val_acc
        self.params = {"layers": net.layers, "alpha": f"{_WEIGHT_DECAY:g}"}
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
        """Per-site probabilities from the DeepSets net, or None when untrained"""
        if self.net is None or self.vectorizer is None:
            return None
        # Average over (position, time) sampled inside each utility's box/window;
        # context is recomputed per sample because the sampled time feeds it too.
        sets = _sampled_utility_sets(utility, _N_SAMPLES)
        proba = np.zeros(len(self.classes))
        for sampled in sets:
            ctx_dict = round_context(
                map_id=map_id,
                team=team,
                opponent=opponent,
                buy_type=buy_type,
                equip_value=equip_value,
                utility=sampled,
            )
            x_ctx = np.asarray(self.vectorizer.transform([ctx_dict])[0], dtype=float)
            tokens = _to_array(round_tokens(map_id, sampled))
            proba += self.net.predict_proba(tokens, x_ctx)
        proba /= len(sets)

        out = {s: 0.0 for s in SITES}
        for cls_name, p in zip(self.classes, proba, strict=True):
            out[cls_name] = float(p)
        total = sum(out.values()) or 1.0
        return {k: v / total for k, v in out.items()}
