"""Rebuild the C4 damage overlays of the two-level maps from skinsniper's 3D voxels.

Their published 2D field flattens every height into one image, so on a two-level map
the heat lands on the wrong floor. Here each level is flattened on its own.

Run: backend/.venv/bin/python scripts/regen_vox_bomb.py <de_nuke|de_vertigo> [vox.bin]
"""
from __future__ import annotations

import gzip
import sys
import urllib.request
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
BOMB_DIR = ROOT / "app" / "assets" / "bomb"
RADAR_DIR = ROOT / "app" / "assets" / "radars"

# z_split: below it is the lower level. upper_cap: without it nuke also paints the
# rafters, roofs and silo top the radar never draws. sites: vox order -> our labels,
# reversed on vertigo because skinsniper has its A/B the wrong way round.
MAPS: dict[str, dict] = {
    "de_nuke": {
        "sid": "nuke",
        "w": 650, "h": 342, "n": 100764, "zmin": -765,
        "origin": (-2985.0, -2475.0),
        "upper_cal": (-2568.0, 971.4, 5.3854),
        "lower_cal": (-490.9, 2909.2, 5.2859),
        "z_split": -495.0,
        "upper_cap": -250.0,
        "fill_holes": True,
        "sites": ("a", "b"),
    },
    "de_vertigo": {
        "sid": "vertigo",
        "w": 276, "h": 273, "n": 63157, "zmin": 11495,
        "origin": (-2625.0, -1610.0),
        "upper_cal": (-3900.9, 1257.9, 5.0),
        "lower_cal": (-3841.6, 3344.7, 4.8),
        "z_split": 11700.0,
        "upper_cap": None,
        "fill_holes": False,
        "sites": ("b", "a"),
    },
}

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")


def load_vox(sid: str, local: str | None) -> bytes:
    if local:
        data = Path(local).read_bytes()
    else:
        url = f"https://skinsniper.com/img/bomb/{sid}-vox.bin"
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        data = urllib.request.urlopen(req).read()
    return gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data


def flood(mask: np.ndarray, seeds: deque, w: int, h: int) -> np.ndarray:
    seen = np.zeros_like(mask)
    for s in seeds:
        seen[s] = True
    while seeds:
        y, x = seeds.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < h and 0 <= xx < w and mask[yy, xx] and not seen[yy, xx]:
                seen[yy, xx] = True
                seeds.append((yy, xx))
    return seen


def flatten(cfg: dict, arr: np.ndarray, cell_t: np.ndarray, sel: np.ndarray,
            rlum: np.ndarray, cal: tuple[float, float, float]) -> np.ndarray:
    w, h = cfg["w"], cfg["h"]
    ox, oy = cfg["origin"]
    gray = np.full(w * h, 256, int)
    np.minimum.at(gray, cell_t[sel], arr[sel])
    gray = gray.reshape(h, w)
    occ = gray < 256

    # Enclosed holes get the min neighbouring gray when they are prop-sized, or medium
    # but drawn light on the radar (nuke's A-plant crates). Big dark voids — the roof
    # gaps the radar draws dark — are real, and stay unheated.
    if cfg["fill_holes"]:
        border = deque((y, x) for x in range(w) for y in (0, h - 1) if not occ[y, x])
        border.extend((y, x) for y in range(h) for x in (0, w - 1) if not occ[y, x])
        holes = ~occ & ~flood(~occ, border, w, h)

        lbl = np.zeros((h, w), int)
        cur = 0
        for y, x in zip(*np.nonzero(holes), strict=True):
            if lbl[y, x]:
                continue
            cur += 1
            comp = flood(holes & (lbl == 0), deque([(y, x)]), w, h)
            lbl[comp] = cur
            ys, xs = np.nonzero(comp)
            px = np.clip(np.round((ox + xs * 10 - cal[0]) / cal[2]).astype(int), 0, 1023)
            py = np.clip(np.round((cal[1] - (oy + ys * 10)) / cal[2]).astype(int), 0, 1023)
            if not (len(ys) <= 120 or (len(ys) <= 600 and rlum[py, px].mean() > 90)):
                continue
            todo = comp.copy()
            while todo.any():
                done = np.zeros((h, w), bool)
                for hy, hx in zip(*np.nonzero(todo), strict=True):
                    best = 256
                    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        yy, xx = hy + dy, hx + dx
                        if 0 <= yy < h and 0 <= xx < w and occ[yy, xx] and not todo[yy, xx]:
                            best = min(best, gray[yy, xx])
                    if best < 256:
                        gray[hy, hx] = best
                        done[hy, hx] = True
                if not done.any():
                    break
                occ |= done
                todo &= ~done

    out = np.zeros((h, w, 2), np.uint8)
    out[..., 0] = np.where(occ, gray, 0)
    out[..., 1] = np.where(occ, 255, 0)
    return out[::-1]  # vox rows grow north; PNG row 0 is the top


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in MAPS:
        sys.exit(f"usage: regen_vox_bomb.py <{'|'.join(MAPS)}> [vox.bin]")
    map_id = sys.argv[1]
    cfg = MAPS[map_id]
    w, h, n = cfg["w"], cfg["h"], cfg["n"]

    raw = load_vox(cfg["sid"], sys.argv[2] if len(sys.argv) > 2 else None)
    assert len(raw) == w * h + n * 3, f"vox size mismatch: {len(raw)}"
    b = np.frombuffer(raw, np.uint8)
    count = b[: w * h].astype(int)
    z = cfg["zmin"] + b[w * h : w * h + n].astype(int) * 10
    cell_t = np.repeat(np.arange(w * h), count)
    rlum = (np.asarray(Image.open(RADAR_DIR / f"{map_id}.png").convert("RGBA")
                       .resize((1024, 1024)))[..., :3].astype(float)
            * [0.299, 0.587, 0.114]).sum(-1)

    split = cfg["z_split"]
    cap = cfg["upper_cap"]
    in_upper = z >= split if cap is None else (z >= split) & (z <= cap)

    for i, site in enumerate(cfg["sites"]):
        arr = b[w * h + n * (1 + i) : w * h + n * (2 + i)].astype(int)
        upper = flatten(cfg, arr, cell_t, in_upper, rlum, cfg["upper_cal"])
        lower = flatten(cfg, arr, cell_t, z < split, rlum, cfg["lower_cal"])
        Image.fromarray(upper, "LA").save(BOMB_DIR / f"{map_id}_{site}.png")
        Image.fromarray(lower, "LA").save(BOMB_DIR / f"{map_id}_{site}_lower.png")
        print(f"{map_id}_{site}: upper cells {int((upper[..., 1] > 0).sum())}, "
              f"lower cells {int((lower[..., 1] > 0).sum())}")


if __name__ == "__main__":
    main()
