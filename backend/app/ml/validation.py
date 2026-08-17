from __future__ import annotations

import numpy as np

from app.ml.features import SITES
from app.ml.model import MIN_ROUNDS, SitePredictor, _base_rate, evaluate_rows

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
        })
    return out


def leave_teams_out(
    samples: list[dict],
    targets: list[str],
    timing_targets: list[str | None] | None = None,
    n_folds: int = DEFAULT_FOLDS,
) -> dict:

    keep = [i for i, t in enumerate(targets) if t in set(SITES)]
    teams = {i: str(samples[i]["context"].get("team") or "?") for i in keep}
    opponents = {i: str(samples[i]["context"].get("opponent") or "?") for i in keep}
    ctxs = [s["context"] for s in samples]

    folds: list[dict] = []
    skipped: list[dict] = []
    for held in team_folds([teams[i] for i in keep], n_folds):
        group = set(held)
        test = [i for i in keep if teams[i] in group]
        train = [i for i in keep if teams[i] not in group and opponents[i] not in group]
        row = {"teams": sorted(group), "n_teams": len(group), "n_train": len(train)}

        if len(train) < MIN_ROUNDS or not test:
            skipped.append({**row, "reason": "too few training rounds"})
            continue
        predictor = SitePredictor.train(
            [samples[i] for i in train],
            [targets[i] for i in train],
            {"n_rounds": len(train), "n_teams": len({teams[i] for i in train})},
            [timing_targets[i] for i in train] if timing_targets is not None else None,
        )
        if not predictor.trained:
            skipped.append({**row, "reason": "no A/B/NoPlant split in the training rounds"})
            continue

        probs = predictor.proba3_rows([samples[i] for i in test])
        p3 = {i: probs[k] for k, i in enumerate(test)}
        base = _base_rate([ctxs[i] for i in train], [targets[i] for i in train])
        folds.append({**row, **evaluate_rows(p3, targets, ctxs, test, base)})

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
        "per_map": _pool_per_map(folds),
        "folds": folds,
    }
