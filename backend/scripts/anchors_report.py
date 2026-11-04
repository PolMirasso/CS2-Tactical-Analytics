"""Anchors sobre la cabeza de site, con los mismos modelos de los folds de SHAP.

    anchors_report.py [--tau 0.95] [--max-size 5]

Cada ronda con plant la explica el modelo del fold que no vio a su equipo
(data_store/shap/models, de shap_report.py). Las rondas con plant de cada mapa se parten en dos
mitades: con una se busca la regla y con la otra se mide su precisión y su cobertura.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import joblib
import numpy as np
from shap_report import _load

from app.analytics.maps import get_map
from app.ml.anchors import ANY, MAX_SIZE, TAU, Pool, find_anchor, round_predicates
from app.ml.explain import token_zone
from app.ml.model import _to_array
from app.ml.validation import fold_split, fold_teams

OUT = Path("/app/data_store/anchors")
SHAP = Path("/app/data_store/shap")
SITES = ("A", "B")


def _names() -> dict[tuple[str, str], str]:
    out = {}
    for m in {"de_ancient", "de_anubis", "de_cache", "de_dust2", "de_inferno", "de_mirage",
              "de_nuke", "de_overpass", "de_train"}:
        gm = get_map(m)
        if gm is not None:
            out.update({(m, z.id): z.name for z in gm.zones})
    return out


def _label(names, m: str, anchor) -> str:
    return " I ".join(
        f"{'utility' if t == ANY else t} a {names.get((m, z), z)}" for t, z in anchor
    )


def _shap_top_zone(m: str, rec: dict) -> str | None:
    phi = np.array(rec["site"]["phi_b"])
    if not len(phi):
        return None
    toward = phi if rec["site"]["p_b"] > 0.5 else -phi
    g = rec["grenades"][int(np.argmax(toward))]
    z = token_zone(m, g["x"], g["y"], g["z"])
    return z.id if z is not None else None


def run(tau: float, max_size: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    samples, targets, _, _ = _load()
    folds = fold_teams(samples, targets, 5)
    models = [joblib.load(SHAP / "models" / f"fold{k}.joblib") for k in range(len(folds))]

    plant = [i for i, t in enumerate(targets) if t in SITES]
    pidx = {i: j for j, i in enumerate(plant)}
    maps = [str(samples[i]["context"]["map"]) for i in plant]
    y = np.array([int(targets[i] == "B") for i in plant])
    dummy = np.zeros(1)
    pred = np.array([
        [int(m.site_net.predict_proba(_to_array(samples[i]["tokens"]), dummy)[1] > 0.5)
         for i in plant]
        for m in models
    ])
    cand = [round_predicates(maps[j], samples[i]["tokens"]) for j, i in enumerate(plant)]

    # mitad 0 = buscar la regla, mitad 1 = medirla
    rng = np.random.default_rng(0)
    halves: dict[tuple[str, int], np.ndarray] = {}
    for m in sorted(set(maps)):
        js = np.array([j for j in range(len(plant)) if maps[j] == m])
        js = js[rng.permutation(len(js))]
        halves[(m, 0)], halves[(m, 1)] = js[: len(js) // 2], js[len(js) // 2 :]
    eval_pos = {int(j): pos for m in set(maps) for pos, j in enumerate(halves[(m, 1)])}
    pools = {
        (k, m, h): Pool.build([cand[j] for j in js], pred[k, js])
        for k in range(len(models)) for (m, h), js in halves.items()
    }

    shap = {}
    for p in SHAP.glob("fold*.json"):
        for r in json.loads(p.read_text())["rounds"]:
            if "site" in r:
                shap[r["i"]] = r

    names = _names()
    recs = []
    for k, held in enumerate(folds):
        _, test = fold_split(samples, targets, held)
        for i in test:
            if targets[i] not in SITES:
                continue
            j = pidx[i]
            m, target = maps[j], int(pred[k, j])
            rec = {"i": i, "fold": k, "map": m, "target": targets[i],
                   "pred": SITES[target], "n_grenades": len(samples[i]["tokens"])}
            a = find_anchor(pools[(k, m, 0)], cand[j], target, tau=tau, max_size=max_size)
            if a is not None:
                ev = pools[(k, m, 1)]
                rows = ev.rows(a.predicates)
                if j in eval_pos:  # la ronda explicada no cuenta para medir su propia regla
                    rows[eval_pos[j]] = False
                n = int(rows.sum())
                ys = y[halves[(m, 1)]]
                rec.update({
                    "anchor": [list(p) for p in a.predicates],
                    "rule": _label(names, m, a.predicates),
                    "valid": a.valid, "size": len(a.predicates),
                    "search": {"precision": a.precision, "lower": a.lower,
                               "coverage": a.coverage, "n": a.n},
                    "eval": {"n": n, "coverage": n / len(ev.pred),
                             "precision": float(np.mean(ev.pred[rows] == target)) if n else None,
                             "truth": float(np.mean(ys[rows] == target)) if n else None},
                })
                top = _shap_top_zone(m, shap[i]) if i in shap else None
                rec["shap_top_in_anchor"] = (
                    None if top is None else any(z == top for _, z in a.predicates)
                )
            recs.append(rec)
    (OUT / f"rounds_t{tau:g}.json").write_text(json.dumps(recs))
    report(recs, tau)


def _mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def _f(v, pct=False) -> str:
    if v is None:
        return "    —"
    return f"{v:.1%}" if pct else f"{v:.3f}"


def report(recs: list[dict], tau: float) -> dict:
    valid = [r for r in recs if r.get("valid")]
    ev = [r for r in valid if r["eval"]["n"]]
    summary = {
        "tau": tau, "n": len(recs), "valid": len(valid) / len(recs),
        "size": _mean([r["size"] for r in valid]),
        "coverage_search": _mean([r["search"]["coverage"] for r in valid]),
        "coverage_eval": _mean([r["eval"]["coverage"] for r in valid]),
        "precision_eval": _mean([r["eval"]["precision"] for r in ev]),
        "precision_eval_ge_tau": _mean([r["eval"]["precision"] >= tau for r in ev]),
        "truth_eval": _mean([r["eval"]["truth"] for r in ev]),
        "no_eval_rows": 1 - len(ev) / len(valid) if valid else None,
        "shap_top_in_anchor": _mean([r["shap_top_in_anchor"] for r in valid]),
        "accuracy_with_anchor": _mean([r["pred"] == r["target"] for r in valid]),
        "accuracy_without": _mean([r["pred"] == r["target"] for r in recs if not r.get("valid")]),
    }
    print(f"\nAnchors · τ {tau} · {len(recs)} plant rounds")
    print(f"  with an anchor             {_f(summary['valid'], True)}")
    print(f"  mean size                  {_f(summary['size'])}")
    print(f"  coverage search / eval     {_f(summary['coverage_search'], True)} / "
          f"{_f(summary['coverage_eval'], True)}")
    print(f"  precision on eval half     {_f(summary['precision_eval'])} "
          f"(≥ τ in {_f(summary['precision_eval_ge_tau'], True)}, "
          f"no eval rounds {_f(summary['no_eval_rows'], True)})")
    print(f"  agrees with the real site  {_f(summary['truth_eval'])}")
    print(f"  top SHAP callout in anchor {_f(summary['shap_top_in_anchor'], True)}")
    print(f"  model accuracy, with / without anchor {_f(summary['accuracy_with_anchor'])} / "
          f"{_f(summary['accuracy_without'])}")

    by_size = defaultdict(int)
    for r in valid:
        by_size[r["size"]] += 1
    print("  sizes: " + ", ".join(f"{s}: {by_size[s]}" for s in sorted(by_size)))

    per_map, rules = [], {}
    print(f"\n{'map':<13}{'rounds':>7}{'anchor':>8}{'size':>6}{'cov':>7}{'prec':>7}{'truth':>7}")
    for m in sorted({r["map"] for r in recs}):
        rs = [r for r in recs if r["map"] == m]
        vs = [r for r in rs if r.get("valid")]
        row = {
            "map": m, "n": len(rs), "valid": len(vs) / len(rs),
            "size": _mean([r["size"] for r in vs]),
            "coverage": _mean([r["eval"]["coverage"] for r in vs]),
            "precision": _mean([r["eval"]["precision"] for r in vs]),
            "truth": _mean([r["eval"]["truth"] for r in vs]),
        }
        per_map.append(row)
        print(f"{m:<13}{len(rs):>7}{row['valid']:>8.0%}{_f(row['size']):>6}"
              f"{_f(row['coverage'], True):>7}{_f(row['precision']):>7}{_f(row['truth']):>7}")

        groups: dict[tuple, list[dict]] = defaultdict(list)
        for r in vs:
            groups[(r["rule"], r["pred"])].append(r)
        top = sorted(groups.items(), key=lambda kv: -len(kv[1]))[:5]
        rules[m] = [
            {"rule": rule, "site": site, "rounds": len(g),
             "coverage": _mean([r["eval"]["coverage"] for r in g]),
             "precision": _mean([r["eval"]["precision"] for r in g]),
             "truth": _mean([r["eval"]["truth"] for r in g])}
            for (rule, site), g in top
        ]

    print("\nMost used rules per map (rounds it explains · coverage · precision · real site)")
    for m, rows in rules.items():
        print(f"  {m}")
        for r in rows:
            print(f"    SI {r['rule']} → {r['site']}   {r['rounds']} · {_f(r['coverage'], True)}"
                  f" · {_f(r['precision'])} · {_f(r['truth'])}")

    out = {"summary": summary, "per_map": per_map, "rules": rules}
    (OUT / f"summary_t{tau:g}.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tau", type=float, default=TAU)
    ap.add_argument("--max-size", type=int, default=MAX_SIZE)
    ap.add_argument("--report", action="store_true",
                    help="solo vuelve a imprimir a partir de rounds_t<τ>.json")
    args = ap.parse_args()
    if args.report:
        p = OUT / f"rounds_t{args.tau:g}.json"
        if not p.exists():
            sys.exit(f"No {p}")
        report(json.loads(p.read_text()), args.tau)
    else:
        run(args.tau, args.max_size)


if __name__ == "__main__":
    main()
