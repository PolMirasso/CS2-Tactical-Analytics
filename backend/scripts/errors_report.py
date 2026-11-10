from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from shap_report import _load
from sqlalchemy import text

from app.analytics.maps import get_map, lower_level_threshold
from app.db import _ensure, init_db
from app.ml.explain import token_zone

DS = Path("/app/data_store")
SHAP, ANCHORS, LIME = DS / "shap", DS / "anchors" / "rounds_t0.9.json", DS / "lime"
SWEEP = DS / "sweep_deepsets_2026-09-21"
OUT = DS / "errors"
SIDE = 0.05


def _rounds() -> list[dict]:
    out = []
    for p in sorted(SHAP.glob("fold*.json")):
        out += [r for r in json.loads(p.read_text())["rounds"] if "site" in r]
    for r in out:
        r["pred"] = "B" if r["site"]["p_b"] > 0.5 else "A"
        r["ok"] = r["pred"] == r["target"]
        r["conf"] = max(r["site"]["p_b"], 1 - r["site"]["p_b"])
    return out


def _sides(rounds: list[dict]) -> None:
    zdir = {
        (m, z["zone"]): z["mean_phi_b"]
        for m, rows in json.loads((SHAP / "summary.json").read_text())["site"]["zones"].items()
        for z in rows
    }
    for r in rounds:
        r["sides"] = []
        for g in r["grenades"]:
            z = token_zone(r["map"], g["x"], g["y"], g["z"])
            d = zdir.get((r["map"], z.id)) if z is not None else None
            r["sides"].append(
                "?" if d is None else "B" if d > SIDE else "A" if d < -SIDE else "neutral"
            )


def bias(rounds: list[dict]) -> dict:
    print("\n== Predicted vs real B share and per-class accuracy")
    print(f"{'map':<12}{'rounds':>7}{'real B':>8}{'pred B':>8}{'acc A':>7}{'acc B':>7}")
    out = []
    for m in [*sorted({r["map"] for r in rounds}), "all"]:
        rs = [r for r in rounds if m in ("all", r["map"])]
        row = {
            "map": m, "n": len(rs),
            "real_b": float(np.mean([r["target"] == "B" for r in rs])),
            "pred_b": float(np.mean([r["pred"] == "B" for r in rs])),
            "acc_a": float(np.mean([r["ok"] for r in rs if r["target"] == "A"])),
            "acc_b": float(np.mean([r["ok"] for r in rs if r["target"] == "B"])),
        }
        out.append(row)
        print(f"{m:<12}{len(rs):>7}{row['real_b']:>8.3f}{row['pred_b']:>8.3f}"
              f"{row['acc_a']:>7.3f}{row['acc_b']:>7.3f}")
    return {"per_map": out, "base_b": float(np.mean([r["site"]["base_b"] for r in rounds]))}


def by_size_and_confidence(rounds: list[dict]) -> dict:
    out: dict = {"n": [], "conf": []}
    print("\n== By number of grenades")
    for lo, hi in ((0, 0), (1, 3), (4, 6), (7, 10), (11, 15), (16, 99)):
        rs = [r for r in rounds if lo <= r["n"] <= hi]
        row = {"n": f"{lo}-{hi}", "rounds": len(rs), "acc": float(np.mean([r["ok"] for r in rs])),
               "real_b": float(np.mean([r["target"] == "B" for r in rs])),
               "pred_b": float(np.mean([r["pred"] == "B" for r in rs]))}
        out["n"].append(row)
        print(f"  {row['n']:<6}{len(rs):>6} acc {row['acc']:.3f}  real B {row['real_b']:.3f}"
              f"  pred B {row['pred_b']:.3f}")
    print("\n== By confidence")
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 0.97), (0.97, 1.01)):
        rs = [r for r in rounds if lo <= r["conf"] < hi]
        row = {"conf": f"{lo}-{min(hi, 1.0)}", "rounds": len(rs),
               "acc": float(np.mean([r["ok"] for r in rs]))}
        out["conf"].append(row)
        print(f"  {row['conf']:<10}{len(rs):>6} acc {row['acc']:.3f}")
    wrong = [r for r in rounds if not r["ok"]]
    out["wrong"] = len(wrong)
    out["wrong_conf_ge_0.8"] = float(np.mean([r["conf"] >= 0.8 for r in wrong]))
    out["wrong_conf_lt_0.7"] = float(np.mean([r["conf"] < 0.7 for r in wrong]))
    print(f"  {len(wrong)} errors: confidence ≥ 0.8 in {out['wrong_conf_ge_0.8']:.1%},"
          f" < 0.7 in {out['wrong_conf_lt_0.7']:.1%}")
    return out


def typology(rounds: list[dict]) -> dict:
    """Errores según dónde cae su utility: en callouts del site predicho, del real, o en ninguno."""
    kinds = {
        (True, False): "only_pred", (True, True): "both",
        (False, False): "neither", (False, True): "only_real",
    }
    out: dict = {}
    print(f"\n== Where the utility of each round lands (callouts with |mean φ| > {SIDE})")
    for grp, rs in (("wrong", [r for r in rounds if not r["ok"]]),
                    ("right", [r for r in rounds if r["ok"]])):
        c = Counter(kinds[(r["pred"] in r["sides"], r["target"] in r["sides"])] for r in rs)
        out[grp] = {k: c[k] / len(rs) for k in kinds.values()}
        out[grp]["n"] = len(rs)
        print(f"  {grp:<6}{len(rs):>5}  " + "  ".join(f"{k} {c[k] / len(rs):.1%}"
                                                     for k in kinds.values()))
    for lo, hi in ((0.5, 0.8), (0.8, 1.01)):
        rs = [r for r in rounds if not r["ok"] and lo <= r["conf"] < hi]
        c = Counter(kinds[(r["pred"] in r["sides"], r["target"] in r["sides"])] for r in rs)
        key = f"wrong_conf_{lo}-{min(hi, 1.0)}"
        out[key] = {k: c[k] / len(rs) for k in kinds.values()}
        out[key]["n"] = len(rs)
        print(f"  wrong, confidence {lo}-{min(hi, 1.0)}: {len(rs)}  " + "  ".join(
            f"{k} {c[k] / len(rs):.1%}" for k in kinds.values()))

    print("\n== The grenade with most SHAP weight toward the predicted site")
    for grp, rs in (("wrong", [r for r in rounds if not r["ok"]]),
                    ("right", [r for r in rounds if r["ok"]])):
        t, side = [], Counter()
        for r in rs:
            if not r["n"]:
                continue
            phi = np.array(r["site"]["phi_b"])
            j = int(np.argmax(phi if r["pred"] == "B" else -phi))
            t.append(r["grenades"][j]["t"])
            side["neutral" if r["sides"][j] in ("neutral", "?") else
                 "pred" if r["sides"][j] == r["pred"] else "other"] += 1
        tot = sum(side.values())
        out[f"top_{grp}"] = {"median_t": float(np.median(t)),
                             **{k: side[k] / tot for k in ("pred", "neutral", "other")}}
        print(f"  {grp:<6} median throw {np.median(t):.0f} s · in a callout of the predicted site "
              f"{side['pred'] / tot:.1%} · neutral {side['neutral'] / tot:.1%}"
              f" · other site {side['other'] / tot:.1%}")
    return out


def hard_maps(rounds: list[dict]) -> dict:
    out = {}
    for m in ("de_nuke", "de_train"):
        rs = [r for r in rounds if r["map"] == m]
        out[m] = {}
        print(f"\n== {m}: real-B rounds, right vs wrong")
        for ok in (True, False):
            sel = [r for r in rs if r["target"] == "B" and r["ok"] == ok]
            sides = Counter(s for r in sel for s in r["sides"])
            tot = sum(sides.values())
            row = {
                "rounds": len(sel), "grenades": float(np.mean([r["n"] for r in sel])),
                "any_b": float(np.mean(["B" in r["sides"] for r in sel])),
                "any_a": float(np.mean(["A" in r["sides"] for r in sel])),
                "share": {k: sides[k] / tot for k in ("A", "B", "neutral")},
                "lower": float(np.mean([g["z"] >= 1 for r in sel for g in r["grenades"]])),
            }
            out[m]["right" if ok else "wrong"] = row
            print(f"  {'right' if ok else 'wrong':<6}{len(sel):>4} rounds · {row['grenades']:.1f}"
                  f" grenades · some in a B callout {row['any_b']:.0%} · in an A callout"
                  f" {row['any_a']:.0%} · grenades A/B/neutral {row['share']['A']:.0%}/"
                  f"{row['share']['B']:.0%}/{row['share']['neutral']:.0%}"
                  + (f" · lower level {row['lower']:.0%}" if m == "de_nuke" else ""))
        neu = [r for r in rs if r["n"] and all(s in ("neutral", "?") for s in r["sides"])]
        if neu:
            out[m]["only_neutral"] = {
                "rounds": len(neu), "real_b": float(np.mean([r["target"] == "B" for r in neu])),
                "mean_p_b": float(np.mean([r["site"]["p_b"] for r in neu])),
                "pred_b": float(np.mean([r["pred"] == "B" for r in neu])),
            }
            o = out[m]["only_neutral"]
            print(f"  only neutral utility: {o['rounds']} rounds · real B {o['real_b']:.2f}"
                  f" · mean P(B) {o['mean_p_b']:.2f} · predicted B {o['pred_b']:.2f}")
    return out


def nuke_levels(rounds: list[dict]) -> dict:
    """¿Falta el nivel de alguna granada de nuke, o el umbral de z parte mal los dos niveles?"""
    unknown = sum(g["z"] == 0.5 for r in rounds if r["map"] == "de_nuke" for g in r["grenades"])
    thr = lower_level_threshold("de_nuke")
    gm = get_map("de_nuke")
    with _ensure()() as s:
        rows = s.execute(text("""
            select u.radar_x, u.radar_y, u.z from utility_events u
            join rounds r on r.id = u.round_id
            where r.map_id = 'de_nuke' and r.target_site in ('A', 'B') and u.team = 't'
              and u.z is not null and u.radar_x is not null
              and (r.plant_time_s is null or u.round_time_s <= r.plant_time_s)
        """)).all()
    zs = np.array([r.z for r in rows
                   if (z := gm.zone_at(r.radar_x, r.radar_y)) is not None and z.name == "A Site"])
    hist = Counter((np.floor(zs / 50) * 50).astype(int).tolist())
    near = int(np.sum(np.abs(zs - thr) < 50))
    print(f"\n== nuke levels: {unknown} grenades without level · z threshold {thr}"
          f" · grenades over A Site in 2D: {len(zs)}, within ±50 of the threshold: {near}")
    print("  " + "  ".join(f"{b}:{hist[b]}" for b in sorted(hist) if b <= -300))
    return {"unknown": int(unknown), "threshold": thr, "a_site_2d": len(zs), "near": near,
            "hist": {int(k): v for k, v in sorted(hist.items())}}


def intent() -> dict:
    samples, targets, _, _ = _load()
    labels: dict[str, Counter] = defaultdict(Counter)
    for s, t in zip(samples, targets, strict=True):
        key = f"plant_{t}" if t in ("A", "B") else f"intent_{s.get('intent')}"
        labels[s["context"]["map"]][key] += 1
    acc: dict[str, dict[str, list]] = {arm: defaultdict(list) for arm in ("baseline", "intent_off")}
    for p in sorted(SWEEP.glob("ltoF_seed*.json")):
        d = json.loads(p.read_text())
        for arm in acc:
            for pm in d["results"][arm]["cv"]["per_map"]:
                acc[arm][pm["map_id"]].append(pm["site_accuracy"])
    out = []
    print("\n== NoPlant rounds with intent (site head training) and their effect, 8 seeds")
    print(f"{'map':<12}{'plant B':>8}{'intent B':>9}{'with':>7}{'without':>8}{'delta':>8}{'+':>4}")
    for m in sorted(labels):
        c = labels[m]
        a, b = np.array(acc["baseline"][m]), np.array(acc["intent_off"][m])
        row = {"map": m,
               "plant_b": c["plant_B"] / (c["plant_A"] + c["plant_B"]),
               "intent_b": c["intent_B"] / max(1, c["intent_A"] + c["intent_B"]),
               "intent_n": c["intent_A"] + c["intent_B"],
               "with": float(a.mean()), "without": float(b.mean()),
               "delta": float((a - b).mean()), "positive": int((a > b).sum()), "seeds": len(a)}
        out.append(row)
        print(f"{m:<12}{row['plant_b']:>8.2f}{row['intent_b']:>9.2f}{row['with']:>7.3f}"
              f"{row['without']:>8.3f}{row['delta']:>+8.3f}{row['positive']:>4}")
    return {"per_map": out}


def anchors_and_lime(rounds: list[dict]) -> dict:
    out: dict = {}
    if ANCHORS.exists():
        anch = {r["i"]: r for r in json.loads(ANCHORS.read_text())}
        for grp, ok in (("wrong", False), ("right", True)):
            out[f"anchor_{grp}"] = float(np.mean(
                [anch[r["i"]].get("valid", False)
                 for r in rounds if r["ok"] == ok and r["i"] in anch]
            ))
        print(f"\n== Rounds with an Anchors rule (τ 0.9): wrong {out['anchor_wrong']:.1%},"
              f" right {out['anchor_right']:.1%}")
    lime = []
    for p in sorted(LIME.glob("fold*.json")):
        lime += json.loads(p.read_text())["rounds"]
    if lime:
        ok = {r["i"]: r["ok"] for r in rounds}
        for grp, flag in (("wrong", False), ("right", True)):
            out[f"lime_r2_{grp}"] = float(np.mean(
                [r["lime"]["score"] for r in lime if ok.get(r["i"]) == flag]
            ))
        print(f"== LIME R² (how linear the model is around the round): wrong"
              f" {out['lime_r2_wrong']:.3f}, right {out['lime_r2_right']:.3f}")
    return out


def teams(rounds: list[dict], min_rounds: int = 40) -> dict:
    by: dict[str, list[bool]] = defaultdict(list)
    for r in rounds:
        by[str(r["team"])].append(r["ok"])
    accs = sorted(float(np.mean(v)) for v in by.values() if len(v) >= min_rounds)
    print(f"\n== Accuracy per unseen team (≥{min_rounds} plants): {len(accs)} teams,"
          f" {accs[0]:.3f} – {accs[-1]:.3f}, median {np.median(accs):.3f}")
    return {"teams": len(accs), "min": accs[0], "max": accs[-1], "median": float(np.median(accs))}


def main() -> None:
    init_db()
    rounds = _rounds()
    _sides(rounds)
    print(f"{len(rounds)} plant rounds · accuracy {np.mean([r['ok'] for r in rounds]):.4f}")
    out = {
        "bias": bias(rounds),
        "size_conf": by_size_and_confidence(rounds),
        "typology": typology(rounds),
        "hard_maps": hard_maps(rounds),
        "nuke_levels": nuke_levels(rounds),
        "intent": intent(),
        "explainers": anchors_and_lime(rounds),
        "teams": teams(rounds),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "summary.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"\n→ {OUT / 'summary.json'}")


if __name__ == "__main__":
    main()
