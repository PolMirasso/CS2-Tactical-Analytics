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

_BUY = {
    "pistol": "pistol round",
    "full_eco": "full eco (saving)",
    "eco": "eco",
    "ak_hero": "eco plus one AK-47",
    "m4_hero": "eco plus one M4",
    "awp_hero": "eco plus one AWP",
    "force": "force buy",
    "full": "full buy",
}


def questions(*, context: bool = False, shots: bool = False) -> dict[str, dict]:
    """The three choice questions; ``context``/``shots`` name the extra inputs in the prompt"""
    given = f"the T side's utility this round {_ABOUT}"
    if context:
        given += ", the phase of the match and both teams' economy and weapons"
    if shots:
        given += ", and how similar rounds by other teams on this map ended"
    return {
        "site": {
            "type": "choice",
            "instructions": f"Given {given}, which bombsite are they executing on?",
            "criteria": {"A": "Bombsite A", "B": "Bombsite B"},
        },
        "plant": {
            "type": "choice",
            "instructions": f"Given {given}, will they plant the bomb?",
            "criteria": {
                "plant": "They commit to a site and plant the bomb",
                "no_plant": "They don't plant: save, eco, or an execute that fails or is abandoned",
            },
        },
        "timing": {
            "type": "choice",
            "instructions": f"Given {given}, if they plant, when in the round do they plant?",
            "criteria": {
                "rush": f"Plant within the first {_TIMING_RUSH_MAX_S:.0f} s of the round",
                "default": f"Plant between {_TIMING_RUSH_MAX_S:.0f} and {_TIMING_LATE_MIN_S:.0f} s",
                "late": f"Plant after {_TIMING_LATE_MIN_S:.0f} s",
            },
        },
    }


QUESTIONS = questions()


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


def clef_round(
    *,
    phase: str,
    team: str | None,
    opponent: str | None,
    buy_type: str | None,
    equip_value: int | None,
    opponent_buy_type: str | None,
    opponent_equip_value: int | None,
    team_weapons: str | None,
    opponent_weapons: str | None,
) -> dict:
    """The round context the other models get: phase, teams, and both sides' economy and weapons"""
    def side(name, buy, equip, weapons):
        return {"team": name or "?", "buy": _BUY.get(buy, buy or "?"),
                "equipment_value": equip,
                "weapons": ", ".join(w for w in (weapons or "").split(",") if w) or "?"}
    return {
        "phase": phase.replace("_", " "),
        "T": side(team, buy_type, equip_value, team_weapons),
        "CT": side(opponent, opponent_buy_type, opponent_equip_value, opponent_weapons),
    }


def clef_example(state: dict, target: str, intent: str | None,
                 plant_time_s: float | None, round_info: dict | None = None) -> dict:
    """A labelled round in a compact form, so several fit in the context"""
    if target in ("A", "B"):
        outcome = f"planted {target} at {plant_time_s:.0f} s"
    elif intent in ("A", "B"):
        outcome = f"no plant (went towards {intent})"
    else:
        outcome = "no plant"
    utility = [f"{g['type']} {g['callout']} {g['time_s']}s"
               for g in state["utility_thrown_by_T_so_far"]]
    example: dict = {"utility": utility, "outcome": outcome}
    if round_info:
        example["buys"] = f"T {round_info['T']['buy']}, CT {round_info['CT']['buy']}"
    return example


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
