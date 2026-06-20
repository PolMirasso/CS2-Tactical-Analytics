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

from app.analytics.maps import GameMap, get_map, list_maps
from dataclasses import dataclass, field

# Frames per second kept in the artifact. 8 Hz is smooth enough for a 2D radar
# replay and keeps a ~100 s round around a few hundred frames.
SAMPLE_HZ = 8.0


@dataclass
class PlayerSlot:
    steamid: str
    name: str
    side: str  # "t" / "ct"


@dataclass
class Frame:
    t: float  # seconds since the round went live (freeze end)
    # One [x, y, yaw, hp] per player, aligned to the round's ``players`` roster.
    pos: list[list[float]]


@dataclass
class UtilityShot:
    util_type: str
    side: str
    t: float
    from_xy: tuple[float, float]
    to_xy: tuple[float, float]


@dataclass
class ReplayRound:
    round_number: int
    duration_s: float
    players: list[PlayerSlot]
    frames: list[Frame] = field(default_factory=list)
    utility: list[UtilityShot] = field(default_factory=list)


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
        "players": [{"steamid": p.steamid, "name": p.name, "side": p.side} for p in r.players],
        "frames": [{"t": round(f.t, 2), "pos": f.pos} for f in r.frames],
        "utility": [
            {
                "type": u.util_type,
                "side": u.side,
                "t": round(u.t, 2),
                "from": [round(u.from_xy[0], 1), round(u.from_xy[1], 1)],
                "to": [round(u.to_xy[0], 1), round(u.to_xy[1], 1)],
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
        rounds.append(replay_round)

    return ReplayData(map_id=map_id, sample_hz=SAMPLE_HZ, rounds=rounds)


def _build_round(pl, rdf, rnum: int, freeze_end: float, tickrate: float, step: int) -> ReplayRound:
    ticks = sorted({int(t) for t in rdf["tick"].to_list()})
    sampled = ticks[::step]
    duration = (ticks[-1] - freeze_end) / tickrate if ticks else 0.0

    has = set(rdf.columns)
    cols = ["tick", "steamid", "name", "side", "X", "Y"]
    cols += [c for c in ("yaw", "health") if c in has]
    sub = rdf.filter(pl.col("tick").is_in(sampled)).select([c for c in cols if c in has])

    # Roster: every player seen this round, side taken from their first sample.
    roster: dict[str, PlayerSlot] = {}
    by_tick: dict[int, dict[str, list[float]]] = {}
    for row in sub.iter_rows(named=True):
        sid = str(row["steamid"])
        if sid not in roster:
            roster[sid] = PlayerSlot(sid, row.get("name") or "", (row.get("side") or "").lower())
        x, y = row.get("X"), row.get("Y")
        if x is None or y is None:
            continue
        yaw = float(row.get("yaw") or 0.0)
        hp = float(row.get("health") if row.get("health") is not None else 100.0)
        by_tick.setdefault(int(row["tick"]), {})[sid] = [
            round(float(x), 1), round(float(y), 1), round(yaw, 1), hp
        ]

    players = list(roster.values())
    frames: list[Frame] = []
    for tk in sampled:
        snap = by_tick.get(tk, {})
        # Dead/missing players keep their last position with hp 0 so the dot fades
        # rather than jumping; missing-at-start defaults to origin with hp 0.
        pos = [snap.get(p.steamid, [0.0, 0.0, 0.0, 0.0]) for p in players]
        frames.append(Frame(t=(tk - freeze_end) / tickrate, pos=pos))

    return ReplayRound(round_number=rnum, duration_s=duration, players=players, frames=frames)


def _round_utility(pl, grenades, rnum: int, freeze_end: float, tickrate: float) -> list[UtilityShot]:
    from app.parsing.parser import _grenade_type  # local import avoids a cycle

    if grenades is None or grenades.is_empty():
        return []
    try:
        events = (
            grenades.filter(
                (pl.col("round_num") == rnum)
                & pl.col("X").is_not_null()
                & pl.col("Y").is_not_null()
            )
            .sort("tick")
            .group_by("entity_id")
            .agg(
                pl.col("grenade_type").first().alias("grenade_type"),
                pl.col("tick").min().alias("throw_tick"),
                pl.col("X").first().alias("from_x"),
                pl.col("Y").first().alias("from_y"),
                pl.col("X").last().alias("to_x"),
                pl.col("Y").last().alias("to_y"),
            )
        )
    except Exception:
        return []

    out: list[UtilityShot] = []
    for g in events.iter_rows(named=True):
        util = _grenade_type(g.get("grenade_type"))
        if util is None:
            continue
        t = max(0.0, (float(g.get("throw_tick", freeze_end)) - freeze_end) / tickrate)
        out.append(
            UtilityShot(
                util_type=util.value,
                side="",  # thrower side resolved client-side is not needed for the line
                t=t,
                from_xy=(float(g["from_x"]), float(g["from_y"])),
                to_xy=(float(g["to_x"]), float(g["to_y"])),
            )
        )
    out.sort(key=lambda u: u.t)
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
        players = [PlayerSlot(f"T{i}", f"T Player {i}", "t") for i in range(1, 6)]
        players += [PlayerSlot(f"CT{i}", f"CT Player {i}", "ct") for i in range(1, 6)]

        duration = 60.0
        n_frames = int(duration * SAMPLE_HZ)
        frames: list[Frame] = []
        offsets = [(rng.uniform(-300, 300), rng.uniform(-300, 300)) for _ in players]
        for fi in range(n_frames):
            t = fi / SAMPLE_HZ
            prog = min(1.0, fi / max(1, n_frames - 1))
            pos = []
            for p, (ox, oy) in zip(players, offsets):
                if p.side == "t":
                    sx, sy = t_spawn
                    dx, dy = target
                else:
                    sx, sy = ct_spawn
                    dx, dy = target[0], (target[1] + ct_spawn[1]) / 2
                x = sx + (dx - sx) * prog + ox
                y = sy + (dy - sy) * prog + oy
                pos.append([round(x, 1), round(y, 1), 0.0, 100.0])
            frames.append(Frame(t=t, pos=pos))

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
        rounds.append(
            ReplayRound(rd.round_number, duration, players, frames=frames, utility=shots)
        )

    return ReplayData(map_id=game_map.id, sample_hz=SAMPLE_HZ, rounds=rounds)
