from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.error
from collections import Counter
from pathlib import Path

import numpy as np
from sqlalchemy import select

from app.config import get_settings
from app.db import _ensure, init_db
from app.domain.models import User
from app.ml.clef import DEFAULT_HOST, DEFAULT_MODEL, ask, clef_example, questions
from app.ml.dataset import build_dataset
from app.ml.features import SITES, TIMINGS
from app.ml.model import HOLDOUT_FRAC, _base_rate, _reliability, evaluate_rows
from app.ml.validation import _teams, fold_teams, summarise_folds

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


def _out(context: bool, shots: int, pick: str) -> Path:
    name = "sweep_clef" + ("_ctx" if context else "")
    if shots:
        name += f"_k{shots}" + ("_rand" if pick == "random" else "")
    return get_settings().data_dir / name


def _bag(state: dict) -> Counter:
    return Counter((g["type"], g["callout"]) for g in state["utility_thrown_by_T_so_far"])


def _similarity(a: Counter, b: Counter) -> float:
    union = sum((a | b).values())
    return sum((a & b).values()) / union if union else 1.0


def _fold_pools(samples, targets, folds: int) -> dict[int, tuple[int, list[int]]]:
    """Each leave-teams-out test round with its fold and that fold's training rounds"""
    teams = _teams(samples, targets)
    opp = {i: str(samples[i]["context"].get("opponent") or "?") for i in teams}
    out = {}
    for k, held in enumerate(fold_teams(samples, targets, folds)):
        group = set(held)
        train = [i for i in teams if teams[i] not in group and opp[i] not in group]
        out.update({i: (k, train) for i in teams if teams[i] in group})
    return out


def _examples(i, samples, targets, pool, shots: int, pick: str, bags,
              context: bool) -> list[dict]:
    """Labelled rounds from the fold's training teams, same map; the closest goes last"""
    m = samples[i]["context"].get("map")
    pool = [j for j in pool if samples[j]["context"].get("map") == m]
    if pick == "random":
        rng = np.random.default_rng(i)
        chosen = [pool[k] for k in rng.choice(len(pool), min(shots, len(pool)), replace=False)]
    else:
        chosen = sorted(pool, key=lambda j: (-_similarity(bags[i], bags[j]), j))[:shots][::-1]
    return [clef_example(samples[j]["clef"], targets[j], samples[j]["intent"],
                         samples[j]["plant_time_s"],
                         samples[j]["clef_round"] if context else None) for j in chosen]


def build_states(samples, targets, context: bool, shots: int, pick: str,
                 folds: int) -> dict[int, tuple[dict, int | None]]:
    """Clef's input per round, with the leave-teams-out fold it was built for when it has shots"""
    pools = _fold_pools(samples, targets, folds) if shots else {}
    bags = {i: _bag(s["clef"]) for i, s in enumerate(samples)} if shots else {}
    out = {}
    for i in _keep(targets):
        base = samples[i]["clef"]
        state = {k: v for k, v in base.items() if k != "utility_thrown_by_T_so_far"}
        fold = None
        if shots:
            if i not in pools:
                continue
            fold, pool = pools[i]
            state["labelled_rounds_by_other_teams_on_this_map"] = _examples(
                i, samples, targets, pool, shots, pick, bags, context)
        if context:
            state["this_round"] = samples[i]["clef_round"]
        state["utility_thrown_by_T_so_far"] = base["utility_thrown_by_T_so_far"]
        out[i] = (state, fold)
    return out


def run_ask(samples, targets, states, qs, path: Path, host: str, model: str, num_ctx: int,
            limit: int | None) -> None:
    done = _read_answers(path)
    for i, r in done.items():
        if i not in states or r["digest"] != _digest(states[i][0]):
            sys.exit(f"{path.name} row {i} no longer matches the dataset (re-parsed?)")
    order = [int(k) for k in np.random.default_rng(0).permutation(_keep(targets))]
    todo = [i for i in order if i in states and i not in done][:limit]
    print(f"{len(done)} done, {len(todo)} to ask ({host}, {model})", flush=True)

    t0 = time.time()
    with path.open("a") as fh:
        for n, i in enumerate(todo, 1):
            state, fold = states[i]
            for attempt in range(3):
                try:
                    t = time.time()
                    out = ask(state, host=host, model=model, questions=qs)
                    break
                except (urllib.error.URLError, TimeoutError) as e:
                    if attempt == 2:
                        raise
                    print(f"  round {i}: {e}, retrying", flush=True)
                    time.sleep(30)
            # Ollama truncates an over-long prompt silently
            if out["usage"].get("input_tokens", 0) >= 0.95 * num_ctx:
                sys.exit(f"round {i}: {out['usage']['input_tokens']} input tokens, close to "
                         f"num_ctx {num_ctx}; use a model variant with a bigger num_ctx")
            fh.write(json.dumps({
                "i": i, "digest": _digest(state),
                "map": samples[i]["context"].get("map"), "target": targets[i], "model": model,
                **({"fold": fold} if fold is not None else {}),
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


def run_score(samples, targets, timing, path: Path, seeds: int, folds: int, shots: int) -> None:
    answers = _read_answers(path)
    if not answers:
        sys.exit(f"no answers in {path}")
    out_dir = path.parent
    p3 = {i: _p3(r) for i, r in answers.items()}
    pred_t = {i: _timing(r) for i, r in answers.items()}
    n_keep = len(_keep(targets))
    secs = [r["seconds"] for r in answers.values()]
    print(f"{len(answers)}/{n_keep} rounds answered · {np.median(secs):.1f} s/round median")

    # The shots come from one leave-teams-out fold's training teams, which the 80/20 splits don't respect
    runs = [] if shots else holdout(samples, targets, timing, p3, pred_t, seeds)
    def mean(key):
        vals = [r[key] for r in runs if r.get(key) is not None]
        return (float(np.mean(vals)), float(np.std(vals))) if vals else (None, None)
    if runs:
        print(f"\n80/20 holdout, {seeds} splits (answered rounds of each 20%)")
        for key in ("site_accuracy", "site_baseline_accuracy", "accuracy", "baseline_accuracy",
                    "timing_accuracy", "timing_baseline_accuracy", "ece"):
            m, sd = mean(key)
            print(f"  {key:<26}{_fmt(m)}" + (f" ±{sd:.3f}" if sd is not None else ""))
    else:
        print("\n80/20 holdout skipped: the shots are only leak-free under leave-teams-out")

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
    if runs:
        (out_dir / "holdout.json").write_text(json.dumps(
            {"meta": {**meta, "seeds": seeds}, "results": {"clef": {"runs": runs}}}, indent=1))
    (out_dir / "lto.json").write_text(json.dumps(
        {"meta": {**meta, "folds": folds}, "results": {"clef": {"cv": cv}}}, indent=1))
    print(f"\nwrote {out_dir}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="ask", choices=("ask", "score", "show"))
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--num-ctx", type=int, default=2048, help="the model variant's num_ctx")
    ap.add_argument("--context", action="store_true", help="add round, score and economy")
    ap.add_argument("--shots", type=int, default=0,
                    help="labelled rounds of the same map from the fold's training teams")
    ap.add_argument("--pick", default="similar", choices=("similar", "random"))
    ap.add_argument("--limit", type=int, default=None, help="ask at most this many rounds")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()

    samples, targets, timing, _ = _load()
    out = _out(args.context, args.shots, args.pick)
    path = out / "answers.jsonl"
    if args.stage == "score":
        run_score(samples, targets, timing, path, args.seeds, args.folds, args.shots)
        return
    states = build_states(samples, targets, args.context, args.shots, args.pick, args.folds)
    qs = questions(context=args.context, shots=args.shots > 0)
    if args.stage == "show":
        i = int(np.random.default_rng(0).permutation(list(states))[0])
        print(json.dumps({"state": states[i][0], "questions": qs}, indent=1, ensure_ascii=False))
        return
    out.mkdir(parents=True, exist_ok=True)
    run_ask(samples, targets, states, qs, path, args.host, args.model, args.num_ctx, args.limit)


if __name__ == "__main__":
    main()
