from __future__ import annotations

import math
from app.domain.enums import Region
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    region: Region
    centroid: tuple[float, float]


@dataclass(frozen=True)
class GameMap:
    id: str
    name: str
    zones: tuple[Zone, ...]

    def nearest_zone(self, x: float, y: float) -> Zone:
        return min(self.zones, key=lambda z: math.dist(z.centroid, (x, y)))


def _z(zid: str, name: str, region: Region, cx: float, cy: float) -> Zone:
    return Zone(id=zid, name=name, region=region, centroid=(cx, cy))


# de_mirage
_MIRAGE = GameMap(
    id="de_mirage",
    name="Mirage",
    zones=(
        _z("mirage_palace", "Palace", Region.A, -2250.0, -350.0),
        _z("mirage_ramp", "Ramp / Tetris", Region.A, -1500.0, -1500.0),
        _z("mirage_a_site", "A Site", Region.A, -1900.0, 600.0),
        _z("mirage_stairs", "Stairs", Region.A, -1050.0, -150.0),
        _z("mirage_mid", "Mid", Region.MID, 0.0, -600.0),
        _z("mirage_top_mid", "Top Mid", Region.MID, 350.0, 250.0),
        _z("mirage_window", "Window", Region.MID, -350.0, 350.0),
        _z("mirage_connector", "Connector", Region.MID, -750.0, 450.0),
        _z("mirage_apartments", "Apartments", Region.B, 1500.0, -250.0),
        _z("mirage_b_site", "B Site", Region.B, 2200.0, 600.0),
        _z("mirage_market", "Market", Region.B, 1900.0, -800.0),
    ),
)

# de_inferno
_INFERNO = GameMap(
    id="de_inferno",
    name="Inferno",
    zones=(
        _z("inferno_banana", "Banana", Region.B, 500.0, 2300.0),
        _z("inferno_b_site", "B Site", Region.B, 350.0, 3000.0),
        _z("inferno_mid", "Mid", Region.MID, 600.0, 700.0),
        _z("inferno_short", "Short / Mid Apts", Region.MID, 1300.0, 1100.0),
        _z("inferno_apartments", "Apartments", Region.A, 2100.0, 700.0),
        _z("inferno_arch", "Arch", Region.A, 1900.0, 200.0),
        _z("inferno_a_site", "A Site", Region.A, 2150.0, 1450.0),
        _z("inferno_pit", "Pit", Region.A, 2550.0, 1700.0),
        _z("inferno_t_ramp", "T Ramp", Region.MID, 1100.0, -400.0),
    ),
)

# pendiente agregar todos los mapas de la pool

_MAPS: dict[str, GameMap] = {m.id: m for m in (_MIRAGE, _INFERNO)}


def get_map(map_id: str) -> GameMap | None:
    return _MAPS.get(map_id)


def list_maps() -> list[GameMap]:
    return list(_MAPS.values())


def classify_point(map_id: str, x: float, y: float) -> Zone | None:
    """Return the nearest tactical zone for a world-space point, if the map exists."""
    game_map = _MAPS.get(map_id)
    return game_map.nearest_zone(x, y) if game_map else None


# radar assets — custom override (e.g. SimpleRadar) first, then awpy's bundled set
def radar_file(map_id: str) -> Path | None:
    """Path to the map's radar PNG.

    A user-supplied ``<map_id>.png`` in ``settings.radars_dir`` (drop SimpleRadar
    images there) wins over awpy's downloaded radar. Returns ``None`` if neither
    exists. The world→pixel calibration is identical for both, since SimpleRadar
    images are aligned to Valve's radar coordinate system.
    """
    from app.config import get_settings

    override = get_settings().radars_dir / f"{map_id}.png"
    if override.exists():
        return override
    try:
        from awpy.data import MAPS_DIR
    except Exception:
        return None
    path = Path(MAPS_DIR) / f"{map_id}.png"
    return path if path.exists() else None


# World→radar-pixel calibration (pos_x, pos_y, scale) for 1024×1024 radars.
# Static constants (sourced from awpy's map_data) so the transform works without
# downloading awpy assets at runtime — the values are fixed per map version.
_CALIBRATION: dict[str, tuple[float, float, float]] = {
    "de_ancient": (-2953.0, 2164.0, 5.0),
    "de_anubis": (-2796.0, 3328.0, 5.22),
    "de_dust2": (-2476.0, 3239.0, 4.4),
    "de_inferno": (-2087.0, 3870.0, 4.9),
    "de_mirage": (-3230.0, 1713.0, 5.0),
    "de_nuke": (-3453.0, 2887.0, 7.0),
    "de_overpass": (-4831.0, 1781.0, 5.2),
    "de_train": (-2308.0, 2078.0, 4.082077),
    "de_vertigo": (-3168.0, 1762.0, 4.0),
}


def calibration(map_id: str) -> dict | None:
    """World→radar-pixel calibration (pos_x, pos_y, scale) for the map, if known."""
    known = _CALIBRATION.get(map_id)
    if known is not None:
        pos_x, pos_y, scale = known
        return {"pos_x": pos_x, "pos_y": pos_y, "scale": scale}
    # Fall back to awpy's bundled data for any map not in the static table.
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
