from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path

import joblib
import numpy as np
from shap_report import _deletion, _load

from app.ml.explain import shapley, site_value, token_zone
from app.ml.lime import NUM_SAMPLES, kernel_shap, lime_fit, sample_masks
from app.ml.validation import fold_split, fold_teams

OUT = Path("/app/data_store/lime")
SHAP = Path("/app/data_store/shap")
SITES = ("A", "B")
K_MAX = 5
MIN_ZONE = 15
_POOL: dict = {}


# explicar

def _explain_round(model, tokens, i: int, target: str, rng) -> dict:
    n = len(tokens)
    value = site_value(model, tokens)

    t0 = time.perf_counter()
    masks = sample_masks(n, NUM_SAMPLES, np.random.default_rng((0, i)))
    y = value(masks)[:, 1]
    fit = lime_fit(masks, y)
    t_lime = time.perf_counter() - t0

    v_empty = float(value(np.zeros((1, n), dtype=bool))[0, 1])
    ks = kernel_shap(masks, y, v_empty, float(y[0]))
    masks1 = sample_masks(n, NUM_SAMPLES, np.random.default_rng((1, i)))
    fit1 = lime_fit(masks1, value(masks1)[:, 1])

    t0 = time.perf_counter()
    sh = shapley(value, n)
    t_shap = time.perf_counter() - t0

    p_b = float(y[0])
    pred, yb = int(p_b > 0.5), int(target == "B")
    return {
        "n": n, "p_b": p_b, "base_b": v_empty,
        "lime": {"coef": fit.coef.tolist(), "intercept": fit.intercept, "score": fit.score,
                 "local_pred": fit.local_pred},
        "lime_seed1": fit1.coef.tolist(),
        "kshap": ks.tolist(),
        "shap_phi": sh.phi[:, 1].tolist(),
        "time": {"lime": t_lime, "shap": t_shap, "shap_exact": sh.exact},
        "deletion": _deletion(value, n, fit.coef if pred else -fit.coef, pred, yb, rng),
    }


def _fold(k: int) -> tuple[int, int, float]:
    samples, targets, held = _POOL["samples"], _POOL["targets"], _POOL["folds"][k]
    t0 = time.time()
    model = joblib.load(SHAP / "models" / f"fold{k}.joblib")
    _, test = fold_split(samples, targets, held)
    rng = np.random.default_rng(k)
    recs = []
    for i in test:
        if targets[i] not in SITES or not len(samples[i]["tokens"]):
            continue
        rec = _explain_round(model, samples[i]["tokens"], i, targets[i], rng)
        recs.append({"i": i, "fold": k, "map": samples[i]["context"].get("map"),
                     "target": targets[i], **rec})
    (OUT / f"fold{k}.json").write_text(json.dumps({"held": held, "rounds": recs}))
    return k, len(recs), time.time() - t0


def stage_explain(jobs: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    samples, targets, _, _ = _load()
    folds = fold_teams(samples, targets, 5)
    _POOL.update(samples=samples, targets=targets, folds=folds)
    with ProcessPoolExecutor(max_workers=jobs, mp_context=get_context("fork")) as ex:
        for k, n, dt in ex.map(_fold, range(len(folds))):
            print(f"fold {k}: {n} rounds in {dt:.0f}s", flush=True)


# informe

def _rounds(path: Path) -> list[dict]:
    out = []
    for p in sorted(path.glob("fold*.json")):
        out += json.loads(p.read_text())["rounds"]
    return out


def _joined() -> list[dict]:
    shap = {r["i"]: r for r in _rounds(SHAP) if "site" in r}
    rows = []
    for r in _rounds(OUT):
        s = shap[r["i"]]
        assert s["n"] == r["n"] and abs(s["site"]["p_b"] - r["p_b"]) < 1e-9, r["i"]
        rows.append({**r, "grenades": s["grenades"], "phi": np.array(s["site"]["phi_b"]),
                     "coef": np.array(r["lime"]["coef"]), "coef1": np.array(r["lime_seed1"]),
                     "ks": np.array(r["kshap"]), "shap_deletion": s["site"]["deletion"]})
    return rows


def _spearman(a: np.ndarray, b: np.ndarray) -> float | None:
    from scipy.stats import spearmanr

    if len(a) < 3 or np.ptp(a) == 0 or np.ptp(b) == 0:
        return None
    return float(spearmanr(a, b).statistic)


def _toward(r: dict, v: np.ndarray) -> np.ndarray:
    return v if r["p_b"] > 0.5 else -v


def _agreement(rows: list[dict], key: str, ref: str = "phi") -> dict:
    """Coincidencia de ``key`` con ``ref``: rango, granada principal, top 3 y signo."""
    rho, top1, top3, chance, sign = [], [], [], [], []
    for r in rows:
        a, b = _toward(r, r[ref]), _toward(r, r[key])
        s = _spearman(a, b)
        if s is not None:
            rho.append(s)
        if r["n"] >= 2:
            top1.append(np.argmax(a) == np.argmax(b))
            chance.append(1 / r["n"])
        if r["n"] >= 4:
            top3.append(len(set(np.argsort(-a)[:3]) & set(np.argsort(-b)[:3])) / 3)
        w = np.abs(r[ref])
        if w.sum() > 0:
            sign.append(w @ (np.sign(r[ref]) == np.sign(r[key])) / w.sum())
    return {"spearman": float(np.mean(rho)), "spearman_median": float(np.median(rho)),
            "top1": float(np.mean(top1)), "top1_chance": float(np.mean(chance)),
            "top3": float(np.mean(top3)), "sign": float(np.mean(sign)), "n": len(rows)}


def _deletion_table(rows: list[dict]) -> dict:
    out: dict[str, list] = {"remove": [], "keep": []}
    print(f"\nFaithfulness (rounds with more than k grenades)\n{'':<9}{'k':<3}{'rounds':>8}"
          f"{'full':>8}{'SHAP':>8}{'LIME':>8}{'rand':>8}{'flip S':>8}{'flip L':>8}{'flip r':>8}")
    for mode in ("remove", "keep"):
        for k in range(1, K_MAX + 1):
            rs = [r for r in rows if r["deletion"][mode][k - 1] is not None]
            y = np.array([int(r["target"] == "B") for r in rs])
            pred = np.array([int(r["p_b"] > 0.5) for r in rs])
            lim = np.array([r["deletion"][mode][k - 1]["shap"] for r in rs])
            shp = np.array([r["shap_deletion"][mode][k - 1]["shap"] for r in rs])
            rnd = [r["shap_deletion"][mode][k - 1] for r in rs]
            line = {
                "k": k, "n": len(rs), "full": float(np.mean(pred == y)),
                "shap_acc": float(np.mean(shp == y)), "lime_acc": float(np.mean(lim == y)),
                "rand_acc": float(np.mean([x["rand_correct"] for x in rnd])),
                "shap_flip": float(np.mean(shp != pred)), "lime_flip": float(np.mean(lim != pred)),
                "rand_flip": float(1 - np.mean([x["rand_same"] for x in rnd])),
            }
            out[mode].append(line)
            print(f"{mode:<9}{k:<3}{len(rs):>8}{line['full']:>8.3f}{line['shap_acc']:>8.3f}"
                  f"{line['lime_acc']:>8.3f}{line['rand_acc']:>8.3f}{line['shap_flip']:>8.3f}"
                  f"{line['lime_flip']:>8.3f}{line['rand_flip']:>8.3f}")
    return out


def _type_time(rows: list[dict]) -> dict:
    from app.ml.features import _UTILS

    bins = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 1e9)]
    out: dict = {"types": {}, "times": []}
    for key in ("phi", "coef"):
        by_type, by_time = defaultdict(list), defaultdict(list)
        for r in rows:
            for g, v in zip(r["grenades"], r[key], strict=True):
                by_type[g["type"]].append(abs(v))
                by_time[next(b for b in bins if b[0] <= g["t"] < b[1])].append(abs(v))
        tot = sum(sum(v) for v in by_type.values())
        for t in _UTILS:
            out["types"].setdefault(t, {})[key] = sum(by_type[t]) / tot
        for j, b in enumerate(bins):
            if len(out["times"]) <= j:
                out["times"].append({"bin": f"{b[0]}-{b[1]} s" if b[1] < 1e9 else f">{b[0]} s",
                                     "n": len(by_time[b])})
            out["times"][j][key] = float(np.mean(by_time[b]))
    print(f"\n{'type':<10}{'% Σ|φ| SHAP':>13}{'% Σ|c| LIME':>13}")
    for t, v in out["types"].items():
        print(f"{t:<10}{v['phi']:>13.1%}{v['coef']:>13.1%}")
    print(f"\n{'throw time':<12}{'grenades':>10}{'|φ| SHAP':>10}{'|c| LIME':>10}")
    for b in out["times"]:
        print(f"{b['bin']:<12}{b['n']:>10}{b['phi']:>10.3f}{b['coef']:>10.3f}")
    first, last = out["times"][0], out["times"][-1]
    out["late_ratio"] = {k: last[k] / first[k] for k in ("phi", "coef")}
    lr = out["late_ratio"]
    print(f"late / early: SHAP ×{lr['phi']:.1f}, LIME ×{lr['coef']:.1f}")
    return out


def _zones(rows: list[dict]) -> dict:
    acc: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        for g, phi, c in zip(r["grenades"], r["phi"], r["coef"], strict=True):
            z = token_zone(r["map"], g["x"], g["y"], g["z"])
            if z is None:
                continue
            row = acc[r["map"]].setdefault(z.id, {"zone": z.id, "name": z.name, "phi": [], "c": []})
            row["phi"].append(phi)
            row["c"].append(c)
    out, allp, allc = {}, [], []
    print(f"\nCallouts (≥{MIN_ZONE} grenades): mean φ (SHAP) vs mean coef (LIME) toward B")
    for m in sorted(acc):
        zs = [{"zone": v["zone"], "name": v["name"], "n": len(v["phi"]),
               "phi": float(np.mean(v["phi"])), "coef": float(np.mean(v["c"]))}
              for v in acc[m].values() if len(v["phi"]) >= MIN_ZONE]
        p, c = np.array([z["phi"] for z in zs]), np.array([z["coef"] for z in zs])
        allp += p.tolist()
        allc += c.tolist()
        same = {}
        for side, sgn in (("A", 1), ("B", -1)):
            ts = {z["zone"] for z in sorted(zs, key=lambda z: sgn * z["phi"])[:3]}
            tl = {z["zone"] for z in sorted(zs, key=lambda z: sgn * z["coef"])[:3]}
            same[side] = len(ts & tl)
        r_m = float(np.corrcoef(p, c)[0, 1])
        top_l = {side: [z["name"] for z in sorted(zs, key=lambda z: sgn * z["coef"])[:3]]
                 for side, sgn in (("A", 1), ("B", -1))}
        out[m] = {"zones": zs, "pearson": r_m, "same_top3": same, "lime_top3": top_l}
        print(f"  {m:<12} r={r_m:.3f}  same top-3 A {same['A']}/3 B {same['B']}/3"
              f"  LIME A: {', '.join(top_l['A'])} | B: {', '.join(top_l['B'])}")
    r_all = float(np.corrcoef(allp, allc)[0, 1])
    print(f"  all callouts r={r_all:.3f} ({len(allp)} callouts)")
    return {"per_map": out, "pearson": r_all, "n": len(allp)}


# figuras

_SHAP_C, _LIME_C, _RAND_C = "#2a78d6", "#1baf7a", "#eb6834"
_INK, _INK2, _GRID = "#0b0b0b", "#52514e", "#e6e5e1"


def plot_deletion(deletion: dict, figs: Path) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), dpi=150, sharey=True)
    titles = {"remove": "Treient k granades", "keep": "Deixant només k granades"}
    series = (("shap_acc", _SHAP_C, "o", "les k amb més pes SHAP"),
              ("lime_acc", _LIME_C, "s", "les k amb més pes LIME"),
              ("rand_acc", _RAND_C, "^", "k a l'atzar"))
    for ax, mode in zip(axes, ("remove", "keep"), strict=True):
        rows = deletion[mode]
        ks = [r["k"] for r in rows]
        for key, color, marker, label in series:
            ys = [r[key] for r in rows]
            ax.plot(ks, ys, color=color, lw=2, marker=marker, ms=5, label=label)
            ax.annotate(f"{ys[-1]:.2f}", (ks[-1], ys[-1]), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8, color=_INK2)
        ax.axhline(0.5, color=_INK2, lw=0.8, ls=":")
        ax.set_title(titles[mode], loc="left", fontsize=10, color=_INK)
        ax.set_xlabel("k", color=_INK2)
        ax.set_xticks(ks)
        ax.set_xlim(0.7, K_MAX + 0.6)
        ax.grid(axis="y", color=_GRID, lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("encert A/B", color=_INK2)
    axes[0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(figs / "deletion.png", facecolor="white")
    plt.close(fig)


def plot_example(r: dict, figs: Path, name: str) -> None:
    """La misma ronda explicada con SHAP y con LIME."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from shap_report import _A, _B, _MARKERS, _NAMES, _radar

    from app.ml.explain import token_radar_px
    from app.ml.features import _UTILS

    m = r["map"]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6.6), dpi=150)
    scale = 600 / max(np.abs(r["phi"]).max(), np.abs(r["coef"]).max(), 1e-9)
    for ax, key, title in ((axes[0], "phi", "SHAP (φ)"), (axes[1], "coef", "LIME (coeficient)")):
        _radar(ax, m)
        v = r[key]
        top = int(np.argmax(_toward(r, v)))
        for j, (g, f) in enumerate(zip(r["grenades"], v, strict=True)):
            gx, gy = token_radar_px(m, g["x"], g["y"], g["z"])
            ax.scatter(gx, gy, s=30 + scale * abs(f), marker=_MARKERS[g["type"]],
                       c=_B if f > 0 else _A, edgecolors=_INK if j == top else "white",
                       linewidths=2.2 if j == top else 1.5, zorder=3)
            ax.annotate(f"{f:+.2f} · {g['t']:.0f}s", (gx, gy), xytext=(8, -8),
                        textcoords="offset points", fontsize=7, color=_INK,
                        bbox={"fc": "white", "ec": "none", "alpha": 0.75, "pad": 0.6})
        ax.set_title(title, loc="left", fontsize=10, color=_INK)
    handles = [Line2D([], [], marker=_MARKERS[t], ls="", color=_INK2, label=_NAMES[t])
               for t in _UTILS]
    handles += [Line2D([], [], marker="o", ls="", color=c, label=lab)
                for c, lab in ((_A, "empeny cap a A"), (_B, "empeny cap a B"))]
    handles.append(Line2D([], [], marker="o", ls="", mfc="white", mec=_INK, mew=2.2,
                          label="la de més pes"))
    axes[0].legend(handles=handles, loc="lower left", fontsize=7, framealpha=0.85)
    site = "B" if r["p_b"] > 0.5 else "A"
    p = r["p_b"] if site == "B" else 1 - r["p_b"]
    fig.suptitle(f"{m} · ronda {r['i']} · real {r['target']} · P({site}) = {p:.2f}"
                 f" · R² de LIME {r['lime']['score']:.2f}", x=0.01, ha="left", fontsize=10,
                 color=_INK)
    fig.tight_layout()
    fig.savefig(figs / f"{name}.png", facecolor="white")
    plt.close(fig)


def stage_report() -> dict:
    rows = _joined()
    if not rows:
        sys.exit(f"No fold*.json in {OUT}: run --stage explain first.")
    acc = np.mean([(r["p_b"] > 0.5) == (r["target"] == "B") for r in rows])
    check = max(float(np.abs(np.array(r["shap_phi"]) - r["phi"]).max()) for r in rows)
    print(f"Site head · {len(rows)} plant rounds with utility · accuracy {acc:.4f}"
          f" · recomputed SHAP vs shap/ {check:.1e}")

    agree = {
        "lime_vs_shap": _agreement(rows, "coef"),
        "kshap_vs_shap": _agreement(rows, "ks"),
        "lime_seed0_vs_seed1": _agreement(rows, "coef1", ref="coef"),
        "kshap_vs_lime": _agreement(rows, "coef", ref="ks"),
    }
    print(f"\n{'':<22}{'spearman':>9}{'top-1':>8}{'chance':>8}{'top-3':>8}{'sign':>8}")
    for k, v in agree.items():
        print(f"{k:<22}{v['spearman']:>9.3f}{v['top1']:>8.3f}{v['top1_chance']:>8.3f}"
              f"{v['top3']:>8.3f}{v['sign']:>8.3f}")

    ks_err = np.concatenate([r["ks"] - r["phi"] for r in rows])
    gap = np.array([abs(r["coef"].sum() - (r["p_b"] - r["base_b"])) for r in rows])
    scale = np.array([np.abs(r["coef"]).sum() / np.abs(r["phi"]).sum() for r in rows
                      if np.abs(r["phi"]).sum() > 0])
    pooled = float(np.corrcoef(np.concatenate([r["phi"] for r in rows]),
                               np.concatenate([r["coef"] for r in rows]))[0, 1])
    r2 = np.array([r["lime"]["score"] for r in rows])
    ok = np.array([(r["p_b"] > 0.5) == (r["target"] == "B") for r in rows])
    fidelity = {
        "kshap_mae": float(np.abs(ks_err).mean()), "kshap_max": float(np.abs(ks_err).max()),
        "lime_sum_gap_mean": float(gap.mean()), "lime_scale_median": float(np.median(scale)),
        "pooled_pearson": pooled, "r2_mean": float(r2.mean()), "r2_median": float(np.median(r2)),
        "r2_correct": float(r2[ok].mean()), "r2_wrong": float(r2[~ok].mean()),
        "local_pred_mae": float(np.mean([abs(r["lime"]["local_pred"] - r["p_b"]) for r in rows])),
        "local_pred_flips": float(np.mean([(r["lime"]["local_pred"] > 0.5) != (r["p_b"] > 0.5)
                                           for r in rows])),
    }
    print(f"\nKernelSHAP vs exact: MAE {fidelity['kshap_mae']:.4f},"
          f" max {fidelity['kshap_max']:.3f}")
    print(f"LIME: |Σcoef − (p − base)| mean {fidelity['lime_sum_gap_mean']:.3f}; "
          f"Σ|coef| / Σ|φ| median {fidelity['lime_scale_median']:.2f}; pooled r {pooled:.3f}")
    print(f"LIME R² mean {fidelity['r2_mean']:.3f} (median {fidelity['r2_median']:.3f}); "
          f"correct {fidelity['r2_correct']:.3f} / wrong {fidelity['r2_wrong']:.3f}")
    print(f"LIME local_pred − p: MAE {fidelity['local_pred_mae']:.3f}, "
          f"other side of 0.5 in {fidelity['local_pred_flips']:.1%}")

    per_map = []
    print(f"\n{'map':<13}{'rounds':>7}{'R²':>7}{'spearman':>9}{'top-1':>7}")
    for m in sorted({r["map"] for r in rows}):
        rs = [r for r in rows if r["map"] == m]
        a = _agreement(rs, "coef")
        row = {"map": m, "n": len(rs), "r2": float(np.mean([r["lime"]["score"] for r in rs])),
               "spearman": a["spearman"], "top1": a["top1"]}
        per_map.append(row)
        print(f"{m:<13}{len(rs):>7}{row['r2']:>7.3f}{row['spearman']:>9.3f}{row['top1']:>7.3f}")

    t_l = np.array([r["time"]["lime"] for r in rows])
    t_s = np.array([r["time"]["shap"] for r in rows])
    ns = np.array([r["n"] for r in rows])
    cost = {"lime_mean": float(t_l.mean()), "shap_mean": float(t_s.mean()),
            "lime_total": float(t_l.sum()), "shap_total": float(t_s.sum()), "by_n": []}
    print(f"\nCost per round: LIME {t_l.mean() * 1e3:.0f} ms, exact SHAP {t_s.mean() * 1e3:.0f} ms"
          f" (totals {t_l.sum():.0f} s / {t_s.sum():.0f} s)")
    for lo, hi in ((1, 10), (11, 15), (16, 20), (21, 99)):
        sel = (ns >= lo) & (ns <= hi)
        if sel.any():
            cost["by_n"].append({"n": f"{lo}-{hi}", "rounds": int(sel.sum()),
                                 "lime": float(t_l[sel].mean()), "shap": float(t_s[sel].mean())})
            print(f"  n {lo}-{hi}: {sel.sum()} rounds, LIME {t_l[sel].mean() * 1e3:.0f} ms,"
                  f" SHAP {t_s[sel].mean() * 1e3:.0f} ms")

    conf = np.array([max(r["p_b"], 1 - r["p_b"]) for r in rows])
    fidelity["r2_by_conf"] = []
    for lo, hi in ((0.5, 0.7), (0.7, 0.9), (0.9, 0.97), (0.97, 1.01)):
        sel = (conf >= lo) & (conf < hi)
        fidelity["r2_by_conf"].append({"conf": f"{lo}-{min(hi, 1.0)}", "rounds": int(sel.sum()),
                                       "r2": float(r2[sel].mean())})
    print("LIME R² by model confidence: " + ", ".join(
        f"{b['conf']} {b['r2']:.3f} ({b['rounds']})" for b in fidelity["r2_by_conf"]))

    summary = {
        "n": len(rows), "accuracy": float(acc), "agreement": agree, "fidelity": fidelity,
        "disagreement": _disagreement(rows), "per_map": per_map, "cost": cost,
        "deletion": _deletion_table(rows), "type_time": _type_time(rows), "zones": _zones(rows),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, ensure_ascii=False))

    import matplotlib

    matplotlib.use("Agg")
    figs = OUT / "figures"
    figs.mkdir(exist_ok=True)
    plot_deletion(summary["deletion"], figs)
    ex = _shap_example(rows, "de_dust2")
    if ex is not None:
        plot_example(ex, figs, "example_de_dust2")
    print(f"\n→ {OUT / 'summary.json'} and {figs}/")
    return summary


def _disagreement(rows: list[dict]) -> dict:
    """Rondas en las que LIME y SHAP no eligen la misma granada principal."""
    dis, agr = [], []
    for r in rows:
        if r["n"] < 2:
            continue
        s, lm = _toward(r, r["phi"]), _toward(r, r["coef"])
        order = np.argsort(-s)
        i, j = int(order[0]), int(np.argmax(lm))
        gap = (s[order[0]] - s[order[1]]) / max(abs(s[order[0]]), 1e-9)
        rank = int(np.where(order == j)[0][0]) + 1
        (agr if i == j else dis).append({"gap": gap, "rank": rank,
                                         "later": r["grenades"][j]["t"] > r["grenades"][i]["t"]})
    out = {
        "rounds": len(dis), "of": len(dis) + len(agr),
        "lime_is_shap_2nd": float(np.mean([d["rank"] == 2 for d in dis])),
        "lime_in_shap_top3": float(np.mean([d["rank"] <= 3 for d in dis])),
        "gap_median_disagree": float(np.median([d["gap"] for d in dis])),
        "gap_median_agree": float(np.median([d["gap"] for d in agr])),
        "lime_pick_later": float(np.mean([d["later"] for d in dis])),
    }
    print(f"\nTop grenade differs in {out['rounds']}/{out['of']} rounds: LIME's is SHAP's 2nd in "
          f"{out['lime_is_shap_2nd']:.1%} (top 3 {out['lime_in_shap_top3']:.1%}); SHAP gap #1−#2 "
          f"median {out['gap_median_disagree']:.1%} vs {out['gap_median_agree']:.1%} when they "
          f"agree; LIME's is thrown later in {out['lime_pick_later']:.1%}")
    return out


def _shap_example(rows: list[dict], m: str) -> dict | None:
    """La misma ronda de ejemplo que shap_report.plot_examples para ese mapa."""
    cand = [r for r in rows if r["map"] == m and 6 <= r["n"] <= 12
            and (r["p_b"] > 0.5) == (r["target"] == "B")]
    if not cand:
        return None
    return max(cand, key=lambda r: min(r["phi"][r["phi"] > 0].sum(), -r["phi"][r["phi"] < 0].sum()))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("explain", "report"), required=True)
    ap.add_argument("--jobs", type=int, default=5)
    args = ap.parse_args()
    if args.stage == "explain":
        stage_explain(args.jobs)
    else:
        stage_report()


if __name__ == "__main__":
    main()
