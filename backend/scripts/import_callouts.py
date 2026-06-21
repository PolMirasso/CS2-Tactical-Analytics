"""Import exact callout polygons from totalcsgo.com into
app/assets/callouts/<map>.json.

totalcsgo draws each callout as an SVG <polygon> in an 800x800 viewBox over the
standard Valve radar. That radar is the same one awpy ships (1024x1024), so a
callout pixel maps to world coords by: px = tcs * 1024/800, then the awpy
calibration (pos_x/pos_y/scale). Region (A/B/Mid) is taken from the name when it
is explicit, otherwise from proximity to the two bombsites.

Run: PYTHONPATH=. python scripts/import_callouts.py
"""
from __future__ import annotations

import html
import json
import math
import re
import urllib.request
from pathlib import Path

from app.analytics.maps import _CALIBRATION

_NAMES = {"mirage": "Mirage", "inferno": "Inferno", "dust2": "Dust II", "ancient": "Ancient",
          "anubis": "Anubis", "nuke": "Nuke", "train": "Train"}
SLUGS = list(_NAMES)
_SCALE_800_TO_1024 = 1024 / 800


def _fetch(slug: str) -> str:
    url = f"https://totalcsgo.com/callouts/{slug}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _parse(page: str) -> tuple[list[str], list[list[tuple[float, float]]]]:
    names = [html.unescape(m) for m in re.findall(r'data-copy="([^"]*)"', page)]
    polys = []
    for line in re.findall(r'<polygon points="([^"]*)"', page):
        nums = list(map(float, re.findall(r"-?\d+\.?\d*", line)))
        polys.append(list(zip(nums[0::2], nums[1::2])))
    return names, polys


def _centroid(poly):
    a = cx = cy = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cr = x0 * y1 - x1 * y0
        a += cr
        cx += (x0 + x1) * cr
        cy += (y0 + y1) * cr
    if a == 0:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    return (cx / (3 * a), cy / (3 * a))


def _region(name, centroid, a_c, b_c):
    if re.match(r"^A\b", name):
        return "A"
    if re.match(r"^B\b", name):
        return "B"
    if "mid" in name.lower():
        return "Mid"
    if a_c and b_c:
        da, db = math.dist(centroid, a_c), math.dist(centroid, b_c)
        ab = math.dist(a_c, b_c) or 1
        if abs(da - db) <= 0.2 * ab:
            return "Mid"
        return "A" if da < db else "B"
    return "Mid"


def import_map(slug: str, out_dir: Path) -> None:
    map_id = f"de_{slug}"
    pos_x, pos_y, scale = _CALIBRATION[map_id]
    names, polys = _parse(_fetch(slug))
    if len(names) != len(polys):
        raise SystemExit(f"{slug}: {len(names)} names vs {len(polys)} polygons")

    def to_world(poly):
        return [
            [round(pos_x + x * _SCALE_800_TO_1024 * scale, 1),
             round(pos_y - y * _SCALE_800_TO_1024 * scale, 1)]
            for x, y in poly
        ]

    world = [to_world(p) for p in polys]
    cents = [_centroid(w) for w in world]
    by_name = {n: cents[i] for i, n in enumerate(names)}
    a_c, b_c = by_name.get("A Site"), by_name.get("B Site")

    zones, seen = [], set()
    for name, poly, c in zip(names, world, cents):
        zid = f"{slug}_{re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')}"
        while zid in seen:
            zid += "_x"
        seen.add(zid)
        zones.append({"id": zid, "name": name, "region": _region(name, c, a_c, b_c), "polygon": poly})

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{map_id}.json").write_text(json.dumps({"id": map_id, "name": _NAMES[slug], "zones": zones}))
    print(f"{map_id}: {len(zones)} callouts")


if __name__ == "__main__":
    out_dir = Path(__file__).resolve().parent.parent / "app" / "assets" / "callouts"
    for s in SLUGS:
        import_map(s, out_dir)
