from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.ml.features import SITES, round_features

# Below this many rounds (or <2 distinct sites) we don't fit the MLP and serve
# the historical base rate instead — too little signal to learn anything.
MIN_ROUNDS = 20


def _base_rate(feats: list[dict], targets: list[str]) -> tuple[dict[str, str], str]:
    by_key: dict[tuple, Counter] = {}
    overall: Counter = Counter()
    for f, y in zip(feats, targets, strict=True):
        by_key.setdefault((f.get("map"), f.get("team")), Counter())[y] += 1
        overall[y] += 1
    table = {f"{m}|{t}": c.most_common(1)[0][0] for (m, t), c in by_key.items()}
    global_mode = overall.most_common(1)[0][0] if overall else SITES[0]
    return table, global_mode


@dataclass
class SitePredictor:
    pipeline: object | None = None
    classes: list[str] = field(default_factory=list)
    trained_at: datetime | None = None
    n_rounds: int = 0
    n_teams: int = 0
    accuracy: float | None = None
    baseline_accuracy: float | None = None

    @property
    def trained(self) -> bool:
        return self.pipeline is not None

    @classmethod
    def train(cls, feats: list[dict], targets: list[str], meta: dict) -> SitePredictor:
        from sklearn.feature_extraction import DictVectorizer
        from sklearn.model_selection import cross_val_score
        from sklearn.neural_network import MLPClassifier
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler

        table, global_mode = _base_rate(feats, targets)
        correct = sum(
            int(table.get(f"{f.get('map')}|{f.get('team')}", global_mode) == y)
            for f, y in zip(feats, targets, strict=True)
        )
        baseline_acc = correct / len(targets) if targets else 0.0

        self = cls(
            n_rounds=meta.get("n_rounds", len(feats)),
            n_teams=meta.get("n_teams", 0),
            baseline_accuracy=baseline_acc,
        )
        if len(feats) < MIN_ROUNDS or len(set(targets)) < 2:
            return self

        pipe = Pipeline(
            [
                ("vec", DictVectorizer(sparse=True)),
                ("scale", StandardScaler(with_mean=False)),
                ("mlp", MLPClassifier(hidden_layer_sizes=(64,), max_iter=600, random_state=0)),
            ]
        )
        cv = min(5, min(Counter(targets).values()))
        if cv >= 2:
            try:
                self.accuracy = float(cross_val_score(pipe, feats, targets, cv=cv).mean())
            except Exception:
                self.accuracy = None
        pipe.fit(feats, targets)
        if self.accuracy is None:
            self.accuracy = float(pipe.score(feats, targets))
        self.pipeline = pipe
        self.classes = list(pipe.named_steps["mlp"].classes_)
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
        """Per-site probabilities from the MLP, or ``None`` when untrained."""
        if self.pipeline is None:
            return None
        feats = round_features(
            map_id=map_id,
            team=team,
            opponent=opponent,
            buy_type=buy_type,
            equip_value=equip_value,
            utility=utility,
        )
        proba = self.pipeline.predict_proba([feats])[0]
        out = {s: 0.0 for s in SITES}
        for cls_name, p in zip(self.classes, proba, strict=True):
            out[cls_name] = float(p)
        total = sum(out.values()) or 1.0
        return {k: v / total for k, v in out.items()}
