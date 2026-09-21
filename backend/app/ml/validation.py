from __future__ import annotations

import numpy as np

from app.ml.features import SITES
from app.ml.model import MIN_ROUNDS, SitePredictor, TrainConfig, _base_rate, evaluate_rows

DEFAULT_FOLDS = 5


def team_folds(teams: list[str], n_folds: int = DEFAULT_FOLDS) -> list[list[str]]:
    counts: dict[str, int] = {}
    for t in teams:
        counts[t] = counts.get(t, 0) + 1
    k = max(1, min(n_folds, len(counts)))
    folds: list[list[str]] = [[] for _ in range(k)]
    load = [0] * k
    for team, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        i = int(np.argmin(load))
        folds[i].append(team)
        load[i] += n
    return [f for f in folds if f]


def _micro(parts: list[tuple[float | None, int]]) -> float | None:
    pairs = [(v, n) for v, n in parts if v is not None and n > 0]
    if not pairs:
        return None
    return sum(v * n for v, n in pairs) / sum(n for _, n in pairs)


def _pool_per_map(folds: list[dict]) -> list[dict]:
    by_map: dict[str, list[dict]] = {}
    for f in folds:
        for row in f["per_map"]:
            by_map.setdefault(row["map_id"], []).append(row)
    out = []
    for map_id in sorted(by_map):
        rows = by_map[map_id]
        out.append({
            "map_id": map_id,
            "n_rounds": sum(r["n_rounds"] for r in rows),
            "n_plant": sum(r["n_plant"] for r in rows),
            "accuracy": _micro([(r["accuracy"], r["n_rounds"]) for r in rows]),
            "site_accuracy": _micro([(r["site_accuracy"], r["n_plant"]) for r in rows]),
            "baseline_accuracy": _micro([(r["baseline_accuracy"], r["n_rounds"]) for r in rows]),
            "site_baseline_accuracy": _micro(
                [(r["site_baseline_accuracy"], r["n_plant"]) for r in rows]
            ),
        })
    return out


def _teams(samples: list[dict], targets: list[str]) -> dict[int, str]:
    keep = [i for i, t in enumerate(targets) if t in set(SITES)]
    return {i: str(samples[i]["context"].get("team") or "?") for i in keep}


def fold_teams(
    samples: list[dict], targets: list[str], n_folds: int = DEFAULT_FOLDS
) -> list[list[str]]:
    return team_folds(list(_teams(samples, targets).values()), n_folds)


def fit_fold(
    samples: list[dict],
    targets: list[str],
    timing_targets: list[str | None] | None,
    held: list[str],
    config: TrainConfig | None = None,
) -> dict:
    """Train without the ``held`` teams (and their opponents' rounds) and score on them.
    A fold that cannot train comes back with a ``reason``."""
    teams = _teams(samples, targets)
    opponents = {i: str(samples[i]["context"].get("opponent") or "?") for i in teams}
    ctxs = [s["context"] for s in samples]
    group = set(held)
    test = [i for i in teams if teams[i] in group]
    train = [i for i in teams if teams[i] not in group and opponents[i] not in group]
    row = {"teams": sorted(group), "n_teams": len(group), "n_train": len(train)}

    if len(train) < MIN_ROUNDS or not test:
        return {**row, "reason": "too few training rounds"}
    predictor = SitePredictor.train(
        [samples[i] for i in train],
        [targets[i] for i in train],
        {"n_rounds": len(train), "n_teams": len({teams[i] for i in train})},
        [timing_targets[i] for i in train] if timing_targets is not None else None,
        config=config,
    )
    if not predictor.trained:
        return {**row, "reason": "no A/B/NoPlant split in the training rounds"}

    probs = predictor.proba3_rows([samples[i] for i in test])
    p3 = {i: probs[k] for k, i in enumerate(test)}
    base = _base_rate([ctxs[i] for i in train], [targets[i] for i in train])
    site_base = _base_rate(
        [ctxs[i] for i in train], [targets[i] for i in train], only={"A", "B"}
    )
    return {**row, **evaluate_rows(p3, targets, ctxs, test, base, site_base)}


def leave_teams_out(
    samples: list[dict],
    targets: list[str],
    timing_targets: list[str | None] | None = None,
    n_folds: int = DEFAULT_FOLDS,
    config: TrainConfig | None = None,
) -> dict:
    rows = [
        fit_fold(samples, targets, timing_targets, held, config)
        for held in fold_teams(samples, targets, n_folds)
    ]
    return summarise_folds(samples, targets, rows)


def summarise_folds(samples: list[dict], targets: list[str], rows: list[dict]) -> dict:
    """Pool per-fold rows (from :func:`fit_fold`) into the leave-teams-out result."""
    teams = _teams(samples, targets)
    folds = [r for r in rows if "reason" not in r]
    skipped = [r for r in rows if "reason" in r]
    return {
        "n_folds": len(folds),
        "n_skipped": len(skipped),
        "skipped": skipped,
        "n_rounds": sum(f["n_rounds"] for f in folds),
        "n_plant": sum(f["n_plant"] for f in folds),
        "n_teams": len({t for i, t in teams.items()}),
        "accuracy": _micro([(f["accuracy"], f["n_rounds"]) for f in folds]),
        "site_accuracy": _micro([(f["site_accuracy"], f["n_plant"]) for f in folds]),
        "baseline_accuracy": _micro([(f["baseline_accuracy"], f["n_rounds"]) for f in folds]),
        "site_baseline_accuracy": _micro(
            [(f["site_baseline_accuracy"], f["n_plant"]) for f in folds]
        ),
        "per_map": _pool_per_map(folds),
        "folds": folds,
    }
