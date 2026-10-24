from __future__ import annotations

import json
import urllib.request

from app.analytics.maps import get_map
from app.ml.features import (
    _TIMING_LATE_MIN_S,
    _TIMING_RUSH_MAX_S,
    _attr,
    _event_time,
    _norm_util,
    _side,
)

DEFAULT_HOST = "http://localhost:11435"
DEFAULT_MODEL = "clef-2k"

_ABOUT = "(grenade type, callout where it landed, seconds into the round)"

QUESTIONS: dict[str, dict] = {
    "site": {
        "type": "choice",
        "instructions": f"Given the T side's utility this round {_ABOUT}, "
                        "which bombsite are they executing on?",
        "criteria": {"A": "Bombsite A", "B": "Bombsite B"},
    },
    "plant": {
        "type": "choice",
        "instructions": f"Given the T side's utility this round {_ABOUT}, "
                        "will they plant the bomb?",
        "criteria": {
            "plant": "They commit to a site and plant the bomb",
            "no_plant": "They don't plant: save, eco, or an execute that fails or is abandoned",
        },
    },
    "timing": {
        "type": "choice",
        "instructions": f"Given the T side's utility this round {_ABOUT}, "
                        "if they plant, when in the round do they plant?",
        "criteria": {
            "rush": f"Plant within the first {_TIMING_RUSH_MAX_S:.0f} s of the round",
            "default": f"Plant between {_TIMING_RUSH_MAX_S:.0f} and {_TIMING_LATE_MIN_S:.0f} s",
            "late": f"Plant after {_TIMING_LATE_MIN_S:.0f} s",
        },
    },
}


def clef_state(map_id: str | None, utility) -> dict:
    """The round as Clef reads it: T-side grenades by time, each with its callout name"""
    game_map = get_map(map_id or "")
    names = {z.id: z.name for z in game_map.zones} if game_map else {}
    grenades = []
    for ev in sorted(utility or [], key=_event_time):
        if _side(ev) != "t":
            continue
        util = _norm_util(_attr(ev, "util_type"))
        if util is None:
            continue
        zid = _attr(ev, "zone")
        grenades.append({"type": util, "callout": names.get(zid, zid),
                         "time_s": round(_event_time(ev))})
    return {
        "game": "Counter-Strike 2",
        "map": game_map.name if game_map else (map_id or "?"),
        "side": "T (attackers)",
        "utility_thrown_by_T_so_far": grenades,
    }


def ask(
    state: dict,
    *,
    host: str = DEFAULT_HOST,
    model: str = DEFAULT_MODEL,
    questions: dict[str, dict] = QUESTIONS,
    timeout: float = 1800.0,
) -> dict:
    """One /v1/systemone call; returns Clef's raw ``answers`` plus ``usage``"""
    body = {"model": model, "state": state, "questions": questions}
    req = urllib.request.Request(
        f"{host}/v1/systemone", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        out = json.loads(resp.read())
    return {"answers": out["answers"], "usage": out.get("usage", {})}
