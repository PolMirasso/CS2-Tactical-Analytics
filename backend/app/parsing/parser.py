from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from app.analytics.maps import classify_point, get_map, list_maps, to_radar_pixel
from app.config import get_settings
from app.domain.enums import BuyType, Site, UtilityType
from app.domain.weapons import weapons_present
from app.parsing.replay import ReplayData, build_replay, build_sample_replay

TICKRATE = 64

# T-side team equipment value thresholds (sum of the 5 players)
_FULL_ECO_MAX = 4_000
_ECO_MAX = 9_000
_FORCE_MAX = 18_000

# Match structure: MR12 regulation (24 rounds, half at 12), MR3 overtime halves.
_REGULATION_ROUNDS = 24
_REGULATION_HALF = 12

# Hero weapon → buy type, ordered by precedence (AWP outranks rifles).
_HERO_BUYS: tuple[tuple[str, tuple[str, ...], BuyType], ...] = (
    ("awp", ("awp",), BuyType.AWP_HERO),
    ("ak", ("ak-47", "ak47"), BuyType.AK_HERO),
    ("m4", ("m4a1", "m4a4", "m4a1-s", "m4"), BuyType.M4_HERO),
)


def is_pistol_round(round_number: int) -> bool:
    """First round of each regulation half (1, 13); overtime starts with money."""
    if round_number > _REGULATION_ROUNDS:
        return False
    return round_number % _REGULATION_HALF == 1

# demoparser2 grenade_type strings
_GRENADE_MAP = {
    "smoke": UtilityType.SMOKE,
    "smokegrenade": UtilityType.SMOKE,
    "flash": UtilityType.FLASH,
    "flashbang": UtilityType.FLASH,
    "molotov": UtilityType.MOLOTOV,
    "incendiary": UtilityType.MOLOTOV,
    "incendiarygrenade": UtilityType.MOLOTOV,
    "inferno": UtilityType.MOLOTOV,
    "firebomb": UtilityType.MOLOTOV,
    "he": UtilityType.HE,
    "hegrenade": UtilityType.HE,
    "he_grenade": UtilityType.HE,
}


class ParseError(RuntimeError):
    """Raised when a demo cannot be parsed into usable rounds."""


@dataclass
class UtilData:
    round_number: int
    util_type: str
    zone_id: str | None
    region: str | None
    round_time_s: float
    side: str  # "t" / "ct"
    # detonation position in 1024-space radar pixels
    radar_x: float | None = None
    radar_y: float | None = None
    # separates upper/lower on two-level maps (nuke)
    z: float | None = None


@dataclass
class RoundData:
    round_number: int
    target_site: str
    buy_type: str
    equip_value: int
    team: str | None = None
    opponent: str | None = None
    winner: str | None = None  # "t" / "ct"
    win_reason: str | None = None
    plant_time_s: float | None = None
    opponent_buy_type: str | None = None
    opponent_equip_value: int | None = None
    team_weapons: str | None = None
    opponent_weapons: str | None = None


@dataclass
class KillData:
    round_number: int
    time_s: float
    killer_name: str | None
    killer_side: str | None
    victim_name: str | None
    victim_side: str | None
    assister_name: str | None
    weapon: str | None
    headshot: bool
    x: float | None = None
    y: float | None = None


@dataclass
class PlayerStatData:
    name: str
    team: str | None
    steamid: str | None = None
    kills: int = 0
    deaths: int = 0
    assists: int = 0
    headshots: int = 0
    rounds: int = 0
    adr: float | None = None


@dataclass
class ParsedDemo:
    map_id: str
    team: str | None
    opponent: str | None
    rounds: list[RoundData] = field(default_factory=list)
    utility: list[UtilData] = field(default_factory=list)
    kills: list[KillData] = field(default_factory=list)
    player_stats: list[PlayerStatData] = field(default_factory=list)
    # 2D-replay frames (player positions + grenade lines); built lazily so the
    # analytics path stays cheap when the viewer artifact is not needed.
    replay: ReplayData | None = None


def classify_buy(
        team_equip_value: int, round_number: int, hero_weapon: str | None = None
) -> BuyType:
    if is_pistol_round(round_number):
        return BuyType.PISTOL
    if team_equip_value < _FULL_ECO_MAX:
        base = BuyType.FULL_ECO
    elif team_equip_value < _ECO_MAX:
        base = BuyType.ECO
    elif team_equip_value < _FORCE_MAX:
        return BuyType.FORCE
    else:
        return BuyType.FULL
    # On a save/eco, a single expensive weapon makes it a "hero" buy.
    if hero_weapon:
        for key, _, hero_type in _HERO_BUYS:
            if key == hero_weapon:
                return hero_type
    return base


def _planted_sites(demo, rounds_df, map_id: str) -> dict[int, tuple[str, float | None]]:
    # round (planted site, plant tick) from the bomb_planted event
    events = getattr(demo, "events", None) or {}
    planted = events.get("bomb_planted")
    if planted is None or planted.is_empty():
        return {}

    windows: list[tuple[int, float, float]] = []
    for r in rounds_df.iter_rows(named=True):
        start = float(r.get("start") or 0)
        end = float(r.get("official_end") or r.get("end") or start)
        windows.append((int(r["round_num"]), start, end))

    out: dict[int, tuple[str, float | None]] = {}
    for row in planted.iter_rows(named=True):
        tick = row.get("tick")
        if tick is None:
            continue
        place = str(row.get("user_place") or "")
        if place.endswith("A"):
            site = Site.A.value
        elif place.endswith("B"):
            site = Site.B.value
        else:
            x, y = row.get("user_X"), row.get("user_Y")
            zone = classify_point(map_id, x, y) if x is not None and y is not None else None
            site = zone.region.value if zone and zone.region.value in (Site.A.value, Site.B.value) else None
        if site is None:
            continue
        for rnum, start, end in windows:
            if start <= float(tick) <= end:
                out[rnum] = (site, float(tick))
                break
    return out


def _grenade_type(raw: str | None) -> UtilityType | None:
    if not raw:
        return None
    # awpy reports engine class names (``CSmokeGrenadeProjectile``); sample data
    # uses short tokens (``smoke``). Match both by substring.
    s = str(raw).lower()
    if "decoy" in s:
        return None
    if "flash" in s:
        return UtilityType.FLASH
    if "smoke" in s:
        return UtilityType.SMOKE
    if "incendiary" in s or "molotov" in s or "inferno" in s or "firebomb" in s:
        return UtilityType.MOLOTOV
    if "he" in s and "grenade" in s:
        return UtilityType.HE
    return _GRENADE_MAP.get(s.replace(" ", ""))


def parse_demo(
        path: Path, *, map_hint: str | None = None, team_hint: str | None = None
) -> ParsedDemo:
    """Parse a demo into a :class:`ParsedDemo`. Raises :class:`ParseError` on failure."""
    if get_settings().use_sample_data:
        return generate_sample(map_id=map_hint, team=team_hint)
    return _parse_with_awpy(path, map_hint=map_hint, team_hint=team_hint)


# awpy path
def _parse_with_awpy(
        path: Path, *, map_hint: str | None, team_hint: str | None = None
) -> ParsedDemo:
    try:
        import polars as pl
        from awpy import Demo
    except ImportError as exc:  # pragma: no cover - deps are declared
        raise ParseError(f"parsing dependencies unavailable: {exc}") from exc

    base_props = [
        "current_equip_value",
        "team_clan_name",
        "yaw",
        "armor_value",
        "balance",
        "active_weapon_name",
        "active_weapon_ammo",
        "total_ammo_left",
        "inventory",
    ]

    try:
        demo = Demo(path=path, tickrate=TICKRATE)
        demo.parse(player_props=base_props + ["m_iCompTeammateColor"])
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        try:
            demo = Demo(path=path, tickrate=TICKRATE)
            demo.parse(player_props=base_props)
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            raise ParseError(f"awpy failed to parse demo: {exc}") from exc

    header = getattr(demo, "header", None) or {}
    map_id = header.get("map_name") or map_hint
    if not map_id:
        raise ParseError("could not determine map for demo")

    rounds_df = getattr(demo, "rounds", None)
    ticks_df = getattr(demo, "ticks", None)
    if rounds_df is None or ticks_df is None or rounds_df.is_empty():
        raise ParseError("demo produced no rounds")

    tickrate = float(getattr(demo, "tickrate", TICKRATE) or TICKRATE)
    planted_sites = _planted_sites(demo, rounds_df, map_id)
    rounds: list[RoundData] = []
    # Both clans appear on T and CT across a match (sides swap at the half), so
    # tally every clan we see regardless of side and resolve the matchup later.
    clan_votes: dict[str, int] = {}

    for r in rounds_df.iter_rows(named=True):
        rnum = int(r["round_num"])
        freeze_end = r.get("freeze_end") or r.get("start") or 0
        t_rows = _round_side_rows(pl, ticks_df, rnum, freeze_end, "t")
        ct_rows = _round_side_rows(pl, ticks_df, rnum, freeze_end, "ct")
        equip = _sum_equip(t_rows)
        opp_equip = _sum_equip(ct_rows)
        team = _mode_clan(t_rows)
        opp = _mode_clan(ct_rows)
        for clan in (team, opp):
            if clan:
                clan_votes[clan] = clan_votes.get(clan, 0) + 1
        site, plant_tick = planted_sites.get(rnum, (Site.NO_PLANT.value, None))
        plant_time_s = (
            max(0.0, (plant_tick - float(freeze_end)) / tickrate)
            if plant_tick is not None
            else None
        )
        rounds.append(
            RoundData(
                round_number=rnum,
                target_site=site,
                buy_type=classify_buy(equip, rnum, _hero_weapon(t_rows)).value,
                equip_value=equip,
                team=team,
                opponent=opp,
                winner=_side(r.get("winner")),
                win_reason=_win_reason(r),
                plant_time_s=plant_time_s,
                opponent_buy_type=classify_buy(opp_equip, rnum, _hero_weapon(ct_rows)).value,
                opponent_equip_value=opp_equip,
                team_weapons=_side_weapons(t_rows),
                opponent_weapons=_side_weapons(ct_rows),
            )
        )

    utility = _extract_utility(pl, demo, rounds_df, ticks_df, map_id, tickrate)
    replay = build_replay(pl, demo, rounds_df, ticks_df, map_id, tickrate)
    kills = _kills_from_replay(replay)
    player_stats = _player_stats(kills, len(rounds), _extract_damage(pl, demo))
    _assign_player_teams(player_stats, replay, rounds)

    team, opponent = _resolve_matchup(clan_votes, team_hint)
    return ParsedDemo(
        map_id=map_id, team=team, opponent=opponent, rounds=rounds, utility=utility,
        kills=kills, player_stats=player_stats, replay=replay
    )


def _side(value) -> str | None:
    s = str(value).lower() if value else ""
    return s if s in ("t", "ct") else None


def _win_reason(round_row: dict) -> str | None:
    for key in ("reason", "round_end_reason", "end_reason"):
        v = round_row.get(key)
        if v:
            return str(v)
    return None


def _kills_from_replay(replay) -> list[KillData]:
    """Flatten the per-round kill feed the replay builder already produced."""
    out: list[KillData] = []
    if replay is None:
        return out
    for r in replay.rounds:
        for k in r.kills:
            out.append(
                KillData(
                    round_number=r.round_number,
                    time_s=float(k.get("t") or 0.0),
                    killer_name=k.get("atk"),
                    killer_side=_side(k.get("as")),
                    victim_name=k.get("vic"),
                    victim_side=_side(k.get("vs")),
                    assister_name=k.get("ast"),
                    weapon=k.get("wp"),
                    headshot=bool(k.get("hs")),
                    x=k.get("vx"),
                    y=k.get("vy"),
                )
            )
    return out


def _player_stats(
        kills: list[KillData], n_rounds: int, damage: dict[str, int]
) -> list[PlayerStatData]:
    """Aggregate the kill feed into a per-player scoreboard."""
    stats: dict[str, PlayerStatData] = {}

    def slot(name: str | None) -> PlayerStatData | None:
        if not name or name == "?":
            return None
        s = stats.get(name)
        if s is None:
            s = stats[name] = PlayerStatData(name=name, team=None)
        return s

    for k in kills:
        atk = slot(k.killer_name)
        if atk is not None:
            atk.kills += 1
            if k.headshot:
                atk.headshots += 1
        vic = slot(k.victim_name)
        if vic is not None:
            vic.deaths += 1
        ast = slot(k.assister_name)
        if ast is not None:
            ast.assists += 1

    for name, total in damage.items():
        s = stats.get(name)
        if s is not None and n_rounds:
            s.adr = round(total / n_rounds, 1)

    for s in stats.values():
        s.rounds = n_rounds
    return sorted(stats.values(), key=lambda s: s.kills, reverse=True)


def _assign_player_teams(
        stats: list[PlayerStatData], replay, rounds: list[RoundData]
) -> None:
    """Tag each player with their clan and group the scoreboard by team.

    A player's team is stable across the match; sides only swap at the half, so
    their first-half side maps to the clan that played that side in round 1.
    """
    if not stats or not rounds:
        return
    team_t, team_ct = rounds[0].team, rounds[0].opponent
    side_of: dict[str, str] = {}
    id_of: dict[str, str] = {}
    if replay is not None:
        for r in replay.rounds:
            for p in r.players:
                # steamid is stable across halves
                id_of.setdefault(p.name, p.steamid)
                if r.round_number <= _REGULATION_HALF:
                    side_of.setdefault(p.name, p.side)  # sides are stable pre-half
    for s in stats:
        side = side_of.get(s.name)
        s.team = team_t if side == "t" else team_ct if side == "ct" else None
        s.steamid = id_of.get(s.name)
    stats.sort(key=lambda s: (s.team or "~", -s.kills))


def _extract_damage(pl, demo) -> dict[str, int]:
    """Total damage dealt per attacker, for ADR. Best-effort over awpy.damages."""
    try:
        dmg = demo.damages
    except Exception:
        return {}
    if dmg is None or dmg.is_empty():
        return {}
    name_col = next((c for c in ("attacker_name", "attacker") if c in dmg.columns), None)
    val_col = next(
        (c for c in ("dmg_health", "damage", "hp_damage", "health_damage") if c in dmg.columns),
        None,
    )
    if name_col is None or val_col is None:
        return {}
    out: dict[str, int] = {}
    try:
        agg = dmg.group_by(name_col).agg(pl.col(val_col).sum().alias("d"))
        for row in agg.iter_rows(named=True):
            name = row.get(name_col)
            if name:
                out[str(name)] = int(row.get("d") or 0)
    except Exception:
        return {}
    return out


def _resolve_matchup(
        clan_votes: dict[str, int], team_hint: str | None
) -> tuple[str | None, str | None]:
    """Pick (team, opponent) as two *distinct* clans from the match.

    Team identity cannot be read off a single side because sides swap at the
    half, so we work from the distinct clan names seen across the whole match.
    When a hint is given we anchor the team to the closest-matching clan; the
    opponent is always the most-seen *other* clan, so the two never collapse to
    the same name.
    """
    clans = sorted(clan_votes, key=lambda c: clan_votes[c], reverse=True)
    if not clans:
        return team_hint, None
    team = _match_hint(clans, team_hint) if team_hint else clans[0]
    opponent = next((c for c in clans if c != team), None)
    return team, opponent


def _match_hint(clans: list[str], hint: str) -> str:
    """Return the clan whose name best matches ``hint`` (else the most-seen one)."""
    norm = hint.strip().lower()
    if norm:
        for clan in clans:
            if clan.strip().lower() == norm:
                return clan
        for clan in clans:
            cl = clan.strip().lower()
            if norm in cl or cl in norm:
                return clan
    return clans[0]


def _round_side_rows(pl, ticks_df, round_num: int, freeze_end, side: str):
    """Rows for one side at the first in-play tick of a round (peak buy state)."""
    try:
        rdf = ticks_df.filter(pl.col("round_num") == round_num)
        if "side" in rdf.columns:
            rdf = rdf.filter(pl.col("side") == side)
        if rdf.is_empty():
            return rdf
        first_tick = rdf.filter(pl.col("tick") >= freeze_end)
        first_tick = first_tick if not first_tick.is_empty() else rdf
        t0 = first_tick.select(pl.col("tick").min()).item()
        return rdf.filter(pl.col("tick") == t0)
    except Exception:
        return ticks_df.head(0)


def _sum_equip(rows) -> int:
    if rows.is_empty() or "current_equip_value" not in rows.columns:
        return 0
    try:
        return int(rows.select("current_equip_value").sum().item() or 0)
    except Exception:
        return 0


def _inventory_strings(rows) -> list[str]:
    if rows.is_empty():
        return []
    weapons: list[str] = []
    for col in ("inventory", "active_weapon_name"):
        if col not in rows.columns:
            continue
        try:
            for v in rows[col].to_list():
                if isinstance(v, (list, tuple)):
                    weapons.extend(str(x).lower() for x in v if x)
                elif v:
                    weapons.append(str(v).lower())
        except Exception:
            continue
    return weapons


def _hero_weapon(rows) -> str | None:
    """Detect an AWP/AK/M4 held by the side, used to flag hero eco buys."""
    weapons = _inventory_strings(rows)
    for key, needles, _ in _HERO_BUYS:
        if any(any(n in w for n in needles) for w in weapons):
            return key
    return None


def _side_weapons(rows) -> str | None:
    weapons = _inventory_strings(rows)
    if not weapons:
        return None
    return ",".join(weapons_present(weapons))


def _mode_clan(rows) -> str | None:
    if rows.is_empty() or "team_clan_name" not in rows.columns:
        return None
    try:
        vals = [v for v in rows["team_clan_name"].to_list() if v]
        return max(set(vals), key=vals.count) if vals else None
    except Exception:
        return None


def _extract_utility(pl, demo, rounds_df, ticks_df, map_id: str, tickrate: float) -> list[UtilData]:
    grenades = getattr(demo, "grenades", None)
    if grenades is None or grenades.is_empty():
        return []

    freeze_by_round = {
        int(r["round_num"]): (r.get("freeze_end") or r.get("start") or 0)
        for r in rounds_df.iter_rows(named=True)
    }
    side_lookup = _build_side_lookup(pl, ticks_df)

    # ``grenades`` is a per-tick projectile trajectory (>1M rows); collapse it to
    # one event per thrown grenade, keeping the resting/detonation position (last
    # known X/Y) and the throw time (first tick).
    try:
        events = (
            grenades.filter(pl.col("X").is_not_null() & pl.col("Y").is_not_null())
            .sort("tick")
            .group_by(["round_num", "entity_id"])
            .agg(
                pl.col("grenade_type").first().alias("grenade_type"),
                pl.col("thrower_steamid").first().alias("thrower_steamid"),
                pl.col("tick").min().alias("throw_tick"),
                pl.col("X").last().alias("X"),
                pl.col("Y").last().alias("Y"),
                pl.col("Z").last().alias("Z") if "Z" in grenades.columns else pl.lit(None).alias("Z"),
            )
        )
    except Exception:
        return []

    out: list[UtilData] = []
    for g in events.iter_rows(named=True):
        rnum = g.get("round_num")
        util = _grenade_type(g.get("grenade_type"))
        if rnum is None or util is None:
            continue
        rnum = int(rnum)
        x, y = g.get("X"), g.get("Y")
        z = g.get("Z")
        has_pos = x is not None and y is not None
        zone = classify_point(map_id, x, y) if has_pos else None
        radar = to_radar_pixel(map_id, x, y) if has_pos else (None, None)
        freeze_end = freeze_by_round.get(rnum, 0)
        round_time = max(0.0, (float(g.get("throw_tick", freeze_end)) - float(freeze_end)) / tickrate)
        side = side_lookup.get((rnum, g.get("thrower_steamid")), "")
        out.append(
            UtilData(
                round_number=rnum,
                util_type=util.value,
                zone_id=zone.id if zone else None,
                region=zone.region.value if zone else None,
                round_time_s=round_time,
                side=side,
                radar_x=radar[0],
                radar_y=radar[1],
                z=float(z) if z is not None else None,
            )
        )
    return out


def _build_side_lookup(pl, ticks_df) -> dict[tuple[int, object], str]:
    lookup: dict[tuple[int, object], str] = {}
    if ticks_df is None or not {"round_num", "steamid", "side"} <= set(ticks_df.columns):
        return lookup
    try:
        slim = ticks_df.select(["round_num", "steamid", "side"]).unique()
        for row in slim.iter_rows(named=True):
            lookup[(int(row["round_num"]), row["steamid"])] = row["side"]
    except Exception:
        pass
    return lookup


# sample-data path
def _sample_weapons(buy: BuyType, side: str, rng: random.Random) -> str:
    rifle = "ak47" if side == "t" else "m4a4"
    pistol = "glock" if side == "t" else "usp_s"
    if buy is BuyType.PISTOL:
        ids = [pistol] + (["deagle"] if rng.random() < 0.3 else [])
    elif buy in (BuyType.FULL_ECO, BuyType.ECO):
        ids = [pistol] + (["deagle"] if rng.random() < 0.25 else []) \
            + (["ssg08"] if rng.random() < 0.2 else [])
    elif buy is BuyType.FORCE:
        ids = [pistol, rng.choice(["mp9", "mac10", "mp7", "ump45"])]
    else:
        ids = [rifle] + (["awp"] if rng.random() < 0.35 else [])
    return ",".join(ids)


def generate_sample(
        *, map_id: str | None = None, team: str | None = None, seed: int = 0
) -> ParsedDemo:
    """Fabricate a plausible demo: zone-weighted utility that signals the plant site."""
    game_map = get_map(map_id) if map_id else None
    if game_map is None:
        game_map = list_maps()[0]
    rng = random.Random(f"{game_map.id}:{team}:{seed}")

    team = team or "Sample Team"
    opponent = "Sample Opponent"
    zones_by_region: dict[str, list] = {}
    for z in game_map.zones:
        zones_by_region.setdefault(z.region.value, []).append(z)

    rounds: list[RoundData] = []
    utility: list[UtilData] = []
    n_rounds = 24
    for rnum in range(1, n_rounds + 1):
        if is_pistol_round(rnum):
            buy = BuyType.PISTOL
        else:
            buy = rng.choices(
                [BuyType.FULL, BuyType.FORCE, BuyType.ECO, BuyType.FULL_ECO],
                weights=[0.45, 0.25, 0.15, 0.15],
            )[0]
        equip = {
            BuyType.FULL: 22000,
            BuyType.FORCE: 12000,
            BuyType.ECO: 6000,
            BuyType.FULL_ECO: 1500,
            BuyType.PISTOL: 4000,
        }[buy]
        display_buy = buy
        if buy in (BuyType.ECO, BuyType.FULL_ECO) and rng.random() < 0.3:
            display_buy, hero_cost = rng.choice(
                [(BuyType.AK_HERO, 2700), (BuyType.M4_HERO, 3000), (BuyType.AWP_HERO, 4750)]
            )
            equip += hero_cost
        # Eco/save rounds rarely commit to a site.
        if buy in (BuyType.ECO, BuyType.FULL_ECO) and rng.random() < 0.6:
            target = Site.NO_PLANT
        else:
            target = rng.choices([Site.A, Site.B, Site.NO_PLANT], weights=[0.45, 0.4, 0.15])[0]
        # Plant time on plant rounds only
        if target is Site.NO_PLANT:
            plant_time_s = None
        else:
            center = 25.0 if target is Site.A else 55.0
            plant_time_s = round(max(0.0, min(110.0, rng.gauss(center, 15.0))), 1)
        if is_pistol_round(rnum):
            opp_buy = BuyType.PISTOL
        else:
            opp_buy = rng.choices(
                [BuyType.FULL, BuyType.FORCE, BuyType.ECO, BuyType.FULL_ECO],
                weights=[0.45, 0.25, 0.15, 0.15],
            )[0]
        rounds.append(
            RoundData(
                round_number=rnum,
                target_site=target.value,
                buy_type=display_buy.value,
                equip_value=equip,
                team=team,
                opponent=opponent,
                plant_time_s=plant_time_s,
                opponent_buy_type=opp_buy.value,
                opponent_equip_value={
                    BuyType.FULL: 22000, BuyType.FORCE: 12000,
                    BuyType.ECO: 6000, BuyType.FULL_ECO: 1500, BuyType.PISTOL: 4000,
                }[opp_buy],
                team_weapons=_sample_weapons(buy, "t", rng),
                opponent_weapons=_sample_weapons(opp_buy, "ct", rng),
            )
        )
        # Utility lands mostly in the region the team is executing toward.
        exec_region = {Site.A: "A", Site.B: "B", Site.NO_PLANT: "Mid"}[target]
        n_util = {BuyType.FULL_ECO: 0, BuyType.ECO: rng.randint(0, 2), BuyType.PISTOL: rng.randint(1, 2)}.get(
            buy, rng.randint(3, 6)
        )
        for _ in range(n_util):
            region = exec_region if rng.random() < 0.7 else rng.choice(["A", "B", "Mid"])
            pool = zones_by_region.get(region) or list(game_map.zones)
            zone = rng.choice(pool)
            util = rng.choice(list(UtilityType))
            utility.append(
                UtilData(
                    round_number=rnum,
                    util_type=util.value,
                    zone_id=zone.id,
                    region=zone.region.value,
                    round_time_s=round(rng.uniform(0, 40), 1),
                    side="t",
                )
            )
    parsed = ParsedDemo(
        map_id=game_map.id, team=team, opponent=opponent, rounds=rounds, utility=utility
    )
    parsed.replay = build_sample_replay(parsed, seed=seed)

    # Reuse the fabricated replay for round outcomes, the kill feed and the
    # scoreboard so dev mode exercises the same code paths as a real demo.
    win_by_round = {r.round_number: r.winner for r in parsed.replay.rounds}
    reasons = ["elimination", "bomb_exploded", "defused", "time_expired"]
    for rd in rounds:
        rd.winner = win_by_round.get(rd.round_number)
        rd.win_reason = rng.choice(reasons)
    parsed.kills = _kills_from_replay(parsed.replay)
    dmg: dict[str, int] = {}
    for k in parsed.kills:
        if k.killer_name:
            dmg[k.killer_name] = dmg.get(k.killer_name, 0) + rng.randint(95, 140)
    parsed.player_stats = _player_stats(parsed.kills, n_rounds, dmg)
    _assign_player_teams(parsed.player_stats, parsed.replay, rounds)
    return parsed
