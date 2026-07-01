from __future__ import annotations

import json
import math
from app.domain.enums import Region
from dataclasses import dataclass
from pathlib import Path


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
