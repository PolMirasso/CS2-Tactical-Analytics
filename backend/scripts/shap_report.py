"""SHAP sobre las cabezas de DeepSets: cada ronda la explica un modelo que no vio a su equipo.

    shap_report.py --stage explain --jobs 5   # entrena los 5 folds de equipos no vistos
                                              # (semilla 0) y explica sus rondas → fold<k>.json
    shap_report.py --stage report             # tablas y figuras a partir de esos JSON

Site: φ hacia B por granada (hacia A es el negativo). Gate: φ hacia NoPlant por granada y por
grupo de contexto. Timing: φ por clase.
"""

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
from sqlalchemy import select

from app.analytics.maps import get_map, radar_file
from app.db import _ensure, init_db
from app.domain.models import User
from app.ml.dataset import build_dataset
from app.ml.explain import gate_value, shapley, site_value, timing_value
from app.ml.features import _UTILS, ROUND_TIME_S
from app.ml.model import MIN_ROUNDS
from app.ml.validation import fold_split, fold_teams, train_rows

OUT = Path("/app/data_store/shap")
K_MAX = 5
N_RANDOM = 32
MIN_ZONE = 15
_POOL: dict = {}


def _load():
    init_db()
    with _ensure()() as session:
        users = list(session.scalars(select(User).order_by(User.id)))
        user = next((u for u in users if u.is_admin), users[0] if users else None)
        if user is None:
            sys.exit("No users in the DB.")
        return build_dataset(session, user)


# explicar

def _grenades(tokens) -> list[dict]:
    return [
        {
            "type": _UTILS[int(np.argmax(t[: len(_UTILS)]))],
            "x": t[4] * 1024.0, "y": t[5] * 1024.0, "t": t[6] * ROUND_TIME_S, "z": t[7],
        }
        for t in tokens
    ]


def _deletion(value, n: int, toward: np.ndarray, pred: int, target: int, rng) -> dict:
    """Predicción al quitar (o dejar solo) las k granadas con más peso SHAP hacia el site
    predicho, frente a k granadas al azar."""
    order = np.argsort(-toward)
    out: dict[str, list] = {"remove": [], "keep": []}
    for k in range(1, K_MAX + 1):
        if k >= n:
            out["remove"].append(None)
            out["keep"].append(None)
            continue
        rand = np.array([rng.permutation(n)[:k] for _ in range(N_RANDOM)])
        for mode in ("remove", "keep"):
            on = mode == "remove"
            masks = np.full((N_RANDOM + 1, n), on)
            masks[0, order[:k]] = not on
            masks[np.arange(1, N_RANDOM + 1)[:, None], rand] = not on
            preds = (value(masks)[:, 1] > 0.5).astype(int)
            out[mode].append({
                "shap": int(preds[0]),
                "rand_same": float(np.mean(preds[1:] == pred)),
                "rand_correct": float(np.mean(preds[1:] == target)),
            })
    return out


def _explain_round(model, s: dict, target: str, timing: str | None, rng) -> dict:
    tokens = s["tokens"]
    n = len(tokens)
    rec: dict = {"n": n, "grenades": _grenades(tokens)}

    value, players = gate_value(model, tokens, s["context"])
    g = shapley(value, len(players))
    rec["gate"] = {
        "groups": players[n:], "p_noplant": g.full[1], "base_noplant": g.base[1],
        "phi_noplant": g.phi[:, 1].tolist(), "exact": g.exact,
    }
    if target not in ("A", "B"):
        return rec

    value = site_value(model, tokens)
    sh = shapley(value, n)
    p_b = float(sh.full[1])
    pred, y = int(p_b > 0.5), int(target == "B")
    phi_b = sh.phi[:, 1]
    rec["site"] = {
        "p_b": p_b, "base_b": float(sh.base[1]), "phi_b": phi_b.tolist(), "exact": sh.exact,
        "deletion": _deletion(value, n, phi_b if pred else -phi_b, pred, y, rng),
    }
    if model.timing_net is not None and timing is not None and n:
        tsh = shapley(timing_value(model, tokens), n)
        rec["timing"] = {
            "classes": model.timing_classes, "label": timing, "p": tsh.full.tolist(),
            "base": tsh.base.tolist(), "phi": tsh.phi.tolist(),
        }
    return rec


def _fold(task: tuple[int, list[str]]) -> tuple[int, int, float]:
    k, held = task
    samples, targets, timing = _POOL["samples"], _POOL["targets"], _POOL["timing"]
    t0 = time.time()
    train, test = fold_split(samples, targets, held)
    path = OUT / "models" / f"fold{k}.joblib"
    if path.exists():
        model = joblib.load(path)
    else:
        if len(train) < MIN_ROUNDS:
            return k, 0, 0.0
        model = train_rows(samples, targets, timing, train)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, path)
    print(f"fold {k}: trained in {time.time() - t0:.0f}s, explaining {len(test)} rounds",
          flush=True)

    rng = np.random.default_rng(k)
    recs = []
    for i in test:
        ctx = samples[i]["context"]
        rec = _explain_round(model, samples[i], targets[i], timing[i], rng)
        recs.append({"i": i, "fold": k, "map": ctx.get("map"), "team": ctx.get("team"),
                     "target": targets[i], **rec})
    (OUT / f"fold{k}.json").write_text(json.dumps({"held": held, "rounds": recs}))
    return k, len(recs), time.time() - t0


def stage_explain(jobs: int, folds: int) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    samples, targets, timing, meta = _load()
    print(f"rounds={len(samples)} teams={meta.get('n_teams')}", flush=True)
    _POOL.update(samples=samples, targets=targets, timing=timing)
    tasks = list(enumerate(fold_teams(samples, targets, folds)))
    with ProcessPoolExecutor(max_workers=jobs, mp_context=get_context("fork")) as ex:
        for k, n, dt in ex.map(_fold, tasks):
            print(f"fold {k}: {n} rounds in {dt:.0f}s", flush=True)


# informe

def _rounds() -> list[dict]:
    out = []
    for p in sorted(OUT.glob("fold*.json")):
        out += json.loads(p.read_text())["rounds"]
    return out


def _fmt(v) -> str:
    return "    —" if v is None else f"{v:.3f}"


def _site_tables(rounds: list[dict]) -> dict:
    site = [r for r in rounds if "site" in r]
    acc = np.mean([(r["site"]["p_b"] > 0.5) == (r["target"] == "B") for r in site])
    gap = max(abs(sum(r["site"]["phi_b"]) - (r["site"]["p_b"] - r["site"]["base_b"])) for r in site)
    exact = np.mean([r["site"]["exact"] for r in site])
    print(f"\nSite head · {len(site)} plant rounds · accuracy {acc:.4f} · exact {exact:.1%}"
          f" · max |Σφ − (p − base)| {gap:.1e}")

    base = np.mean([r["site"]["base_b"] for r in site])
    print(f"base P(B), no utility: {base:.3f}")

    # cuánto de la decisión llevan las granadas con más peso
    top = defaultdict(list)
    for r in site:
        a = np.sort(np.abs(r["site"]["phi_b"]))[::-1]
        if len(a) >= 3 and a.sum() > 0:
            for k in (1, 3):
                top[k].append(a[:k].sum() / a.sum())
    n_mean = np.mean([r["n"] for r in site])
    print(f"share of Σ|φ| in the top grenade {np.mean(top[1]):.2f}, top 3 {np.mean(top[3]):.2f}"
          f" (mean {n_mean:.1f} grenades/round)")

    by_type: dict[str, list[float]] = defaultdict(list)
    for r in site:
        for g, phi in zip(r["grenades"], r["site"]["phi_b"], strict=True):
            by_type[g["type"]].append(abs(phi))
    total = sum(sum(v) for v in by_type.values())
    count = sum(len(v) for v in by_type.values())
    print(f"\n{'type':<10}{'grenades':>10}{'% count':>9}{'% Σ|φ|':>9}{'mean |φ|':>10}")
    types = {}
    for t in _UTILS:
        v = by_type.get(t, [])
        types[t] = {"n": len(v), "share_count": len(v) / count, "share_phi": sum(v) / total,
                    "mean_abs": float(np.mean(v)) if v else None}
        print(f"{t:<10}{len(v):>10}{len(v) / count:>9.1%}{sum(v) / total:>9.1%}"
              f"{_fmt(types[t]['mean_abs']):>10}")

    bins = [(0, 15), (15, 30), (30, 45), (45, 60), (60, 1e9)]
    by_time: dict[tuple, list[float]] = defaultdict(list)
    for r in site:
        for g, phi in zip(r["grenades"], r["site"]["phi_b"], strict=True):
            b = next(b for b in bins if b[0] <= g["t"] < b[1])
            by_time[b].append(abs(phi))
    print(f"\n{'throw time':<12}{'grenades':>10}{'mean |φ|':>10}")
    times = []
    for b in bins:
        v = by_time[b]
        label = f"{b[0]}-{b[1]} s" if b[1] < 1e9 else f">{b[0]} s"
        times.append({"bin": label, "n": len(v), "mean_abs": float(np.mean(v)) if v else None})
        print(f"{label:<12}{len(v):>10}{_fmt(times[-1]['mean_abs']):>10}")

    deletion = _deletion_table(site)
    zones = _zone_table(site)
    return {"n": len(site), "accuracy": acc, "exact": exact, "base_b": base,
            "top1": np.mean(top[1]), "top3": np.mean(top[3]), "types": types, "times": times,
            "deletion": deletion, "zones": zones}


def _deletion_table(site: list[dict]) -> dict:
    """Acierto al quitar/dejar k granadas: las k de más peso SHAP frente a k al azar."""
    out = {}
    print("\nFaithfulness (rounds with more than k grenades)")
    print(f"{'k':<3}{'rounds':>8}{'full':>8}"
          f"{'−SHAP':>8}{'−rand':>8}{'flip SHAP':>11}{'flip rand':>11}"
          f"{'only SHAP':>11}{'only rand':>11}")
    for mode in ("remove", "keep"):
        out[mode] = []
    for k in range(1, K_MAX + 1):
        rows = [r for r in site if r["site"]["deletion"]["remove"][k - 1] is not None]
        y = np.array([int(r["target"] == "B") for r in rows])
        pred = np.array([int(r["site"]["p_b"] > 0.5) for r in rows])
        line = {"k": k, "n": len(rows), "full": float(np.mean(pred == y))}
        for mode in ("remove", "keep"):
            d = [r["site"]["deletion"][mode][k - 1] for r in rows]
            s = np.array([x["shap"] for x in d])
            line[mode] = {
                "shap_acc": float(np.mean(s == y)),
                "rand_acc": float(np.mean([x["rand_correct"] for x in d])),
                "shap_flip": float(np.mean(s != pred)),
                "rand_flip": float(1 - np.mean([x["rand_same"] for x in d])),
            }
        rm, kp = line["remove"], line["keep"]
        print(f"{k:<3}{len(rows):>8}{line['full']:>8.3f}{rm['shap_acc']:>8.3f}{rm['rand_acc']:>8.3f}"
              f"{rm['shap_flip']:>11.3f}{rm['rand_flip']:>11.3f}"
              f"{kp['shap_acc']:>11.3f}{kp['rand_acc']:>11.3f}")
        out["remove"].append({"k": k, "n": len(rows), "full": line["full"], **rm})
        out["keep"].append({"k": k, "n": len(rows), "full": line["full"], **kp})
    return out


def _zone_table(site: list[dict]) -> dict:
    """φ medio hacia B de las granadas que caen en cada callout (≥ MIN_ZONE granadas)."""
    acc: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in site:
        gm = get_map(r["map"])
        if gm is None:
            continue
        for g, phi in zip(r["grenades"], r["site"]["phi_b"], strict=True):
            z = gm.zone_at(g["x"], g["y"])
            row = acc[r["map"]].setdefault(z.id, {"zone": z.id, "name": z.name, "phi": []})
            row["phi"].append(phi)
    out = {}
    print(f"\nCallouts that point to a site (mean φ toward B, ≥{MIN_ZONE} grenades)")
    for m in sorted(acc):
        rows = [
            {"zone": v["zone"], "name": v["name"], "n": len(v["phi"]),
             "mean_phi_b": float(np.mean(v["phi"]))}
            for v in acc[m].values() if len(v["phi"]) >= MIN_ZONE
        ]
        rows.sort(key=lambda r: r["mean_phi_b"])
        out[m] = rows
        to_a = ", ".join(f"{r['name']} {r['mean_phi_b']:+.2f}" for r in rows[:3])
        to_b = ", ".join(f"{r['name']} {r['mean_phi_b']:+.2f}" for r in rows[::-1][:3])
        print(f"  {m:<12} A: {to_a}\n  {'':<12} B: {to_b}")
    return out


def _gate_table(rounds: list[dict]) -> dict:
    gate = [r for r in rounds if "gate" in r]
    groups = gate[0]["gate"]["groups"]
    share: dict[str, list[float]] = defaultdict(list)
    for r in gate:
        phi = np.abs(r["gate"]["phi_noplant"])
        tot = phi.sum()
        if tot == 0:
            continue
        share["grenades"].append(phi[: r["n"]].sum() / tot)
        for j, g in enumerate(groups):
            share[g].append(phi[r["n"] + j] / tot)
    exact = np.mean([r["gate"]["exact"] for r in gate])
    print(f"\nGate (plant vs NoPlant) · {len(gate)} rounds · exact {exact:.1%}")
    print(f"{'player':<12}{'mean share of Σ|φ|':>20}")
    out = {}
    for k in ["grenades", *groups]:
        out[k] = float(np.mean(share[k]))
        print(f"{k:<12}{out[k]:>20.1%}")
    return {"n": len(gate), "exact": exact, "share": out}


def _timing_table(rounds: list[dict]) -> dict:
    """¿La granada que decide el timing es la última lanzada?"""
    rows = [r for r in rounds if "timing" in r and r["n"] >= 2]
    hit, chance = [], []
    for r in rows:
        tm = r["timing"]
        pred = int(np.argmax(tm["p"]))
        phi = np.abs(np.array(tm["phi"])[:, pred])
        last = int(np.argmax([g["t"] for g in r["grenades"]]))
        hit.append(int(np.argmax(phi)) == last)
        chance.append(1 / r["n"])
    out = {"n": len(rows), "last_is_top": float(np.mean(hit)), "chance": float(np.mean(chance))}
    print(f"\nTiming · {len(rows)} rounds · top grenade is the last thrown in "
          f"{out['last_is_top']:.1%} (chance {out['chance']:.1%})")
    return out


# figuras

_A, _B, _MID = "#e34948", "#2a78d6", "#f0efec"
_INK, _INK2 = "#0b0b0b", "#52514e"
_MARKERS = {"smoke": "o", "flash": "^", "molotov": "s", "he": "D"}
_NAMES = {"smoke": "smoke", "flash": "flash", "molotov": "molotov", "he": "HE"}


def _cmap():
    from matplotlib.colors import LinearSegmentedColormap

    return LinearSegmentedColormap.from_list("ab", [_A, _MID, _B])


def _radar(ax, map_id: str) -> None:
    import matplotlib.image as mpimg

    path = radar_file(map_id)
    if path is not None:
        # en gris para que el rojo de los sites del radar no se lea como "hacia A"
        img = mpimg.imread(path)
        gray = img[..., :3] @ np.array([0.299, 0.587, 0.114])
        ax.imshow(gray, cmap="gray", vmin=0, vmax=1, alpha=0.55, extent=(0, 1024, 1024, 0))
    ax.set_xlim(0, 1024)
    ax.set_ylim(1024, 0)
    ax.set_axis_off()


def plot_zones(zones: dict, figs: Path) -> None:
    import matplotlib.pyplot as plt
    from matplotlib.colors import Normalize
    from matplotlib.patches import Polygon

    lim = max(abs(r["mean_phi_b"]) for rows in zones.values() for r in rows)
    norm = Normalize(-lim, lim)
    for m, rows in zones.items():
        gm = get_map(m)
        fig, ax = plt.subplots(figsize=(7, 7.6), dpi=150)
        _radar(ax, m)
        by_id = {r["zone"]: r for r in rows}
        for z in gm.zones:
            if not z.polygon:
                continue
            r = by_id.get(z.id)
            if r is None:
                ax.add_patch(Polygon(z.polygon, closed=True, fill=False, lw=0.4,
                                     ec="white", alpha=0.35))
                continue
            ax.add_patch(Polygon(z.polygon, closed=True, fc=_cmap()(norm(r["mean_phi_b"])),
                                 ec="white", lw=0.8, alpha=0.8))
            if abs(r["mean_phi_b"]) >= 0.25 * lim:
                cx, cy = z.centroid
                ax.text(cx, cy, z.name, ha="center", va="center", fontsize=6, color=_INK,
                        bbox={"fc": "white", "ec": "none", "alpha": 0.7, "pad": 0.8})
        sm = plt.cm.ScalarMappable(norm=norm, cmap=_cmap())
        cb = fig.colorbar(sm, ax=ax, orientation="horizontal", fraction=0.04, pad=0.02)
        cb.set_label("φ mitjà cap a B per granada  (← A · B →)", color=_INK2, fontsize=8)
        cb.ax.tick_params(labelsize=7, colors=_INK2)
        ax.set_title(f"{m} · on apunta la utility segons SHAP", color=_INK, fontsize=10,
                     loc="left")
        fig.tight_layout()
        fig.savefig(figs / f"zones_{m}.png", facecolor="white")
        plt.close(fig)


def plot_deletion(deletion: dict, figs: Path) -> None:
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(9, 3.6), dpi=150, sharey=True)
    titles = {"remove": "Treient k granades", "keep": "Deixant només k granades"}
    for ax, mode in zip(axes, ("remove", "keep"), strict=True):
        rows = deletion[mode]
        ks = [r["k"] for r in rows]
        for key, color, label in (("shap_acc", _B, "les k amb més pes SHAP"),
                                  ("rand_acc", "#eb6834", "k a l'atzar")):
            ys = [r[key] for r in rows]
            ax.plot(ks, ys, color=color, lw=2, marker="o", ms=5, label=label)
            ax.annotate(f"{ys[-1]:.2f}", (ks[-1], ys[-1]), xytext=(6, 0),
                        textcoords="offset points", va="center", fontsize=8, color=_INK2)
        ax.axhline(0.5, color=_INK2, lw=0.8, ls=":")
        ax.set_title(titles[mode], loc="left", fontsize=10, color=_INK)
        ax.set_xlabel("k", color=_INK2)
        ax.set_xticks(ks)
        ax.grid(axis="y", color="#e6e5e1", lw=0.6)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    axes[0].set_ylabel("encert A/B", color=_INK2)
    axes[0].legend(frameon=False, fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(figs / "deletion.png", facecolor="white")
    plt.close(fig)


def plot_examples(site: list[dict], figs: Path) -> None:
    """Por mapa, la ronda acertada de 6 a 12 granadas con más tira y afloja entre A y B."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    by_map: dict[str, list[dict]] = defaultdict(list)
    for r in site:
        ok = (r["site"]["p_b"] > 0.5) == (r["target"] == "B")
        if ok and 6 <= r["n"] <= 12:
            by_map[r["map"]].append(r)
    for m, rows in by_map.items():
        r = max(rows, key=lambda r: min(sum(f for f in r["site"]["phi_b"] if f > 0),
                                        -sum(f for f in r["site"]["phi_b"] if f < 0)))
        phi = np.array(r["site"]["phi_b"])
        fig, ax = plt.subplots(figsize=(7, 7.4), dpi=150)
        _radar(ax, m)
        scale = 600 / max(np.abs(phi).max(), 1e-9)
        for g, f in zip(r["grenades"], phi, strict=True):
            ax.scatter(g["x"], g["y"], s=30 + scale * abs(f), marker=_MARKERS[g["type"]],
                       c=_B if f > 0 else _A, edgecolors="white", linewidths=1.5, zorder=3)
            ax.annotate(f"{f:+.2f} · {g['t']:.0f}s", (g["x"], g["y"]), xytext=(8, -8),
                        textcoords="offset points", fontsize=7, color=_INK,
                        bbox={"fc": "white", "ec": "none", "alpha": 0.75, "pad": 0.6})
        handles = [Line2D([], [], marker=_MARKERS[t], ls="", color=_INK2, label=_NAMES[t])
                   for t in _UTILS]
        handles += [Line2D([], [], marker="o", ls="", color=c, label=lab)
                    for c, lab in ((_A, "empeny cap a A"), (_B, "empeny cap a B"))]
        ax.legend(handles=handles, loc="lower left", fontsize=7, framealpha=0.85)
        site_lbl = "B" if r["site"]["p_b"] > 0.5 else "A"
        p = r["site"]["p_b"] if site_lbl == "B" else 1 - r["site"]["p_b"]
        base = r["site"]["base_b"] if site_lbl == "B" else 1 - r["site"]["base_b"]
        ax.set_title(f"{m} · ronda {r['i']} · real {r['target']} · P({site_lbl}) "
                     f"{base:.2f} sense utility → {p:.2f}", loc="left", fontsize=9, color=_INK)
        fig.tight_layout()
        fig.savefig(figs / f"example_{m}.png", facecolor="white")
        plt.close(fig)


def stage_report() -> None:
    import matplotlib

    matplotlib.use("Agg")
    rounds = _rounds()
    if not rounds:
        sys.exit(f"No fold*.json in {OUT}: run --stage explain first.")
    summary = {
        "site": _site_tables(rounds),
        "gate": _gate_table(rounds),
        "timing": _timing_table(rounds),
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    figs = OUT / "figures"
    figs.mkdir(exist_ok=True)
    plot_zones(summary["site"]["zones"], figs)
    plot_deletion(summary["site"]["deletion"], figs)
    plot_examples([r for r in rounds if "site" in r], figs)
    print(f"\n→ {OUT / 'summary.json'} and {figs}/")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=("explain", "report"), required=True)
    ap.add_argument("--jobs", type=int, default=5)
    ap.add_argument("--folds", type=int, default=5)
    args = ap.parse_args()
    if args.stage == "explain":
        stage_explain(args.jobs, args.folds)
    else:
        stage_report()


if __name__ == "__main__":
    main()
