from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np


def _agg(runs: list[dict], key: str) -> tuple[float | None, float | None]:
    vals = [r[key] for r in runs if r.get(key) is not None]
    if not vals:
        return None, None
    return float(np.mean(vals)), float(np.std(vals))


def _f(v: float | None, sd: float | None = None, digits: int = 3) -> str:
    if v is None:
        return "—"
    return f"{v:.{digits}f}" + (f" ±{sd:.3f}" if sd is not None else "")


def holdout_table(path: Path, name_col: str = "Configuració") -> str:
    blob = json.loads(path.read_text())
    rows = []
    for name, r in blob["results"].items():
        site, site_sd = _agg(r["runs"], "site_accuracy")
        acc, acc_sd = _agg(r["runs"], "accuracy")
        tim, tim_sd = _agg(r["runs"], "timing_accuracy")
        base, _ = _agg(r["runs"], "baseline_accuracy")
        sbase, _ = _agg(r["runs"], "site_baseline_accuracy")
        rows.append((name, r.get("description") or r["label"], site, site_sd,
                     acc, acc_sd, tim, tim_sd, sbase, base))
    out = [f"| {name_col} | site (A/B) | baseline A/B | 3 classes | baseline 3-cl | timing |",
           "|---|---|---|---|---|---|"]
    for n, _lab, site, ssd, acc, asd, tim, tsd, sbase, base in rows:
        out.append(
            f"| `{n}` | {_f(site, ssd)} | {_f(sbase)} | {_f(acc, asd)} | "
            f"{_f(base)} | {_f(tim, tsd)} |"
        )
    return "\n".join(out)


def lto_table(path: Path, name_col: str = "Configuració") -> str:
    blob = json.loads(path.read_text())
    out = [f"| {name_col} | site (A/B) | baseline A/B | 3 classes | rondes | plants |",
           "|---|---|---|---|---|---|"]
    for name, r in blob["results"].items():
        cv = r["cv"]
        out.append(
            f"| `{name}` | {_f(cv['site_accuracy'])} | {_f(cv['site_baseline_accuracy'])} | "
            f"{_f(cv['accuracy'])} | {cv['n_rounds']} | {cv['n_plant']} |"
        )
    return "\n".join(out)


def per_map_table(path: Path, config: str = "baseline") -> str:
    """Per-map site accuracy pooled over the holdout seeds of one config."""
    blob = json.loads(path.read_text())
    runs = blob["results"][config]["runs"]
    acc: dict[str, list] = {}
    for r in runs:
        for row in r.get("per_map") or []:
            acc.setdefault(row["map_id"], []).append(row)
    out = ["| Mapa | rondes al holdout | plants | site (A/B) | baseline A/B | 3 classes |",
           "|---|---|---|---|---|---|"]
    for m in sorted(acc, key=lambda k: -sum(r["n_plant"] for r in acc[k])):
        rows = acc[m]
        n_r = sum(r["n_rounds"] for r in rows) / len(rows)
        n_p = sum(r["n_plant"] for r in rows) / len(rows)
        site = [r["site_accuracy"] for r in rows if r["site_accuracy"] is not None]
        a3 = [r["accuracy"] for r in rows if r["accuracy"] is not None]
        bl = [r["site_baseline_accuracy"] for r in rows
              if r.get("site_baseline_accuracy") is not None]
        out.append(
            f"| {m} | {n_r:.0f} | {n_p:.0f} | "
            f"{_f(float(np.mean(site)) if site else None)} | "
            f"{_f(float(np.mean(bl)) if bl else None)} | "
            f"{_f(float(np.mean(a3)) if a3 else None)} |"
        )
    return "\n".join(out)


def lto_per_map_table(path: Path, config: str = "baseline") -> str:
    """Per-map site accuracy pooled over the leave-teams-out folds."""
    blob = json.loads(path.read_text())
    cv = blob["results"][config]["cv"]
    out = ["| Mapa | plants | site (A/B) | baseline A/B | rondes |",
           "|---|---|---|---|---|"]
    for r in sorted(cv["per_map"], key=lambda r: -r["n_plant"]):
        out.append(
            f"| {r['map_id']} | {r['n_plant']} | {_f(r['site_accuracy'])} | "
            f"{_f(r.get('site_baseline_accuracy'))} | {r['n_rounds']} |"
        )
    return "\n".join(out)


def lto_folds_table(path: Path, config: str = "baseline") -> str:
    blob = json.loads(path.read_text())
    cv = blob["results"][config]["cv"]
    out = ["| Fold | equips fora | rondes d'entrenament | rondes de test | plants | site (A/B) |",
           "|---|---|---|---|---|---|"]
    for i, f in enumerate(cv["folds"], 1):
        out.append(
            f"| {i} | {f['n_teams']} | {f['n_train']} | {f['n_rounds']} | "
            f"{f['n_plant']} | {_f(f['site_accuracy'])} |"
        )
    out.append(
        f"| **conjunt** | {cv['n_teams']} | — | {cv['n_rounds']} | "
        f"{cv['n_plant']} | **{_f(cv['site_accuracy'])}** |"
    )
    return "\n".join(out)


def main() -> None:
    base = Path(sys.argv[1] if len(sys.argv) > 1 else "/app/data_store/sweep")
    if (p := base / "configs.json").exists():
        print("### Configuracions (holdout 80/20)\n")
        print(holdout_table(p), "\n")
        print("### Per mapa (config per defecte)\n")
        print(per_map_table(p), "\n")
    if (p := base / "ablations.json").exists():
        print("### Ablacions (holdout 80/20)\n")
        print(holdout_table(p, "Ablació"), "\n")
    if (p := base / "lto.json").exists():
        print("### Configuracions (leave-teams-out)\n")
        print(lto_table(p), "\n")
        print("### Per mapa (leave-teams-out, config per defecte)\n")
        print(lto_per_map_table(p), "\n")
        print("### Folds de la config per defecte\n")
        print(lto_folds_table(p), "\n")
    if (p := base / "lto_ablations.json").exists():
        print("### Ablacions (leave-teams-out)\n")
        print(lto_table(p, "Ablació"), "\n")


if __name__ == "__main__":
    main()
