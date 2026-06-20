from __future__ import annotations

import random
from app.analytics.maps import classify_point, get_map, list_maps
from app.config import get_settings
from app.domain.enums import BuyType, Site, UtilityType
from app.parsing.replay import ReplayData, build_replay, build_sample_replay
from dataclasses import dataclass, field
from pathlib import Path

# T-side equipment value
_ECO_MAX = 5_000
_FORCE_MAX = 18_000

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


@dataclass
class RoundData:
    round_number: int
    target_site: str
    buy_type: str
    equip_value: int
    team: str | None = None
    opponent: str | None = None


@dataclass
class ParsedDemo:
    map_id: str
    team: str | None
    opponent: str | None
    rounds: list[RoundData] = field(default_factory=list)
    utility: list[UtilData] = field(default_factory=list)
    # 2D-replay frames (player positions + grenade lines); built lazily so the
    # analytics path stays cheap when the viewer artifact is not needed.
    replay: "ReplayData | None" = None


def classify_buy(team_equip_value: int) -> BuyType:
    if team_equip_value < _ECO_MAX:
        return BuyType.ECO
    if team_equip_value < _FORCE_MAX:
        return BuyType.FORCE
    return BuyType.FULL


def _site_from_bomb(bomb_site: str | None) -> str:
    return {"bombsite_a": Site.A.value, "bombsite_b": Site.B.value}.get(
        bomb_site or "", Site.NO_PLANT.value
    )


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

    try:
        demo = Demo(path=path)
        demo.parse(player_props=["current_equip_value", "team_clan_name", "yaw"])
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

    tickrate = float(getattr(demo, "tickrate", 128) or 128)
    rounds: list[RoundData] = []
    # Both clans appear on T and CT across a match (sides swap at the half), so
    # tally every clan we see regardless of side and resolve the matchup later.
    clan_votes: dict[str, int] = {}

    for r in rounds_df.iter_rows(named=True):
        rnum = int(r["round_num"])
        freeze_end = r.get("freeze_end") or r.get("start") or 0
        t_rows = _round_side_rows(pl, ticks_df, rnum, freeze_end, "t")
        equip = _sum_equip(t_rows)
        team = _mode_clan(t_rows)
        opp = _mode_clan(_round_side_rows(pl, ticks_df, rnum, freeze_end, "ct"))
        for clan in (team, opp):
            if clan:
                clan_votes[clan] = clan_votes.get(clan, 0) + 1
        rounds.append(
            RoundData(
                round_number=rnum,
                target_site=_site_from_bomb(r.get("bomb_site")),
                buy_type=classify_buy(equip).value,
                equip_value=equip,
                team=team,
                opponent=opp,
            )
        )

    utility = _extract_utility(pl, demo, rounds_df, ticks_df, map_id, tickrate)
    replay = build_replay(pl, demo, rounds_df, ticks_df, map_id, tickrate)

    team, opponent = _resolve_matchup(clan_votes, team_hint)
    return ParsedDemo(
        map_id=map_id, team=team, opponent=opponent, rounds=rounds, utility=utility, replay=replay
    )


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
        zone = classify_point(map_id, x, y) if x is not None and y is not None else None
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
        buy = rng.choices(
            [BuyType.FULL, BuyType.FORCE, BuyType.ECO], weights=[0.55, 0.25, 0.20]
        )[0]
        equip = {BuyType.FULL: 22000, BuyType.FORCE: 12000, BuyType.ECO: 2500}[buy]
        # Eco rounds rarely commit to a site.
        if buy is BuyType.ECO and rng.random() < 0.6:
            target = Site.NO_PLANT
        else:
            target = rng.choices([Site.A, Site.B, Site.NO_PLANT], weights=[0.45, 0.4, 0.15])[0]
        rounds.append(
            RoundData(
                round_number=rnum,
                target_site=target.value,
                buy_type=buy.value,
                equip_value=equip,
                team=team,
                opponent=opponent,
            )
        )
        # Utility lands mostly in the region the team is executing toward.
        exec_region = {Site.A: "A", Site.B: "B", Site.NO_PLANT: "Mid"}[target]
        n_util = 0 if buy is BuyType.ECO else rng.randint(3, 6)
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
    return parsed
