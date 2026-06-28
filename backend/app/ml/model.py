from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from app.ml.deepsets import DeepSets
from app.ml.features import SITES, TOKEN_DIM, round_context, round_tokens

# Below this many rounds (or < 2 distinct sites) we don't fit the net and serve
# the historical base rate instead — too little signal to learn anything.
MIN_ROUNDS = 20
_WEIGHT_DECAY = 1e-4


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
        ctx_dict = round_context(
            map_id=map_id,
            team=team,
            opponent=opponent,
            buy_type=buy_type,
            equip_value=equip_value,
            utility=utility,
        )
        x_ctx = self.vectorizer.transform([ctx_dict])[0]
        tokens = _to_array(round_tokens(map_id, utility))
        proba = self.net.predict_proba(tokens, np.asarray(x_ctx, dtype=float))

        out = {s: 0.0 for s in SITES}
        for cls_name, p in zip(self.classes, proba, strict=True):
            out[cls_name] = float(p)
        total = sum(out.values()) or 1.0
        return {k: v / total for k, v in out.items()}
