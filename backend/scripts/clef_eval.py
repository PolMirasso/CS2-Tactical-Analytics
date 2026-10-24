from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
from pathlib import Path

import numpy as np
from sqlalchemy import select

from app.config import get_settings
from app.db import _ensure, init_db
from app.domain.models import User
from app.ml.clef import DEFAULT_HOST, DEFAULT_MODEL, ask
from app.ml.dataset import build_dataset
from app.ml.features import SITES, TIMINGS
from app.ml.model import HOLDOUT_FRAC, _base_rate, _reliability, evaluate_rows
from app.ml.validation import _teams, fold_teams, summarise_folds

OUT = get_settings().data_dir / "sweep_clef"
_IDX3 = {"A": 0, "B": 1, "NoPlant": 2}


def _load() -> tuple[list[dict], list[str], list, dict]:
    init_db()
    with _ensure()() as session:
        users = list(session.scalars(select(User).order_by(User.id)))
        user = next((u for u in users if u.is_admin), users[0] if users else None)
        if user is None:
            sys.exit("No users in the DB — nothing to measure.")
        return build_dataset(session, user)


def _keep(targets: list[str]) -> list[int]:
    return [i for i, t in enumerate(targets) if t in set(SITES)]


def _digest(state: dict) -> str:
    return hashlib.sha1(json.dumps(state, sort_keys=True).encode()).hexdigest()[:12]


def _read_answers(path: Path) -> dict[int, dict]:
    if not path.exists():
        return {}
    rows = (json.loads(line) for line in path.read_text().splitlines() if line.strip())
    return {r["i"]: r for r in rows}


def run_ask(samples, targets, path: Path, host: str, model: str, limit: int | None) -> None:
    done = _read_answers(path)
    for i, r in done.items():
        if r["digest"] != _digest(samples[i]["clef"]):
            sys.exit(f"answers.jsonl row {i} no longer matches the dataset (re-parsed?)")
    order = [int(k) for k in np.random.default_rng(0).permutation(_keep(targets))]
    todo = [i for i in order if i not in done][:limit]
    print(f"{len(done)} done, {len(todo)} to ask ({host}, {model})", flush=True)

    t0 = time.time()
    with path.open("a") as fh:
        for n, i in enumerate(todo, 1):
            for attempt in range(3):
                try:
                    t = time.time()
                    out = ask(samples[i]["clef"], host=host, model=model)
                    break
                except (urllib.error.URLError, TimeoutError) as e:
                    if attempt == 2:
                        raise
                    print(f"  round {i}: {e}, retrying", flush=True)
                    time.sleep(30)
            fh.write(json.dumps({
                "i": i, "digest": _digest(samples[i]["clef"]),
                "map": samples[i]["context"].get("map"), "target": targets[i], "model": model,
                "seconds": round(time.time() - t, 2), **out,
            }) + "\n")
            fh.flush()
            if n % 25 == 0 or n == len(todo):
                rate = (time.time() - t0) / n
                print(f"  {n}/{len(todo)} · {rate:.1f} s/round · "
                      f"~{rate * (len(todo) - n) / 3600:.1f} h left", flush=True)


def _probs(answer: dict) -> dict[str, float]:
    return {k: float(v) for k, v in answer["probabilities"].items()}


def _p3(row: dict) -> np.ndarray:
    site, plant = _probs(row["answers"]["site"]), _probs(row["answers"]["plant"])
    pa = site["A"] / (site["A"] + site["B"])
    pp = plant["plant"] / (plant["plant"] + plant["no_plant"])
    return np.array([pp * pa, pp * (1 - pa), 1 - pp])


def _timing(row: dict) -> str:
    p = _probs(row["answers"]["timing"])
    return max(TIMINGS, key=lambda c: p.get(c, 0.0))


def _ece(p3: dict[int, np.ndarray], targets: list[str], rows: list[int]) -> tuple[float, list]:
    return _reliability([float(p3[i].max()) for i in rows],
                        [int(np.argmax(p3[i]) == _IDX3[targets[i]]) for i in rows])


def _timing_metrics(rows, train, ctxs, tim, pred) -> tuple[float | None, float | None]:
    test = [i for i in rows if tim[i] is not None]
    if not test:
        return None, None
    tr = [i for i in train if tim[i] is not None]
    tbl, gmode = _base_rate([ctxs[i] for i in tr], [tim[i] for i in tr])
    acc = float(np.mean([pred[i] == tim[i] for i in test]))
    base = float(np.mean([
        tbl.get(f"{ctxs[i].get('map')}|{ctxs[i].get('team')}", gmode) == tim[i] for i in test
    ]))
    return acc, base


def holdout(samples, targets, timing, p3, pred_t, seeds: int) -> list[dict]:
    """The split SitePredictor.train draws for each seed; metrics on its answered 20%"""
    keep = _keep(targets)
    ctxs = [s["context"] for s in samples]
    runs = []
    for seed in range(seeds):
        order = np.random.default_rng(seed).permutation(len(keep))
        n_val = max(2, round(len(keep) * HOLDOUT_FRAC))
        va = [keep[k] for k in order[:n_val] if keep[k] in p3]
        tr = [keep[k] for k in order[n_val:]]
        base = _base_rate([ctxs[i] for i in tr], [targets[i] for i in tr])
        site_base = _base_rate([ctxs[i] for i in tr], [targets[i] for i in tr], only={"A", "B"})
        row = evaluate_rows(p3, targets, ctxs, va, base, site_base)
        row["ece"], row["reliability"] = _ece(p3, targets, va)
        plant = [i for i in va if targets[i] in ("A", "B")]
        row["timing_accuracy"], row["timing_baseline_accuracy"] = _timing_metrics(
            plant, [i for i in tr if targets[i] in ("A", "B")], ctxs, timing, pred_t)
        runs.append({"seed": seed, **row})
    return runs


def leave_teams_out(samples, targets, p3, folds: int) -> dict:
    """fit_fold's train/test split per fold, without the training"""
    teams = _teams(samples, targets)
    ctxs = [s["context"] for s in samples]
    rows = []
    for held in fold_teams(samples, targets, folds):
        group = set(held)
        opp = {i: str(ctxs[i].get("opponent") or "?") for i in teams}
        test = [i for i in teams if teams[i] in group and i in p3]
        train = [i for i in teams if teams[i] not in group and opp[i] not in group]
        base = _base_rate([ctxs[i] for i in train], [targets[i] for i in train])
        site_base = _base_rate([ctxs[i] for i in train], [targets[i] for i in train],
                               only={"A", "B"})
        rows.append({"teams": sorted(group), "n_teams": len(group), "n_train": len(train),
                     **evaluate_rows(p3, targets, ctxs, test, base, site_base)})
    return summarise_folds(samples, targets, rows)


def _fmt(v: float | None) -> str:
    return "     —" if v is None else f"{v:.3f}"


def run_score(samples, targets, timing, path: Path, seeds: int, folds: int) -> None:
    answers = _read_answers(path)
    if not answers:
        sys.exit(f"no answers in {path}")
    p3 = {i: _p3(r) for i, r in answers.items()}
    pred_t = {i: _timing(r) for i, r in answers.items()}
    n_keep = len(_keep(targets))
    secs = [r["seconds"] for r in answers.values()]
    print(f"{len(answers)}/{n_keep} rounds answered · {np.median(secs):.1f} s/round median")

    runs = holdout(samples, targets, timing, p3, pred_t, seeds)
    def mean(key):
        vals = [r[key] for r in runs if r.get(key) is not None]
        return (float(np.mean(vals)), float(np.std(vals))) if vals else (None, None)
    print(f"\n80/20 holdout, {seeds} splits (answered rounds of each 20%)")
    for key in ("site_accuracy", "site_baseline_accuracy", "accuracy", "baseline_accuracy",
                "timing_accuracy", "timing_baseline_accuracy", "ece"):
        m, sd = mean(key)
        print(f"  {key:<26}{_fmt(m)}" + (f" ±{sd:.3f}" if sd is not None else ""))

    cv = leave_teams_out(samples, targets, p3, folds)
    print(f"\nLeave-teams-out, {folds} folds")
    print(f"  site {_fmt(cv['site_accuracy'])}  sbase {_fmt(cv['site_baseline_accuracy'])}"
          f"  3-class {_fmt(cv['accuracy'])}  base {_fmt(cv['baseline_accuracy'])}"
          f"  rounds {cv['n_rounds']}  plants {cv['n_plant']}")
    print(f"\n  {'map':<12}{'plants':>8}{'site':>8}{'sbase':>8}")
    for m in cv["per_map"]:
        print(f"  {m['map_id']:<12}{m['n_plant']:>8}{_fmt(m['site_accuracy']):>8}"
              f"{_fmt(m['site_baseline_accuracy']):>8}")

    meta = {"n_rounds": len(samples), "n_answered": len(answers), "n_keep": n_keep,
            "model": next(iter(answers.values())).get("model"),
            "median_seconds": float(np.median(secs))}
    (OUT / "holdout.json").write_text(json.dumps(
        {"meta": {**meta, "seeds": seeds}, "results": {"clef": {"runs": runs}}}, indent=1))
    (OUT / "lto.json").write_text(json.dumps(
        {"meta": {**meta, "folds": folds}, "results": {"clef": {"cv": cv}}}, indent=1))
    print(f"\nwrote {OUT}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="ask", choices=("ask", "score"))
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=None, help="ask at most this many rounds")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    samples, targets, timing, _ = _load()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "answers.jsonl"
    if args.stage == "ask":
        run_ask(samples, targets, path, args.host, args.model, args.limit)
    else:
        run_score(samples, targets, timing, path, args.seeds, args.folds)


if __name__ == "__main__":
    main()
