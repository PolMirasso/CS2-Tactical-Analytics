"""Build 2D-replay data (player frames + grenade trajectories) for a demo.

The viewer needs the position of every player over time plus where each piece of
utility was thrown from and where it landed. awpy already exposes this in its
per-tick ``ticks`` frame and per-tick ``grenades`` frame; here we downsample it
to a handful of frames per second so the payload stays small (a full match is a
few MB raw, well under 1 MB gzipped) and serialise it to a plain dict that the
service writes as a gzip-JSON artifact.

Player positions are world-space; the frontend turns them into radar pixels with
the per-map calibration (``pos_x``/``pos_y``/``scale``) served by the maps API.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.analytics.maps import GameMap, get_map, list_maps

# Frames per second kept in the artifact. 8 Hz is smooth enough for a 2D radar
# replay and keeps a ~100 s round around a few hundred frames.
SAMPLE_HZ = 8.0


@dataclass
class PlayerSlot:
    steamid: str
    name: str
    side: str  # "t" / "ct"
    color: int = -1  # in-game teammate-colour index


@dataclass
class Frame:
    t: float  # seconds since the round went live (freeze end)
    # One [x, y, yaw, hp, z] per player, aligned to the round's ``players`` roster.
    # z (world height) lets the viewer pick the right level on two-level maps.
    pos: list[list[float]]
    # One [armor, money, weapon_idx] per player (same roster order). Discrete
    # scoreboard stats — not interpolated; ``weapon_idx`` indexes the round's
    # ``weapons`` string table.
    st: list[list[int]] = field(default_factory=list)


@dataclass
class UtilityShot:
    util_type: str
    side: str
    t: float
    from_xy: tuple[float, float]
    to_xy: tuple[float, float]
    to_z: float = 0.0  # landing height, to pick the level on two-level maps
    path: list[tuple[float, float, float]] = field(default_factory=list)


@dataclass
class ReplayRound:
    round_number: int
    duration_s: float
    players: list[PlayerSlot]
    frames: list[Frame] = field(default_factory=list)
    utility: list[UtilityShot] = field(default_factory=list)
    # Per-round weapon-name table; ``Frame.st`` weapon indices point here.
    # Index 0 is always "" (no/unknown weapon, e.g. dead players).
    weapons: list[str] = field(default_factory=lambda: [""])
    # Shot events as ``[player_idx, t]`` (t seconds since freeze end); drives the
    # muzzle-flash "firing" indicator in the viewer.
    fires: list[list[float]] = field(default_factory=list)
    # Bomb plant for the round: ``{t, x, y, site}`` (world-space), or ``None``.
    bomb: dict | None = None
    # Kill events for the kill feed: {t, atk, as, vic, vs, wp, hs} plus optional air no-scope.
    kills: list[dict] = field(default_factory=list)
    winner: str | None = None  # "ct" | "t"


@dataclass
class ReplayData:
    map_id: str
    sample_hz: float
    rounds: list[ReplayRound] = field(default_factory=list)


# serialisation
def replay_to_dict(replay: ReplayData) -> dict:
    return {
        "map_id": replay.map_id,
        "sample_hz": replay.sample_hz,
        "rounds": [_round_to_dict(r) for r in replay.rounds],
    }


def _round_to_dict(r: ReplayRound) -> dict:
    return {
        "round_number": r.round_number,
        "duration_s": round(r.duration_s, 2),
        "players": [
            {"steamid": p.steamid, "name": p.name, "side": p.side, "ci": p.color} for p in r.players
        ],
        "weapons": r.weapons,
        "fires": r.fires,
        "bomb": r.bomb,
        "kills": r.kills,
        "winner": r.winner,
        "frames": [{"t": round(f.t, 2), "pos": f.pos, "st": f.st} for f in r.frames],
        "utility": [
            {
                "type": u.util_type,
                "side": u.side,
                "t": round(u.t, 2),
                "from": [round(u.from_xy[0], 1), round(u.from_xy[1], 1)],
                "to": [round(u.to_xy[0], 1), round(u.to_xy[1], 1)],
                "z": round(u.to_z),
                "path": [[round(x, 1), round(y, 1), round(z)] for x, y, z in u.path],
            }
            for u in r.utility
        ],
    }


def round_meta(replay_dict: dict) -> list[dict]:
    """Lightweight per-round summary for the replay metadata endpoint."""
    out = []
    for r in replay_dict.get("rounds", []):
        out.append(
            {
                "round_number": r["round_number"],
                "duration_s": r["duration_s"],
                "n_frames": len(r.get("frames", [])),
                "n_players": len(r.get("players", [])),
                "n_utility": len(r.get("utility", [])),
                "winner": r.get("winner"),
            }
        )
    return out


# awpy path
def build_replay(pl, demo, rounds_df, ticks_df, map_id: str, tickrate: float) -> ReplayData:
    """Build :class:`ReplayData` from awpy's parsed ``ticks``/``grenades`` frames."""
    step = max(1, round(tickrate / SAMPLE_HZ))
    grenades = getattr(demo, "grenades", None)

    rounds: list[ReplayRound] = []
    for r in rounds_df.iter_rows(named=True):
        rnum = int(r["round_num"])
        freeze_end = float(r.get("freeze_end") or r.get("start") or 0)
        rdf = ticks_df.filter((pl.col("round_num") == rnum) & (pl.col("tick") >= freeze_end))
        if rdf.is_empty():
            continue
        replay_round = _build_round(pl, rdf, rnum, freeze_end, tickrate, step)
        replay_round.utility = _round_utility(pl, grenades, rnum, freeze_end, tickrate)
        replay_round.fires = _round_fires(pl, demo, rnum, freeze_end, tickrate, replay_round.players)
        replay_round.bomb = _round_bomb(pl, demo, rnum, freeze_end, tickrate)
        replay_round.kills = _round_kills(pl, demo, rnum, freeze_end, tickrate)
        replay_round.winner = str(r.get("winner")).lower() if r.get("winner") else None
        rounds.append(replay_round)

    return ReplayData(map_id=map_id, sample_hz=SAMPLE_HZ, rounds=rounds)


def _color_idx(value) -> int:
    """CS2 competitive teammate-colour index """
    try:
        i = int(value)
    except (TypeError, ValueError):
        return -1
    return i if 0 <= i <= 4 else -1


def _clean_weapon(name) -> str:
    """Normalise demoparser2's active-weapon name to a short display label."""
    if not name:
        return ""
    s = str(name)
    return s[7:] if s.startswith("weapon_") else s


# Grenade-type → bit, matched as substrings against inventory item names. The
# frontend reads this packed mask to show which utility a player is carrying.
NADE_SMOKE, NADE_FLASH, NADE_HE, NADE_MOLOTOV, NADE_DECOY, ITEM_C4 = 1, 2, 4, 8, 16, 32
_NADE_BITS: list[tuple[tuple[str, ...], int]] = [
    (("smoke",), NADE_SMOKE),
    (("flash",), NADE_FLASH),
    (("high explosive", "he grenade", "frag"), NADE_HE),
    (("molotov", "incendiary"), NADE_MOLOTOV),
    (("decoy",), NADE_DECOY),
    (("c4",), ITEM_C4),
]


def _nade_mask(inventory) -> int:
    """Pack the grenade types present in an inventory item list into a bitmask."""
    if not inventory:
        return 0
    mask = 0
    for item in inventory:
        name = str(item).lower()
        for needles, bit in _NADE_BITS:
            if any(n in name for n in needles):
                mask |= bit
    return mask


def _build_round(pl, rdf, rnum: int, freeze_end: float, tickrate: float, step: int) -> ReplayRound:
    ticks = sorted({int(t) for t in rdf["tick"].to_list()})
    sampled = ticks[::step]
    duration = (ticks[-1] - freeze_end) / tickrate if ticks else 0.0

    has = set(rdf.columns)
    cols = ["tick", "steamid", "name", "side", "X", "Y", "Z"]
    # NB: awpy renames the ``armor_value`` prop to ``armor`` on the ticks frame.
    optional = (
        "yaw", "health", "armor", "balance",
        "active_weapon_name", "active_weapon_ammo", "total_ammo_left", "inventory",
        "m_iCompTeammateColor",
    )
    cols += [c for c in optional if c in has]
    sub = rdf.filter(pl.col("tick").is_in(sampled)).select([c for c in cols if c in has])

    # Roster: every player seen this round, side taken from their first sample.
    roster: dict[str, PlayerSlot] = {}
    pos_by_tick: dict[int, dict[str, list[float]]] = {}
    st_by_tick: dict[int, dict[str, list[int]]] = {}
    # Intern weapon names into a per-round table so frames carry a small int.
    weapons: list[str] = [""]
    weapon_idx: dict[str, int] = {"": 0}
    for row in sub.iter_rows(named=True):
        sid = str(row["steamid"])
        if sid not in roster:
            roster[sid] = PlayerSlot(
                sid,
                row.get("name") or "",
                (row.get("side") or "").lower(),
                color=_color_idx(row.get("m_iCompTeammateColor")),
            )
        x, y = row.get("X"), row.get("Y")
        if x is None or y is None:
            continue
        yaw = float(row.get("yaw") or 0.0)
        hp = float(row.get("health") if row.get("health") is not None else 100.0)
        z = row.get("Z")
        tk = int(row["tick"])
        pos_by_tick.setdefault(tk, {})[sid] = [
            round(float(x), 1), round(float(y), 1), round(yaw, 1), hp,
            round(float(z)) if z is not None else 0.0,
        ]
        # Dead players carry no live weapon/ammo/utility; collapse to none.
        alive = hp > 0
        weapon = _clean_weapon(row.get("active_weapon_name")) if alive else ""
        wi = weapon_idx.get(weapon)
        if wi is None:
            wi = len(weapons)
            weapons.append(weapon)
            weapon_idx[weapon] = wi
        st_by_tick.setdefault(tk, {})[sid] = [
            int(row.get("armor") or 0),
            int(row.get("balance") or 0),
            wi,
            int(row.get("active_weapon_ammo") or 0) if alive else 0,
            int(row.get("total_ammo_left") or 0) if alive else 0,
            _nade_mask(row.get("inventory")) if alive else 0,
        ]

    players = list(roster.values())
    frames: list[Frame] = []
    for tk in sampled:
        snap = pos_by_tick.get(tk, {})
        st_snap = st_by_tick.get(tk, {})
        # Dead/missing players keep their last position with hp 0 so the dot fades
        # rather than jumping; missing-at-start defaults to origin with hp 0.
        pos = [snap.get(p.steamid, [0.0, 0.0, 0.0, 0.0, 0.0]) for p in players]
        st = [st_snap.get(p.steamid, [0, 0, 0, 0, 0, 0]) for p in players]
        frames.append(Frame(t=(tk - freeze_end) / tickrate, pos=pos, st=st))

    return ReplayRound(
        round_number=rnum, duration_s=duration, players=players, frames=frames, weapons=weapons
    )


def _simplify_path(pts: list[tuple[float, float, float]], eps: float = 10.0) -> list[tuple[float, float, float]]:
    """Ramer–Douglas–Peucker on the (x, y) plane, keeping bounce corners."""
    if len(pts) < 3:
        return pts
    ax, ay, _ = pts[0]
    bx, by, _ = pts[-1]
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    far_i, far_d = 0, -1.0
    for i in range(1, len(pts) - 1):
        px, py, _ = pts[i]
        if seg2 == 0:
            d = math.hypot(px - ax, py - ay)
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / seg2
            t = max(0.0, min(1.0, t))
            d = math.hypot(px - (ax + t * dx), py - (ay + t * dy))
        if d > far_d:
            far_i, far_d = i, d
    if far_d <= eps:
        return [pts[0], pts[-1]]
    left = _simplify_path(pts[: far_i + 1], eps)
    right = _simplify_path(pts[far_i:], eps)
    return left[:-1] + right


def _round_utility(pl, grenades, rnum: int, freeze_end: float, tickrate: float) -> list[UtilityShot]:
    from app.parsing.parser import _grenade_type  # local import avoids a cycle

    if grenades is None or grenades.is_empty():
        return []
    has_z = "Z" in grenades.columns
    try:
        aggs = [
            pl.col("grenade_type").first().alias("grenade_type"),
            pl.col("tick").min().alias("throw_tick"),
            pl.col("X").alias("xs"),
            pl.col("Y").alias("ys"),
        ]
        if has_z:
            aggs.append(pl.col("Z").alias("zs"))
        events = (
            grenades.filter(
                (pl.col("round_num") == rnum)
                & pl.col("X").is_not_null()
                & pl.col("Y").is_not_null()
            )
            .sort("tick")
            .group_by("entity_id", maintain_order=True)
            .agg(*aggs)
        )
    except Exception:
        return []

    out: list[UtilityShot] = []
    for g in events.iter_rows(named=True):
        util = _grenade_type(g.get("grenade_type"))
        if util is None:
            continue
        xs, ys = g["xs"], g["ys"]
        zs = g.get("zs") or [0.0] * len(xs)
        if not xs:
            continue
        # tolerate ragged xs/ys/zs from odd demos: truncate, don't fail the parse
        raw = [(float(x), float(y), float(z or 0.0)) for x, y, z in zip(xs, ys, zs, strict=False)]
        path = _simplify_path(raw)
        t = max(0.0, (float(g.get("throw_tick", freeze_end)) - freeze_end) / tickrate)
        out.append(
            UtilityShot(
                util_type=util.value,
                side="",  # thrower side resolved client-side is not needed for the line
                t=t,
                from_xy=(path[0][0], path[0][1]),
                to_xy=(path[-1][0], path[-1][1]),
                to_z=path[-1][2],
                path=path,
            )
        )
    out.sort(key=lambda u: u.t)
    return out


def _round_fires(pl, demo, rnum: int, freeze_end: float, tickrate: float, players) -> list[list[float]]:
    """Shot events for one round as ``[player_idx, t]`` aligned to the roster."""
    idx_of = {p.steamid: i for i, p in enumerate(players)}
    try:
        shots = demo.shots  # awpy cached property over the weapon_fire events
    except Exception:
        return []
    if shots is None or shots.is_empty() or "round_num" not in shots.columns:
        return []
    sid_col = "player_steamid" if "player_steamid" in shots.columns else "steamid"
    if sid_col not in shots.columns or "tick" not in shots.columns:
        return []
    out: list[list[float]] = []
    for row in shots.filter(pl.col("round_num") == rnum).iter_rows(named=True):
        i = idx_of.get(str(row.get(sid_col)))
        if i is None:
            continue
        t = (float(row["tick"]) - freeze_end) / tickrate
        if t < 0:
            continue
        out.append([i, round(t, 2)])
    out.sort(key=lambda e: e[1])
    return out


def _round_bomb(pl, demo, rnum: int, freeze_end: float, tickrate: float) -> dict | None:
    """The round's bomb plant as ``{t, x, y, site}`` (world-space), if any."""
    try:
        bomb = demo.bomb  # awpy cached property over the bomb_* events
    except Exception:
        return None
    if bomb is None or bomb.is_empty() or "round_num" not in bomb.columns or "event" not in bomb.columns:
        return None
    try:
        sub = bomb.filter((pl.col("round_num") == rnum) & (pl.col("event") == "plant")).sort("tick")
    except Exception:
        return None
    if sub.is_empty():
        return None
    row = sub.to_dicts()[0]
    # Bomb position columns are upper-case X/Y (from the ticks frame).
    x, y = row.get("X"), row.get("Y")
    if x is None or y is None:
        return None
    z = row.get("Z")
    t = max(0.0, (float(row["tick"]) - freeze_end) / tickrate)
    site = (row.get("bombsite") or "").replace("Bombsite", "") or None  # "BombsiteB" -> "B"
    return {
        "t": round(t, 2),
        "x": round(float(x), 1),
        "y": round(float(y), 1),
        "z": round(float(z)) if z is not None else None,
        "site": site,
    }


def _round_kills(pl, demo, rnum: int, freeze_end: float, tickrate: float) -> list[dict]:
    """Kill events for the round, shaped for the viewer's kill feed."""
    try:
        kills = demo.kills  # awpy cached property over player_death events
    except Exception:
        return []
    if kills is None or kills.is_empty() or "round_num" not in kills.columns:
        return []
    cols = set(kills.columns)
    vx_col = next((c for c in ("victim_X", "victim_x", "user_X") if c in cols), None)
    vy_col = next((c for c in ("victim_Y", "victim_y", "user_Y") if c in cols), None)
    ast_col = next((c for c in ("assister_name", "assister") if c in cols), None)
    air_col = next((c for c in ("attackerinair", "attacker_in_air", "attacker_airborne") if c in cols), None)
    ns_col = next((c for c in ("noscope", "no_scope") if c in cols), None)
    out: list[dict] = []
    for row in kills.filter(pl.col("round_num") == rnum).sort("tick").iter_rows(named=True):
        t = max(0.0, (float(row["tick"]) - freeze_end) / tickrate)
        w = str(row.get("weapon") or "")
        w = w[7:] if w.startswith("weapon_") else w
        ev = {
            "t": round(t, 2),
            "atk": row.get("attacker_name") or "?",
            "as": (row.get("attacker_side") or "").lower(),
            "vic": row.get("victim_name") or "?",
            "vs": (row.get("victim_side") or "").lower(),
            "wp": w.replace("_", " "),
            "hs": bool(row.get("headshot")),
        }
        if air_col and row.get(air_col):
            ev["air"] = True
        if ns_col and row.get(ns_col):
            ev["ns"] = True
        if ast_col and row.get(ast_col):
            ev["ast"] = row.get(ast_col)
        if vx_col and row.get(vx_col) is not None and row.get(vy_col) is not None:
            ev["vx"] = round(float(row[vx_col]), 1)
            ev["vy"] = round(float(row[vy_col]), 1)
        out.append(ev)
    return out


# sample-data path
def build_sample_replay(parsed, *, seed: int = 0) -> ReplayData:
    """Fabricate plausible movement so the viewer works without real demos.

    Five T and five CT players ease from their spawn toward the round's target
    region; utility is thrown from around the T spawn toward zone centroids.
    """
    import random

    game_map: GameMap | None = get_map(parsed.map_id) or (list_maps()[0] if list_maps() else None)
    if game_map is None:
        return ReplayData(map_id=parsed.map_id, sample_hz=SAMPLE_HZ, rounds=[])

    xs = [z.centroid[0] for z in game_map.zones]
    ys = [z.centroid[1] for z in game_map.zones]
    cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
    span = max(max(xs) - min(xs), max(ys) - min(ys)) or 2000.0
    t_spawn = (cx, min(ys) - span * 0.15)
    ct_spawn = (cx, max(ys) + span * 0.15)

    region_centroid: dict[str, tuple[float, float]] = {}
    for z in game_map.zones:
        region_centroid.setdefault(z.region.value, z.centroid)

    rng = random.Random(f"replay:{game_map.id}:{parsed.team}:{seed}")
    util_by_round: dict[int, list] = {}
    for u in parsed.utility:
        util_by_round.setdefault(u.round_number, []).append(u)

    rounds: list[ReplayRound] = []
    for rd in parsed.rounds:
        target = {"A": region_centroid.get("A"), "B": region_centroid.get("B")}.get(
            rd.target_site, (cx, cy)
        ) or (cx, cy)
        players = [PlayerSlot(f"T{i}", f"T Player {i}", "t", color=i - 1) for i in range(1, 6)]
        players += [PlayerSlot(f"CT{i}", f"CT Player {i}", "ct", color=i - 1) for i in range(1, 6)]

        # Plausible loadout per side so the scoreboard panel isn't empty in
        # sample/dev mode (no real weapon/money data available).
        weapons = ["", "ak47", "m4a1"]
        side_weapon = {"t": 1, "ct": 2}

        duration = 60.0
        n_frames = int(duration * SAMPLE_HZ)
        frames: list[Frame] = []
        offsets = [(rng.uniform(-300, 300), rng.uniform(-300, 300)) for _ in players]
        # A few players die mid-round (so the death "X" shows); the rest survive.
        death_t = [
            rng.uniform(20.0, 55.0) if rng.random() < 0.5 else None for _ in players
        ]
        frozen: list[list[float] | None] = [None] * len(players)
        fires: list[list[float]] = []
        for fi in range(n_frames):
            t = fi / SAMPLE_HZ
            prog = min(1.0, fi / max(1, n_frames - 1))
            pos = []
            st = []
            for pi, (p, (ox, oy)) in enumerate(zip(players, offsets, strict=True)):
                dead = death_t[pi] is not None and t >= death_t[pi]
                if dead and frozen[pi] is not None:
                    fx, fy = frozen[pi]
                    pos.append([fx, fy, 0.0, 0.0, 0.0])
                    st.append([0, 2500, 0, 0, 0, 0])
                    continue
                if p.side == "t":
                    sx, sy = t_spawn
                    dx, dy = target
                else:
                    sx, sy = ct_spawn
                    dx, dy = target[0], (target[1] + ct_spawn[1]) / 2
                x = round(sx + (dx - sx) * prog + ox, 1)
                y = round(sy + (dy - sy) * prog + oy, 1)
                if dead:
                    frozen[pi] = [x, y]
                    pos.append([x, y, 0.0, 0.0, 0.0])
                    st.append([0, 2500, 0, 0, 0, 0])
                else:
                    pos.append([x, y, 0.0, 100.0, 0.0])
                    # armor, money, weapon, clip 30 / reserve 90, smoke+flash.
                    mask = NADE_SMOKE | NADE_FLASH | (ITEM_C4 if pi == 0 else 0)
                    st.append([100, 2500, side_weapon[p.side], 30, 90, mask])
                    # Occasional shots while alive.
                    if t > 15.0 and rng.random() < 0.05:
                        fires.append([pi, round(t, 2)])
            frames.append(Frame(t=t, pos=pos, st=st))
        fires.sort(key=lambda e: e[1])

        shots: list[UtilityShot] = []
        for u in util_by_round.get(rd.round_number, []):
            zc = next((z.centroid for z in game_map.zones if z.id == u.zone_id), (cx, cy))
            shots.append(
                UtilityShot(
                    util_type=u.util_type,
                    side=u.side,
                    t=min(duration, u.round_time_s),
                    from_xy=(t_spawn[0] + rng.uniform(-200, 200), t_spawn[1] + rng.uniform(-100, 100)),
                    to_xy=zc,
                )
            )
        shots.sort(key=lambda s: s.t)
        # Fabricate kills from the deaths so the kill feed shows up in dev mode.
        kills: list[dict] = []
        for pi, dtod in enumerate(death_t):
            if dtod is None:
                continue
            victim = players[pi]
            enemies = [q for q in range(len(players)) if players[q].side != victim.side]
            atk = players[rng.choice(enemies)] if enemies else victim
            fz = frozen[pi]
            k = {
                "t": round(dtod, 2),
                "atk": atk.name,
                "as": atk.side,
                "vic": victim.name,
                "vs": victim.side,
                "wp": "ak47" if atk.side == "t" else "m4a1",
                "hs": rng.random() < 0.4,
                "vx": fz[0] if fz else None,
                "vy": fz[1] if fz else None,
            }
            if rng.random() < 0.2:
                k["air"] = True
            if rng.random() < 0.15:
                k["ns"] = True
            kills.append(k)
        kills.sort(key=lambda k: k["t"])
        t_kills = sum(1 for k in kills if k["as"] == "t")
        winner = "t" if t_kills * 2 >= len(kills) else "ct"
        # Plant the bomb at the target on roughly half the rounds, so the viewer's
        # bomb indicator shows up in sample/dev mode.
        bomb = None
        if rng.random() < 0.5:
            bomb = {
                "t": round(min(duration - 5.0, 35.0), 2),
                "x": round(target[0], 1),
                "y": round(target[1], 1),
                "site": rd.target_site or "A",
            }
        rounds.append(
            ReplayRound(
                rd.round_number,
                duration,
                players,
                frames=frames,
                utility=shots,
                weapons=weapons,
                fires=fires,
                bomb=bomb,
                kills=kills,
                winner=winner,
            )
        )

    return ReplayData(map_id=game_map.id, sample_hz=SAMPLE_HZ, rounds=rounds)
