# Which bombsite a round without a plant was heading for

from __future__ import annotations

import math
from collections import Counter

from app.analytics.maps import classify_point

EARLY = 20.0 # seconds before the round ends for the first reading
LATE = 12.0 # and the second, which has to agree
SPAWN_R = 400.0 # a player who has not left this radius is not going anywhere yet
MARGIN = 2 # how many more players one site needs than the other
MIN_T = 5.0 # no reading before the round is this old


def _frame_at(rnd: dict, tau: float) -> dict | None:
    best = None
    for f in rnd["frames"]:
        if f["t"] <= tau:
            best = f
        else:
            break
    return best


def _players_call(map_id: str, rnd: dict, tau: float, slots, spawn) -> str | None:
    f = _frame_at(rnd, tau)
    if f is None:
        return None
    votes: Counter[str] = Counter()
    for i in slots:
        p = f["pos"][i]
        if len(p) < 4 or p[3] <= 0:
            continue
        sx, sy = spawn.get(i, (p[0], p[1]))
        if math.dist((p[0], p[1]), (sx, sy)) < SPAWN_R:
            continue
        zone = classify_point(map_id, p[0], p[1], p[4] if len(p) >= 5 else None)
        if zone is not None:
            votes[zone.region.value] += 1
    a, b = votes.get("A", 0), votes.get("B", 0)
    if abs(a - b) < MARGIN:
        return None
    return "A" if a > b else "B"


def _bomb_call(map_id: str, rnd: dict, tau: float, events) -> str | None:
    prior = [e for e in events if e["t"] <= tau]
    if not prior:
        return None
    last = prior[-1]
    if last["e"] == "drop":
        x, y, z = last["x"], last["y"], last.get("z")
    else:  # carried: the holder's position is the bomb's
        slot = last.get("p")
        f = _frame_at(rnd, tau)
        if slot is None or f is None or slot >= len(f["pos"]):
            return None
        p = f["pos"][slot]
        if len(p) < 4 or p[3] <= 0:  # holder died, the drop is not recorded yet
            return None
        x, y, z = p[0], p[1], (p[4] if len(p) >= 5 else None)
    zone = classify_point(map_id, float(x), float(y), float(z) if z is not None else None)
    if zone is None:
        return None
    return zone.region.value if zone.region.value in ("A", "B") else None


def _stable(read, ref: float) -> str | None:
    """The same call at both instants, or nothing."""
    if ref - EARLY < MIN_T:
        return None
    early = read(ref - EARLY)
    if early is None:
        return None
    return early if early == read(ref - LATE) else None


def intended_site(map_id: str, replay_round: dict) -> str | None:
    """``"A"``/``"B"`` if the round reads clearly, else ``None``. Reads the replay
    artifact, so it needs neither the ``.dem`` nor the database."""
    frames = replay_round.get("frames") or []
    if not frames:
        return None
    slots = [i for i, p in enumerate(replay_round.get("players") or []) if p["side"] == "t"]
    if len(slots) != 5:
        return None
    f0 = frames[0]
    spawn = {i: (f0["pos"][i][0], f0["pos"][i][1]) for i in slots}
    events = sorted(replay_round.get("bomb_events") or [], key=lambda e: e["t"])
    end = frames[-1]["t"]

    players = _stable(lambda t: _players_call(map_id, replay_round, t, slots, spawn), end)
    if players is not None:
        return players
    return _stable(lambda t: _bomb_call(map_id, replay_round, t, events), end)
