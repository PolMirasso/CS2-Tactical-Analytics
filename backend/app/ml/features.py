from __future__ import annotations

from app.analytics.maps import get_map, list_maps, lower_level_threshold
from app.domain.enums import Region, Site, UtilityType
from app.domain.weapons import WEAPON_IDS

_WEAPON_NEUTRAL = 0.5

# Canonical label order for the softmax output
SITES: list[str] = [s.value for s in Site if s is not Site.MID]

# Execution-timing classes
TIMINGS: list[str] = ["rush", "default", "late"]
# Tactical thresholds on the plant time
_TIMING_RUSH_MAX_S = 35.0
_TIMING_LATE_MIN_S = 70.0

_REGIONS = [r.value for r in Region]  # A, B, Mid
_UTILS = [u.value for u in UtilityType]  # smoke, flash, molotov, he
_MAP_ORDER = [m.id for m in list_maps()]

_EQUIP_NORM = 25_000.0
ROUND_TIME_S = 115.0
# Grenades thrown within this many seconds of freeze-end count as "opening" util.
_OPENING_WINDOW_S = 15.0

# per-utility token = [smoke, flash, molotov, he, x01, y01, t01, z_lvl, map one-hot]
TOKEN_DIM = len(_UTILS) + 4 + len(_MAP_ORDER)

_Z_LVL_NEUTRAL = 0.5


def _attr(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def _norm_util(raw) -> str | None:
    s = str(raw or "").lower()
    return s if s in _UTILS else None


def _side(ev) -> str:
    # UtilityEvent stores the throwing side in ``team``; UtilityInput uses ``side``.
    return str(_attr(ev, "side") or _attr(ev, "team") or "t").lower()


def _event_time(ev) -> float:
    """Representative throw time (s into the round)"""
    lo = _attr(ev, "time_from")
    hi = _attr(ev, "time_to")
    if lo is not None and hi is not None:
        return (float(lo) + float(hi)) / 2.0
    if lo is not None:
        return float(lo)
    if hi is not None:
        return float(hi)
    return float(_attr(ev, "round_time_s") or 0.0)


def _radar_pos(map_id: str | None, ev) -> tuple[float, float] | None:
    """Utility position in 1024-space radar pixels"""
    rx, ry = _attr(ev, "radar_x"), _attr(ev, "radar_y")
    if rx is None or ry is None:
        rx, ry = _attr(ev, "x"), _attr(ev, "y")
    if rx is not None and ry is not None:
        return float(rx), float(ry)

    game_map = get_map(map_id or "")
    if game_map is None:
        return None
    zid = _attr(ev, "zone")
    if zid is not None:
        for z in game_map.zones:
            if z.id == zid:
                return z.centroid
    region = _attr(ev, "region")
    if region is not None:
        cs = [z.centroid for z in game_map.zones if z.region.value == region]
        if cs:
            return (sum(c[0] for c in cs) / len(cs), sum(c[1] for c in cs) / len(cs))
    return None


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def timing_label(plant_time_s: float | None) -> str | None:
    """rush / default / late from the plant time"""
    if plant_time_s is None:
        return None
    t = float(plant_time_s)
    if t <= _TIMING_RUSH_MAX_S:
        return "rush"
    if t > _TIMING_LATE_MIN_S:
        return "late"
    return "default"


def _z_level(map_id: str | None, ev) -> float:
    """Per-token height feature: 1=lower level, 0=upper, 0.5=unknown/single-level (nuke)"""
    threshold = lower_level_threshold(map_id or "")
    if threshold is None:
        return _Z_LVL_NEUTRAL
    z = _attr(ev, "z")
    if z is None:
        return _Z_LVL_NEUTRAL
    return 1.0 if float(z) < threshold else 0.0


def round_tokens(map_id: str | None, utility) -> list[list[float]]:
    """One round is a set of per-utility tokens (only T-side opening util)"""
    map_oh = [1.0 if map_id == m else 0.0 for m in _MAP_ORDER]
    tokens: list[list[float]] = []
    for ev in utility or []:
        if _side(ev) != "t":
            continue
        util = _norm_util(_attr(ev, "util_type"))
        if util is None:
            continue
        one_hot = [1.0 if util == u else 0.0 for u in _UTILS]
        pos = _radar_pos(map_id, ev)
        if pos is None:
            x01 = y01 = 0.5  # unknown location → centre of the radar
        else:
            x01, y01 = _clamp01(pos[0] / 1024.0), _clamp01(pos[1] / 1024.0)
        t01 = _clamp01(_event_time(ev) / ROUND_TIME_S)
        z_lvl = _z_level(map_id, ev)
        tokens.append([*one_hot, x01, y01, t01, z_lvl, *map_oh])
    return tokens


def _equip_scalar(equip_value: float | int | None) -> float:
    if equip_value is None:
        return _WEAPON_NEUTRAL
    return float(equip_value) / _EQUIP_NORM


def _emit_weapons(
    ctx: dict[str, float | str], prefix: str, present: str | None, query: str | None
) -> None:
    # training: present set ⇒ 1.0 each; inference: query ⇒ 1.0, rest neutral (as z_lvl)
    if present is not None:
        for wid in present.split(","):
            if wid:
                ctx[f"w_{prefix}_{wid}"] = 1.0
        return
    for wid in WEAPON_IDS:
        ctx[f"w_{prefix}_{wid}"] = 1.0 if wid == query else _WEAPON_NEUTRAL


def round_context(
    *,
    map_id: str | None,
    team: str | None,
    opponent: str | None,
    buy_type: str | None,
    equip_value: float | int | None,
    utility,
    opponent_buy_type: str | None = None,
    opponent_equip_value: float | int | None = None,
    team_weapons: str | None = None,
    opponent_weapons: str | None = None,
    team_weapon: str | None = None,
    opponent_weapon: str | None = None,
) -> dict[str, float | str]:
    """Round-level context fed to the DeepSets head alongside the pooled set.
    Categorical keys (map/team/opponent/buy/opp_buy) stay strings for the
    DictVectorizer to one-hot; the rest are normalised scalars
    """
    ctx: dict[str, float | str] = {
        "map": map_id or "?",
        "team": team or "?",
        "opponent": opponent or "?",
        "buy": buy_type or "?",
        "equip": _equip_scalar(equip_value),
        "opp_buy": opponent_buy_type or "?",
        "opp_equip": _equip_scalar(opponent_equip_value),
    }
    _emit_weapons(ctx, "t", team_weapons, team_weapon)
    _emit_weapons(ctx, "ct", opponent_weapons, opponent_weapon)
    for u in _UTILS:
        ctx[f"u_{u}"] = 0.0

    times: list[float] = []
    n_total = 0
    n_opening = 0
    for ev in utility or []:
        if _side(ev) != "t":
            continue
        util = _norm_util(_attr(ev, "util_type"))
        if util is None:
            continue
        t = _event_time(ev)
        n_total += 1
        ctx[f"u_{util}"] += 1.0
        times.append(t)
        if t <= _OPENING_WINDOW_S:
            n_opening += 1

    ctx["n_util"] = float(n_total)
    ctx["n_opening"] = float(n_opening)
    ctx["t_min"] = (min(times) / ROUND_TIME_S) if times else 0.0
    ctx["t_mean"] = (sum(times) / len(times) / ROUND_TIME_S) if times else 0.0
    return ctx
