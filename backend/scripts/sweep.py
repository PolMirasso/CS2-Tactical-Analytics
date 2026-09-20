from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import numpy as np
from sqlalchemy import select

from app.db import _ensure, init_db
from app.domain.models import User
from app.ml.dataset import build_dataset
from app.ml.model import MIN_ROUNDS, SitePredictor, TrainConfig
from app.ml.validation import leave_teams_out

OUT = Path("/app/data_store/sweep")

CONFIGS: dict[str, TrainConfig] = {
    "baseline": TrainConfig(),
    "phi1": TrainConfig(phi_depth=1),
    "rho1": TrainConfig(rho_depth=1),
    "phi1_rho1": TrainConfig(phi_depth=1, rho_depth=1),
    "phi3": TrainConfig(phi_depth=3),
    "rho3": TrainConfig(rho_depth=3),
    "phi3_rho3": TrainConfig(phi_depth=3, rho_depth=3),
    "narrow": TrainConfig(h_phi=16, d_embed=12, h_rho=16),
    "wide": TrainConfig(h_phi=64, d_embed=48, h_rho=64),
    "xwide": TrainConfig(h_phi=128, d_embed=64, h_rho=128),
    "tanh": TrainConfig(activation="tanh"),
    "leaky_relu": TrainConfig(activation="leaky_relu"),
    "pool_mean": TrainConfig(pooling="mean"),
    "pool_sum": TrainConfig(pooling="sum"),
    "lr_1e-3": TrainConfig(lr=1e-3),
    "lr_1e-2": TrainConfig(lr=1e-2),
    "wd_0": TrainConfig(weight_decay=0.0),
    "wd_1e-3": TrainConfig(weight_decay=1e-3),
    "intent_off": TrainConfig(use_intent=False),
}

# Training is a Python loop over rounds, so it does not thread; parallelism is
# per-process. Workers are forked AFTER the dataset is built, so they inherit it
# copy-on-write instead of pickling several hundred MB each.
_POOL: dict = {}


def _fit(task: tuple) -> tuple:
    """One task in a forked worker: ``(key, kind, payload)``.

    A task carries a LIST of configs so that an ablation deep-copies the pool
    once and then reuses it for every seed — otherwise each seed would hold its
    own copy of the whole dataset.
    """
    key, kind, payload = task
    samples = _POOL["samples"]
    if payload.get("ablation"):
        samples = ablate(samples, payload["ablation"])
    targets, timing, meta = _POOL["targets"], _POOL["timing"], _POOL["meta"]
    if kind == "lto":
        return key, leave_teams_out(samples, targets, timing,
                                    n_folds=payload["folds"], config=payload["configs"][0])
    return key, [_row(SitePredictor.train(samples, targets, meta, timing, config=c))
                 for c in payload["configs"]]


def _map_tasks(tasks: list[tuple], jobs: int) -> dict:
    """Run tasks, returning {key: result}. jobs<=1 stays in-process."""
    if jobs <= 1:
        return dict(_fit(t) for t in tasks)
    with ProcessPoolExecutor(max_workers=jobs, mp_context=get_context("fork")) as ex:
        return dict(ex.map(_fit, tasks))


def _load() -> tuple[list[dict], list[str], list, dict]:
    init_db()
    with _ensure()() as session:
        users = list(session.scalars(select(User).order_by(User.id)))
        user = next((u for u in users if u.is_admin), users[0] if users else None)
        if user is None:
            sys.exit("No users in the DB — nothing to measure.")
        return build_dataset(session, user)


def ablate(samples: list[dict], kind: str) -> list[dict]:
    """Return a copy of ``samples`` with one signal removed or leaked."""
    out = copy.deepcopy(samples)
    rng = np.random.default_rng(0)

    if kind == "none":
        return out

    if kind == "no_position":
        # x01/y01 are token slots 4 and 5; 0.5 is what round_tokens already
        # writes for an unknown location (centre of the radar)
        for s in out:
            for tok in s["tokens"]:
                tok[4] = tok[5] = 0.5
        return out

    if kind == "shuffled_position":
        # Permute (x,y) across every token OF THE SAME MAP, so the marginal
        # distribution of positions is preserved exactly and only the
        # round->position pairing is destroyed. Rounds hold different numbers of
        # grenades, so permuting whole rounds would leave the surplus tokens
        # sitting on their true position and dilute the control.
        by_map: dict[str, list[list[float]]] = {}
        for s in out:
            by_map.setdefault(str(s["context"].get("map")), []).extend(s["tokens"])
        for toks in by_map.values():
            pos = [(t[4], t[5]) for t in toks]
            for tok, k in zip(toks, rng.permutation(len(pos)), strict=True):
                tok[4], tok[5] = pos[k]
        return out

    if kind == "no_map_onehot":
        # map one-hot occupies the tail of the token (after the 4 util flags +
        # x01,y01,t01,z_lvl)
        for s in out:
            for tok in s["tokens"]:
                for j in range(8, len(tok)):
                    tok[j] = 0.0
        return out

    if kind == "no_time":
        for s in out:
            for tok in s["tokens"]:
                tok[6] = 0.0
        return out

    if kind == "no_z_level":
        for s in out:
            for tok in s["tokens"]:
                tok[7] = 0.5
        return out

    raise ValueError(f"unknown ablation {kind!r}")


ABLATIONS = [
    ("none", "cap (referencia)"),
    ("no_position", "sense posicio (x,y neutre = centre del radar)"),
    ("shuffled_position", "posicio barrejada entre rondes del mateix mapa"),
    ("no_map_onehot", "sense one-hot de mapa al token"),
    ("no_time", "sense temps (t01 = 0)"),
    ("no_z_level", "sense alcada (z_lvl neutre)"),
]


def _row(p: SitePredictor) -> dict:
    return {
        "trained": p.trained,
        "accuracy": p.accuracy,
        "site_accuracy": p.site_accuracy,
        "timing_accuracy": p.timing_accuracy,
        "timing_baseline_accuracy": p.timing_baseline_accuracy,
        "baseline_accuracy": p.baseline_accuracy,
        "site_baseline_accuracy": p.site_baseline_accuracy,
        "ece": p.ece,
        "ece_uncalibrated": p.ece_uncalibrated,
        "layers": p.params.get("gate"),
        "per_map": p.per_map,
    }


def _agg(rows: list[dict], key: str) -> tuple[float | None, float | None]:
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return None, None
    return float(np.mean(vals)), float(np.std(vals))


def _fmt(v: float | None, sd: float | None = None) -> str:
    if v is None:
        return "     —"
    return f"{v:.3f}" + (f"±{sd:.3f}" if sd is not None else "")


def run_holdout(cfgs: dict, seeds: int, jobs: int,
                ablation_of: dict[str, str] | None = None) -> dict:
    """80/20 holdout for each config, repeated over `seeds` splits.

    Normally one task per (config, seed), so the pool load-balances. An ablation
    row instead gets a single task holding every seed, so the mutilated copy of
    the pool is built once per row and not once per seed (see `_fit`).
    """
    abl = ablation_of or {}
    tasks = []
    for name, base in cfgs.items():
        seeded = [TrainConfig(**{**base.__dict__, "seed": s}) for s in range(seeds)]
        if name in abl:
            tasks.append((name, "holdout", {"ablation": abl[name], "configs": seeded}))
        else:
            tasks += [((name, s), "holdout", {"configs": [c]})
                      for s, c in enumerate(seeded)]

    t0 = time.time()
    done = _map_tasks(tasks, jobs)
    elapsed = round(time.time() - t0, 1)

    out = {}
    for name, base in cfgs.items():
        runs = done[name] if name in abl else [done[(name, s)][0] for s in range(seeds)]
        out[name] = {"label": base.label(), "runs": runs, "seconds": elapsed}
        acc, acc_sd = _agg(runs, "accuracy")
        site, site_sd = _agg(runs, "site_accuracy")
        tim, tim_sd = _agg(runs, "timing_accuracy")
        base_acc, _ = _agg(runs, "baseline_accuracy")
        site_base, _ = _agg(runs, "site_baseline_accuracy")
        print(
            f"  {name:<18}{_fmt(site, site_sd):>14}{_fmt(acc, acc_sd):>14}"
            f"{_fmt(tim, tim_sd):>14}{_fmt(site_base):>8}{_fmt(base_acc):>8}",
            flush=True,
        )
    print(f"  ({len(tasks)} runs in {elapsed:.0f}s on {jobs} workers)", flush=True)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage", default="configs",
        choices=("configs", "ablations", "lto", "lto_ablations", "curve"),
    )
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--folds", type=int, default=5)
    ap.add_argument("--only", default="", help="comma-separated config names (configs/lto stages)")
    ap.add_argument("--seed", type=int, default=0, help="net/init seed (lto stage)")
    ap.add_argument("--fracs", default="0.25,0.5,0.75,1.0", help="train fractions (curve)")
    ap.add_argument("--out", default="lto", help="output json basename (lto stage)")
    ap.add_argument("--jobs", type=int, default=1, help="parallel worker processes")
    args = ap.parse_args()

    # One BLAS thread per worker: the training loop is Python-bound, so threads
    # inside a worker only fight the other workers for cores.
    if args.jobs > 1:
        for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            os.environ[var] = "1"

    samples, targets, timing, meta = _load()
    _POOL.update(samples=samples, targets=targets, timing=timing, meta=meta)
    maps = sorted({str(s["context"].get("map")) for s in samples})
    print(
        f"pool: {len(samples)} rounds · {meta.get('n_teams')} teams · "
        f"{len(maps)} maps ({', '.join(maps)})"
    )
    if len(samples) < MIN_ROUNDS:
        sys.exit(f"Not enough rounds ({len(samples)} < {MIN_ROUNDS}).")
    OUT.mkdir(parents=True, exist_ok=True)

    if args.stage == "configs":
        print(f"\n80/20 holdout, mean±sd over {args.seeds} splits")
        print(f"  {'config':<18}{'site':>14}{'3-class':>14}{'timing':>14}"
              f"{'sbase':>8}{'base':>8}{'time':>8}")
        only = {c for c in args.only.split(",") if c}
        chosen = {k: v for k, v in CONFIGS.items() if not only or k in only}
        res = run_holdout(chosen, args.seeds, args.jobs)
        (OUT / "configs.json").write_text(json.dumps({"meta": {
            "n_rounds": len(samples), "n_teams": meta.get("n_teams"), "maps": maps,
            "seeds": args.seeds}, "results": res}, indent=1))

    elif args.stage == "ablations":
        print(f"\nAblations at the default config, 80/20 holdout, mean±sd over {args.seeds} splits")
        print(f"  {'ablation':<18}{'site':>14}{'3-class':>14}{'timing':>14}"
              f"{'sbase':>8}{'base':>8}{'time':>8}")
        res = run_holdout({k: TrainConfig() for k, _ in ABLATIONS}, args.seeds,
                          args.jobs, ablation_of={k: k for k, _ in ABLATIONS})
        for kind, desc in ABLATIONS:
            res[kind]["description"] = desc
        (OUT / "ablations.json").write_text(json.dumps({"meta": {
            "n_rounds": len(samples), "n_teams": meta.get("n_teams"), "maps": maps,
            "seeds": args.seeds}, "results": res}, indent=1))

    elif args.stage == "curve":
        # The 20% holdout is drawn first and stays fixed, so only the amount of
        # TRAINING data changes.
        fracs = [float(x) for x in args.fracs.split(",")]
        print(f"\nLearning curve, holdout 80/20 fixed, mean±sd over {args.seeds} splits")
        print(f"  {'train_frac':<12}{'~rondes':>9}{'site':>14}{'3-class':>14}{'timing':>14}")
        res = {}
        n_keep = sum(1 for t in targets if t in ("A", "B", "NoPlant"))
        t0 = time.time()
        done = _map_tasks(
            [((f, sd), "holdout", {"configs": [TrainConfig(seed=sd, train_frac=f)]})
             for f in fracs for sd in range(args.seeds)],
            args.jobs,
        )
        elapsed = round(time.time() - t0, 1)
        for f in fracs:
            runs = [done[(f, sd)][0] for sd in range(args.seeds)]
            n_tr = round(n_keep * 0.8 * f)
            res[str(f)] = {"frac": f, "n_train": n_tr, "runs": runs,
                           "seconds": elapsed}
            site, ssd = _agg(runs, "site_accuracy")
            acc, asd = _agg(runs, "accuracy")
            tim, tsd = _agg(runs, "timing_accuracy")
            print(
                f"  {f:<12}{n_tr:>9}{_fmt(site, ssd):>14}{_fmt(acc, asd):>14}{_fmt(tim, tsd):>14}",
                flush=True,
            )
        (OUT / "curve.json").write_text(json.dumps({"meta": {
            "n_rounds": len(samples), "n_teams": meta.get("n_teams"), "maps": maps,
            "seeds": args.seeds}, "results": res}, indent=1))

    elif args.stage == "lto_ablations":
        print(f"\nAblations under leave-teams-out, {args.folds} folds")
        print(
            f"  {'ablation':<18}{'site':>10}{'3-class':>10}{'sbase':>10}{'base':>10}"
            f"{'rounds':>8}{'plant':>7}{'time':>8}"
        )
        res = {}
        t0 = time.time()
        done = _map_tasks(
            [(kind, "lto", {"ablation": kind, "folds": args.folds,
                            "configs": [TrainConfig()]}) for kind, _ in ABLATIONS],
            args.jobs,
        )
        elapsed = round(time.time() - t0, 1)
        for kind, desc in ABLATIONS:
            cv = done[kind]
            res[kind] = {"description": desc, "cv": cv, "seconds": elapsed}
            print(
                f"  {kind:<18}{_fmt(cv['site_accuracy']):>10}{_fmt(cv['accuracy']):>10}"
                f"{_fmt(cv['site_baseline_accuracy']):>10}"
                f"{_fmt(cv['baseline_accuracy']):>10}{cv['n_rounds']:>8}{cv['n_plant']:>7}",
                flush=True,
            )
        (OUT / "lto_ablations.json").write_text(json.dumps({"meta": {
            "n_rounds": len(samples), "n_teams": meta.get("n_teams"), "maps": maps,
            "folds": args.folds}, "results": res}, indent=1))

    else:
        names = [n for n in (args.only.split(",") if args.only else CONFIGS) if n in CONFIGS]
        print(f"\nLeave-teams-out, {args.folds} folds (test teams unseen in training)")
        print(
            f"  {'config':<18}{'site':>10}{'3-class':>10}{'sbase':>10}{'base':>10}"
            f"{'rounds':>8}{'plant':>7}{'time':>8}"
        )
        res = {}
        cfgs = {n: TrainConfig(**{**CONFIGS[n].__dict__, "seed": args.seed}) for n in names}
        t0 = time.time()
        done = _map_tasks(
            [(n, "lto", {"folds": args.folds, "configs": [c]}) for n, c in cfgs.items()],
            args.jobs,
        )
        elapsed = round(time.time() - t0, 1)
        for name in names:
            cfg, cv = cfgs[name], done[name]
            res[name] = {"label": cfg.label(), "seed": args.seed, "cv": cv,
                         "seconds": elapsed}
            print(
                f"  {name:<18}{_fmt(cv['site_accuracy']):>10}{_fmt(cv['accuracy']):>10}"
                f"{_fmt(cv['site_baseline_accuracy']):>10}"
                f"{_fmt(cv['baseline_accuracy']):>10}{cv['n_rounds']:>8}{cv['n_plant']:>7}",
                flush=True,
            )
        (OUT / f"{args.out}.json").write_text(json.dumps({"meta": {
            "n_rounds": len(samples), "n_teams": meta.get("n_teams"), "maps": maps,
            "folds": args.folds, "seed": args.seed}, "results": res}, indent=1))

    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
