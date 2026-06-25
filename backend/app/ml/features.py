from __future__ import annotations

from app.domain.enums import Region, Site, UtilityType

# Canonical label order for the softmax output.
SITES: list[str] = [s.value for s in Site]

_REGIONS = [r.value for r in Region]  # A, B, Mid
_UTILS = [u.value for u in UtilityType]  # smoke, flash, molotov, he

_EQUIP_NORM = 25_000.0
# Grenades thrown within this many seconds of freeze-end count as "opening" util.
_OPENING_WINDOW_S = 15.0


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


def round_features(
    *,
    map_id: str | None,
    team: str | None,
    opponent: str | None,
    buy_type: str | None,
    equip_value: float | int | None,
    utility,
) -> dict[str, float | str]:
    """One round → the model's feature dict (shared by training and inference).

    Only T-side utility is considered (the executing side). Categorical keys
    (map/team/opponent/buy) are left as strings for the DictVectorizer to one-hot.
    """
    feats: dict[str, float | str] = {
        "map": map_id or "?",
        "team": team or "?",
        "opponent": opponent or "?",
        "buy": buy_type or "?",
        "equip": float(equip_value or 0) / _EQUIP_NORM,
    }
    for r in _REGIONS:
        for u in _UTILS:
            feats[f"r_{r}_{u}"] = 0.0
    for u in _UTILS:
        feats[f"u_{u}"] = 0.0

    times: list[float] = []
    n_total = 0
    n_opening = 0
    for ev in utility or []:
        if _side(ev) != "t":
            continue
        util = _norm_util(_attr(ev, "util_type"))
        if util is None:
            continue
        region = _attr(ev, "region")
        t = float(_attr(ev, "round_time_s") or 0.0)
        n_total += 1
        feats[f"u_{util}"] += 1.0
        if region in _REGIONS:
            feats[f"r_{region}_{util}"] += 1.0
        times.append(t)
        if t <= _OPENING_WINDOW_S:
            n_opening += 1

    feats["n_util"] = float(n_total)
    feats["n_opening"] = float(n_opening)
    feats["t_min"] = min(times) if times else 0.0
    feats["t_mean"] = (sum(times) / len(times)) if times else 0.0
    return feats
