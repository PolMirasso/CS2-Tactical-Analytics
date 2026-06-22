"""One-shot: re-project callout polygons from totalcsgo's 800-space onto the
bundled Valve radar's 1024 pixel space, so /maps can overlay them on the radar.

Per map we map the polygons' bounding box onto the radar image's opaque (map
silhouette) bounding box with an axis-aligned affine. Both boxes are the same
map's silhouette, so the fit is close; fine-tune the rest in the /edit editor.
Nuke is two-level on totalcsgo and won't line up — recalibrate it by hand.

Run once: backend/.venv/bin/python scripts/recalibrate_callouts.py
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CALLOUT_DIR = ROOT / "app" / "assets" / "callouts"
RADAR_DIR = ROOT / "app" / "assets" / "radars"


def opaque_bbox(png: Path) -> tuple[int, int, int, int]:
    im = Image.open(png).convert("RGBA")
    bbox = im.getchannel("A").getbbox()  # (x0, y0, x1, y1) of non-zero alpha
    if bbox is None:
        return (0, 0, im.width, im.height)
    return bbox


def poly_bbox(zones) -> tuple[float, float, float, float]:
    xs = [x for z in zones for x, _ in z["polygon"]]
    ys = [y for z in zones for _, y in z["polygon"]]
    return (min(xs), min(ys), max(xs), max(ys))


def main() -> None:
    for jpath in sorted(CALLOUT_DIR.glob("de_*.json")):
        data = json.loads(jpath.read_text())
        map_id = data["id"]
        radar = RADAR_DIR / f"{map_id}.png"
        if not radar.exists():
            print(f"{map_id}: no radar, skipped")
            continue

        rx0, ry0, rx1, ry1 = opaque_bbox(radar)
        px0, py0, px1, py1 = poly_bbox(data["zones"])
        sx = (rx1 - rx0) / (px1 - px0)
        sy = (ry1 - ry0) / (py1 - py0)
        tx = rx0 - sx * px0
        ty = ry0 - sy * py0

        for z in data["zones"]:
            z["polygon"] = [
                [round(sx * x + tx, 1), round(sy * y + ty, 1)] for x, y in z["polygon"]
            ]

        jpath.write_text(json.dumps(data))
        print(f"{map_id}: radar bbox=({rx0},{ry0},{rx1},{ry1}) "
              f"sx={sx:.3f} sy={sy:.3f} tx={tx:.1f} ty={ty:.1f}")


if __name__ == "__main__":
    main()
