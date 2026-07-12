from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from app.domain.enums import Region


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    region: Region
    bounds: tuple[float, float, float, float]  # world x_min, y_min, x_max, y_max
    # When set, the callout's true (non-rectangular) footprint; overrides bounds.
    polygon: tuple[tuple[float, float], ...] | None = None

    @property
    def centroid(self) -> tuple[float, float]:
        if self.polygon:
            return _polygon_centroid(self.polygon)
        x0, y0, x1, y1 = self.bounds
        return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)

    def contains(self, x: float, y: float) -> bool:
        if self.polygon:
            return _point_in_polygon(x, y, self.polygon)
        x0, y0, x1, y1 = self.bounds
        return x0 <= x <= x1 and y0 <= y <= y1


def _polygon_centroid(ring: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    """Area-weighted centroid of a simple polygon (shoelace)."""
    a = cx = cy = 0.0
    n = len(ring)
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    if a == 0:  # degenerate: fall back to vertex average
        return (sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n)
    return (cx / (3 * a), cy / (3 * a))


def _point_in_polygon(x: float, y: float, ring: tuple[tuple[float, float], ...]) -> bool:
    """Ray-casting test for a point against a simple polygon ring."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


@dataclass(frozen=True)
class GameMap:
    id: str
    name: str
    zones: tuple[Zone, ...]

    def zone_at(self, x: float, y: float) -> Zone:
        for z in self.zones:
            if z.contains(x, y):
                return z
        return min(self.zones, key=lambda z: math.dist(z.centroid, (x, y)))


def _bbox(poly):
    xs = [x for x, _ in poly]
    ys = [y for _, y in poly]
    return (min(xs), min(ys), max(xs), max(ys))


def _load_map(path: Path) -> GameMap:
    """Build a map from assets/callouts/<map>.json (polygons in 1024 pixel space)."""
    data = json.loads(path.read_text())
    zones = tuple(
        Zone(
            id=z["id"],
            name=z["name"],
            region=Region(z["region"]),
            bounds=_bbox(z["polygon"]),
            polygon=tuple((float(x), float(y)) for x, y in z["polygon"]),
        )
        for z in data["zones"]
    )
    return GameMap(id=data["id"], name=data["name"], zones=zones)


_CALLOUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "callouts"
_MAPS: dict[str, GameMap] = {
    m.id: m for m in (_load_map(p) for p in sorted(_CALLOUT_DIR.glob("de_*.json")))
}


def get_map(map_id: str) -> GameMap | None:
    return _MAPS.get(map_id)


def list_maps() -> list[GameMap]:
    return list(_MAPS.values())


def classify_point(map_id: str, x: float, y: float) -> Zone | None:
    game_map = _MAPS.get(map_id)
    if game_map is None:
        return None
    px, py = to_radar_pixel(map_id, x, y)
    return game_map.zone_at(px, py)


def to_radar_pixel(map_id: str, x: float, y: float) -> tuple[float, float]:
    """World (x, y) → 1024-space radar pixel using the map's calibration."""
    cal = _CALIBRATION.get(map_id)
    if cal is None:
        return x, y
    pos_x, pos_y, scale = cal
    return (x - pos_x) / scale, (pos_y - y) / scale


_BUNDLED_RADARS = Path(__file__).resolve().parent.parent / "assets" / "radars"


def radar_file(map_id: str) -> Path | None:
    """Map radar PNG: user override, then bundled, then awpy's downloaded set."""
    from app.config import get_settings

    override = get_settings().radars_dir / f"{map_id}.png"
    if override.exists():
        return override
    bundled = _BUNDLED_RADARS / f"{map_id}.png"
    if bundled.exists():
        return bundled
    try:
        from awpy.data import MAPS_DIR
    except Exception:
        return None
    path = Path(MAPS_DIR) / f"{map_id}.png"
    return path if path.exists() else None


# World→radar-pixel calibration (pos_x, pos_y, scale) for 1024×1024 radars.
_CALIBRATION: dict[str, tuple[float, float, float]] = {
    "de_ancient": (-2953.0, 2164.0, 5.0),
    "de_anubis": (-2796.0, 3328.0, 5.22),
    "de_cache": (-2000.0, 3250.0, 5.5),
    "de_dust2": (-2476.0, 3239.0, 4.4),
    "de_inferno": (-2087.0, 3870.0, 4.9),
    "de_mirage": (-3230.0, 1713.0, 5.0),
    "de_nuke": (-2568.0, 971.4, 5.3854),
    "de_train": (-2407.1, 2203.1, 4.3),
    "de_overpass": (-4831.0, 1781.0, 5.2),
    "de_vertigo": (-3900.9, 1257.9, 5.0),  # upper level (see _LOWER_LEVEL)
}


# Two-level maps: the SimpleRadar draws the lower level offset, so players below
_LOWER_LEVEL: dict[str, tuple[tuple[float, float, float], float]] = {
    # Lower level (B site) is drawn as the bottom-left inset of de_nuke.png.
    "de_nuke": ((-490.9, 2909.2, 5.2859), -495.0),
    # Vertigo draws the lower level as a second radar stacked below the upper.
    "de_vertigo": ((-3841.6, 3344.7, 4.8), 11700.0),
}


def lower_level_threshold(map_id: str) -> float | None:
    """World-z below which a point is on the lower level (nuke), None for single-level maps"""
    lower = _LOWER_LEVEL.get(map_id)
    return lower[1] if lower is not None else None


# SC4 damage grids
_BOMB_DAMAGE: dict[str, dict] = {
    "de_mirage": {"w": 412, "h": 351, "scale": 10, "origin": [-2655.0, -2605.0],
                  "sites": [{"label": "A", "center": [-440.0, -2150.0, -168.0],
                             "scalar": 1795, "quant": 40.255, "arrival_max": 10265},
                            {"label": "B", "center": [-2048.0, 256.0, -151.0],
                             "scalar": 2228, "quant": 43.208, "arrival_max": 11018}]},
    "de_dust2": {"w": 401, "h": 430, "scale": 10, "origin": [-2205.0, -1165.0],
                 "sites": [{"label": "A", "center": [1112.0, 2480.0, 144.0],
                            "scalar": 1929, "quant": 43.733, "arrival_max": 11152},
                           {"label": "B", "center": [-1536.0, 2680.0, 48.0],
                            "scalar": 3234, "quant": 44.506, "arrival_max": 11349}]},
    "de_inferno": {"w": 440, "h": 429, "scale": 10, "origin": [-1725.0, -765.0],
                   "sites": [{"label": "A", "center": [1976.0, 462.0, 180.0],
                              "scalar": 4043, "quant": 57.996, "arrival_max": 14789},
                             {"label": "B", "center": [352.0, 2768.0, 173.0],
                              "scalar": 2437, "quant": 51.502, "arrival_max": 13133}]},
    "de_cache": {"w": 514, "h": 385, "scale": 10, "origin": [-1825.0, -1525.0],
                 "sites": [{"label": "A", "center": [-48.0, -1300.0, 1677.0],
                            "scalar": 3071, "quant": 41.235, "arrival_max": 10515},
                           {"label": "B", "center": [-220.0, 1754.0, 1704.0],
                            "scalar": 2080, "quant": 43.584, "arrival_max": 11114}]},
    "de_ancient": {"w": 370, "h": 431, "scale": 10, "origin": [-2295.0, -2525.0],
                   "sites": [{"label": "A", "center": [-1392.0, 844.0, 68.0],
                              "scalar": 2875, "quant": 40.141, "arrival_max": 10236},
                             {"label": "B", "center": [887.0, 62.0, 144.0],
                              "scalar": 3060, "quant": 43.298, "arrival_max": 11041}]},
    "de_anubis": {"w": 379, "h": 499, "scale": 10, "origin": [-1975.0, -1805.0],
                  "sites": [{"label": "A", "center": [1238.0, 1954.0, -181.0],
                             "scalar": 2035, "quant": 44.353, "arrival_max": 11310},
                            {"label": "B", "center": [-1040.0, 694.0, -2.0],
                             "scalar": 1882, "quant": 38.631, "arrival_max": 9851}]},
    "de_overpass": {"w": 398, "h": 518, "scale": 10, "origin": [-3955.0, -3495.0],
                    "sites": [{"label": "A", "center": [-2136.0, 662.0, 506.0],
                               "scalar": 2263, "quant": 56.082, "arrival_max": 14301},
                              {"label": "B", "center": [-1104.0, 64.0, 108.0],
                               "scalar": 2758, "quant": 45.024, "arrival_max": 11481}]},
    "de_train": {"w": 398, "h": 359, "scale": 10, "origin": [-2175.0, -1795.0],
                 "sites": [{"label": "A", "center": [392.0, -108.0, -174.0],
                            "scalar": 1875, "quant": 47.157, "arrival_max": 12025},
                           {"label": "B", "center": [-40.0, -1292.0, -308.0],
                            "scalar": 1730, "quant": 43.482, "arrival_max": 11088}]},
    "de_vertigo": {"w": 276, "h": 273, "scale": 10, "origin": [-2625.0, -1610.0],
                   "sites": [{"label": "A", "center": [-2248.0, 798.0, 11758.0],
                              "scalar": 2590, "quant": 39.949, "arrival_max": 10187},
                             {"label": "B", "center": [-278.0, -621.0, 11792.0],
                              "scalar": 2371, "quant": 46.149, "arrival_max": 11768}]},
    # Two-level
    "de_nuke": {"w": 650, "h": 342, "scale": 10, "origin": [-2985.0, -2475.0],
                "has_lower": True,
                "sites": [{"label": "A", "center": [688.0, -720.0, -368.0],
                           "scalar": 1893, "quant": 50.02, "arrival_max": 12755},
                          {"label": "B", "center": [592.0, -1008.0, -748.0],
                           "scalar": 3332, "quant": 61.937, "arrival_max": 15794}]},
}

_BOMB_NEAR: list[tuple[float, float]] = [
    (0, 255), (0.091, 255), (0.204, 255), (0.295, 255), (0.408, 240), (0.499, 199),
    (0.589, 166), (0.703, 140), (0.794, 127), (0.907, 110), (0.997, 108), (1, 108),
]
_BOMB_TAIL_START = 108.0
_BOMB_TAIL_DEFAULT: list[tuple[float, float]] = [
    (100, 92), (300, 83), (500, 72), (700, 58), (900, 48), (1100, 35), (1300, 24),
    (1500, 13), (1720, 0),
]
_BOMB_TAILS: dict[tuple[str, str], list[tuple[float, float]]] = {
    ("de_ancient", "A"): [(75, 92), (275, 87), (475, 78), (675, 62), (875, 56), (1075, 41),
                          (1275, 28), (1475, 17), (1575, 10), (1730, 0)],
    ("de_ancient", "B"): [(90, 94), (290, 87), (490, 73), (690, 53), (890, 41), (1090, 34),
                          (1290, 27), (1490, 16), (1690, 2), (1860, 0)],
    ("de_anubis", "A"): [(15, 94), (215, 86), (415, 74), (615, 59), (815, 50), (1015, 40),
                         (1215, 25), (1415, 17), (1515, 9), (1690, 0)],
    ("de_anubis", "B"): [(68, 95), (268, 87), (468, 78), (668, 60), (868, 55), (1068, 37),
                         (1268, 24), (1468, 10), (1568, 2), (1610, 0)],
    ("de_cache", "A"): [(79, 85), (279, 77), (479, 59), (679, 53), (879, 41), (1079, 29),
                        (1279, 15), (1479, 6), (1570, 0)],
    ("de_cache", "B"): [(70, 85), (270, 82), (470, 64), (670, 54), (870, 43), (1070, 28),
                        (1270, 15), (1470, 6), (1540, 0)],
    ("de_dust2", "A"): [(21, 96), (221, 85), (421, 78), (621, 59), (821, 50), (1021, 37),
                        (1221, 25), (1421, 16), (1621, 6), (1710, 0)],
    ("de_dust2", "B"): [(16, 96), (216, 85), (416, 76), (616, 63), (816, 54), (1016, 41),
                        (1216, 29), (1416, 17), (1616, 10), (1750, 0)],
    ("de_inferno", "A"): [(107, 90), (307, 85), (507, 74), (707, 59), (907, 50), (1107, 37),
                          (1307, 22), (1507, 13), (1607, 7), (1710, 0)],
    ("de_inferno", "B"): [(13, 98), (213, 88), (413, 83), (613, 64), (813, 56), (1013, 44),
                          (1213, 32), (1413, 21), (1613, 9), (1770, 0)],
    ("de_mirage", "A"): [(55, 90), (255, 84), (455, 73), (655, 59), (855, 53), (1055, 37),
                         (1255, 23), (1455, 15), (1655, 3), (1700, 0)],
    ("de_mirage", "B"): [(22, 96), (222, 85), (422, 74), (622, 59), (822, 51), (1022, 36),
                         (1222, 26), (1422, 16), (1622, 6), (1710, 0)],
    ("de_nuke", "A"): [(57, 92), (257, 85), (457, 79), (657, 62), (857, 55), (1057, 41),
                       (1257, 28), (1457, 17), (1657, 7), (1740, 0)],
    ("de_nuke", "B"): [(18, 99), (218, 85), (418, 77), (618, 61), (818, 54), (1018, 40),
                       (1218, 28), (1418, 18), (1618, 5), (1690, 0)],
}


def _bomb_interp(curve: list[tuple[float, float]], x: float, start: float) -> float:
    """Piecewise-linear lookup; segments run from (0, start) through `curve`."""
    px, py = 0.0, start
    for cx, cy in curve:
        if x <= cx:
            return py + (cy - py) * ((x - px) / ((cx - px) or 1))
        px, py = cx, cy
    return float(curve[-1][1])


def _bomb_dmg_lut(map_id: str, label: str) -> list[int]:
    """256-entry PNG-gray -> HP table for one bomb site."""
    site = next(s for s in _BOMB_DAMAGE[map_id]["sites"] if s["label"] == label)
    tail = _BOMB_TAILS.get((map_id, label), _BOMB_TAIL_DEFAULT)
    max_dist = site["scalar"] + tail[-1][0]
    out: list[int] = []
    for gray in range(256):
        dist = gray * site["quant"] * (max_dist / site["arrival_max"])
        if dist <= site["scalar"]:
            hp = _bomb_interp(_BOMB_NEAR, dist / site["scalar"], 255.0)
        else:
            hp = _bomb_interp(tail, dist - site["scalar"], _BOMB_TAIL_START)
        out.append(math.floor(hp + 0.5))  # JS Math.round (half up), not banker's
    return out


_BOMB_DIR = Path(__file__).resolve().parent.parent / "assets" / "bomb"


def bomb_damage_meta(map_id: str) -> dict | None:
    """Grid, bomb-site centres and gray->HP tables for the C4 damage overlay."""
    meta = _BOMB_DAMAGE.get(map_id)
    if meta is None:
        return None
    return {
        "w": meta["w"], "h": meta["h"], "scale": meta["scale"], "origin": meta["origin"],
        "has_lower": meta.get("has_lower", False),
        "sites": [{"label": s["label"], "center": s["center"],
                   "dmg": _bomb_dmg_lut(map_id, s["label"])} for s in meta["sites"]],
    }


def bomb_overlay_file(map_id: str, site: str) -> Path | None:
    """Grayscale+alpha arrival field for a map's A/B site, or None if missing."""
    meta = _BOMB_DAMAGE.get(map_id)
    if meta is None:
        return None
    valid = {"a", "b"} | ({"a_lower", "b_lower"} if meta.get("has_lower") else set())
    if site not in valid:
        return None
    path = _BOMB_DIR / f"{map_id}_{site}.png"
    return path if path.exists() else None


def calibration(map_id: str) -> dict | None:
    known = _CALIBRATION.get(map_id)
    if known is not None:
        pos_x, pos_y, scale = known
        out = {"pos_x": pos_x, "pos_y": pos_y, "scale": scale}
        lower = _LOWER_LEVEL.get(map_id)
        if lower is not None:
            (lx, ly, ls), z_max = lower
            out["lower"] = {"pos_x": lx, "pos_y": ly, "scale": ls}
            out["lower_level_max_units"] = z_max
        return out
    try:
        from awpy.data.map_data import MAP_DATA
    except Exception:
        return None
    data = MAP_DATA.get(map_id)
    if not data:
        return None
    try:
        return {
            "pos_x": float(data["pos_x"]),
            "pos_y": float(data["pos_y"]),
            "scale": float(data["scale"]),
        }
    except (KeyError, TypeError, ValueError):
        return None
