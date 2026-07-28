from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from hashlib import sha1

from sqlalchemy import and_, case, func, literal, or_, select
from sqlalchemy.orm import Session

from app.domain.models import Demo, PlayerStat, Round, User, UtilityEvent
from app.domain.schemas import (
    FilterSupportOut,
    RosterEntry,
    RosterLineup,
    SiteDistributionOut,
    SiteStat,
    SupportDrop,
    TeamRef,
    TeamRostersOut,
    ZoneUtilStat,
)
from app.domain.weapons import WEAPON_IDS

_UTIL_TYPES = ("smoke", "flash", "molotov", "he")

# Canonical plant-site order so the chart stays stable even when a site is unused.
_SITE_ORDER = ("A", "B", "NoPlant")
_PLANT_SITES = tuple(s for s in _SITE_ORDER if s != "NoPlant")

SUPPORT_LOW_ROUNDS = 20
SUPPORT_LOW_PLANTS = 10

_BASELINE_ONLY = ("period", "roster")


def _base_conditions(session: Session, user: User, map_id: str):
    # Local import avoids an analytics→demos cycle at module load.
    from app.demos.service import _visibility_clause

    return [Round.map_id == map_id, _visibility_clause(session, user)]


def _team_filter(team_id: str):
    """Match rounds executed by ``team_id`` (HLTV id) or a raw clan (uploads)."""
    return or_(Round.team_hltv_id == team_id, Round.team == team_id)


def _teams_filter(team_ids: list[str]):
    """Match rounds executed by any of team_ids"""
    return or_(Round.team_hltv_id.in_(team_ids), Round.team.in_(team_ids))


def _date_conditions(date_from: date | None, date_to: date | None) -> list:
    """match date window"""
    conds = []
    if date_from:
        conds.append(Demo.match_date >= date_from)
    if date_to:
        conds.append(Demo.match_date <= date_to)
    return conds


def _equip_conditions(column, low: int | None, high: int | None) -> list:
    """Equipment-value window; rounds without a value drop out."""
    if low is not None and high is not None and low > high:
        low, high = high, low
    conds = []
    if low is not None:
        conds.append(column >= low)
    if high is not None:
        conds.append(column <= high)
    return conds


def _weapons_condition(column, weapons: list[str]):
    """All of weapons present in the CSV column"""
    delimited = literal(",") + column + literal(",")
    return and_(*[delimited.like(f"%,{w},%") for w in weapons])


def _round_counts(session: Session, conds: list) -> tuple[int, int]:
    """(rounds, rounds that ended in a plant) matching conds"""
    total, plants = session.execute(
        select(
            func.count(),
            func.sum(case((Round.target_site.in_(_PLANT_SITES), 1), else_=0)),
        )
        .select_from(Round)
        .join(Demo, Demo.id == Round.demo_id)
        .where(*conds)
    ).one()
    return int(total or 0), int(plants or 0)


def filter_support(
        session: Session,
        user: User,
        *,
        map_id: str,
        teams: list[str] | None = None,
        buy_type: str | None = None,
        equip_min: int | None = None,
        equip_max: int | None = None,
        opponent_buy_type: str | None = None,
        opponent_equip_min: int | None = None,
        opponent_equip_max: int | None = None,
        team_weapons: list[str] | None = None,
        opponent_weapons: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        roster: str | None = None,
) -> FilterSupportOut:
    base = _base_conditions(session, user, map_id)
    team_weapons = [w for w in (team_weapons or []) if w in WEAPON_IDS]
    opponent_weapons = [w for w in (opponent_weapons or []) if w in WEAPON_IDS]

    # (UI filter key, its conditions) — the key names the culprit in the warning.
    parts: list[tuple[str, list]] = []
    if teams:
        parts.append(("team", [_teams_filter(teams)]))
    if buy_type:
        parts.append(("buy", [Round.buy_type == buy_type]))
    equip_conds = _equip_conditions(Round.equip_value, equip_min, equip_max)
    if equip_conds:
        parts.append(("equip", equip_conds))
    if opponent_buy_type:
        parts.append(("opp_buy", [Round.opponent_buy_type == opponent_buy_type]))
    opp_equip_conds = _equip_conditions(
        Round.opponent_equip_value, opponent_equip_min, opponent_equip_max
    )
    if opp_equip_conds:
        parts.append(("opp_equip", opp_equip_conds))
    if team_weapons:
        parts.append(("team_weapons", [_weapons_condition(Round.team_weapons, team_weapons)]))
    if opponent_weapons:
        parts.append(
            ("opp_weapons", [_weapons_condition(Round.opponent_weapons, opponent_weapons)])
        )
    date_conds = _date_conditions(date_from, date_to)
    if date_conds:
        parts.append(("period", date_conds))
    roster_conds = _roster_conditions(session, user, map_id=map_id, teams=teams, roster=roster)
    if roster_conds:
        parts.append(("roster", roster_conds))

    model_conds = base + [c for k, cs in parts if k not in _BASELINE_ONLY for c in cs]
    model_rounds, model_plants = _round_counts(session, model_conds)
    scoped = [c for k, cs in parts if k in _BASELINE_ONLY for c in cs]
    if scoped:
        rounds, plants = _round_counts(session, model_conds + scoped)
    else:
        rounds, plants = model_rounds, model_plants
    total_rounds, _ = _round_counts(session, base)

    def _thin(n_rounds: int, n_plants: int) -> bool:
        return n_rounds < SUPPORT_LOW_ROUNDS or n_plants < SUPPORT_LOW_PLANTS

    level, scope = "ok", None
    if model_rounds == 0:
        level, scope = "none", "model"
    elif _thin(model_rounds, model_plants):
        level, scope = "low", "model"
    elif rounds == 0:
        level, scope = "none", "period"
    elif _thin(rounds, plants):
        level, scope = "low", "period"

    # Leave-one-out: dropping which filter gives the most rounds back.
    drops: list[SupportDrop] = []
    if level != "ok":
        for key, _cs in parts:
            without = base + [c for k, cs in parts if k != key for c in cs]
            n, _ = _round_counts(session, without)
            if n > rounds:
                drops.append(SupportDrop(filter=key, rounds_without=n))
        drops.sort(key=lambda d: d.rounds_without, reverse=True)

    return FilterSupportOut(
        map_id=map_id,
        rounds=rounds,
        plant_rounds=plants,
        model_rounds=model_rounds,
        model_plant_rounds=model_plants,
        total_rounds=total_rounds,
        level=level,
        scope=scope,
        filters=[k for k, _ in parts],
        drops=drops,
    )


def teams_for_map(session: Session, user: User, map_id: str) -> list[TeamRef]:
    """Distinct executing teams with parsed rounds on a map, most rounds first"""
    from app.demos.service import resolve_team_names

    conds = _base_conditions(session, user, map_id)
    rows = session.execute(
        select(Round.team_hltv_id, Round.team, func.count())
        .join(Demo, Demo.id == Round.demo_id)
        .where(*conds, or_(Round.team_hltv_id.is_not(None), Round.team.is_not(None)))
        .group_by(Round.team_hltv_id, Round.team)
    ).all()

    names = resolve_team_names(session, {tid for tid, _, _ in rows})
    agg: dict[str, dict] = {}
    for tid, raw, n in rows:
        key = tid or raw
        if not key:
            continue
        label = names.get(tid) or raw or tid
        b = agg.setdefault(key, {"id": key, "name": label, "n": 0})
        b["n"] += n
    ordered = sorted(agg.values(), key=lambda b: b["n"], reverse=True)
    return [TeamRef(id=b["id"], name=b["name"]) for b in ordered]


def site_distribution(
        session: Session,
        user: User,
        *,
        map_id: str,
        teams: list[str] | None = None,
        buy_types: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        roster: str | None = None,
) -> SiteDistributionOut:
    """Historical plant-site split (and per-site win rate) over matching T rounds."""

    conds = _base_conditions(session, user, map_id)
    if teams:
        conds.append(_teams_filter(teams))
    if buy_types:
        conds.append(Round.buy_type.in_(buy_types))
    conds += _date_conditions(date_from, date_to)
    conds += _roster_conditions(session, user, map_id=map_id, teams=teams, roster=roster)

    # The executing team is on T, so a round was won iff its winner is "t".
    rows = session.execute(
        select(Round.target_site, Round.winner, func.count())
        .join(Demo, Demo.id == Round.demo_id)
        .where(*conds)
        .group_by(Round.target_site, Round.winner)
    ).all()
    total_demos = session.scalar(
        select(func.count(func.distinct(Round.demo_id)))
        .select_from(Round)
        .join(Demo, Demo.id == Round.demo_id)
        .where(*conds)
    ) or 0

    agg: dict[str, dict[str, int]] = {s: {"rounds": 0, "wins": 0} for s in _SITE_ORDER}
    for site, winner, n in rows:
        bucket = agg.setdefault(site, {"rounds": 0, "wins": 0})
        bucket["rounds"] += n
        if winner == "t":
            bucket["wins"] += n

    total_rounds = sum(b["rounds"] for b in agg.values())
    total_wins = sum(b["wins"] for b in agg.values())
    ordered = list(_SITE_ORDER) + [s for s in agg if s not in _SITE_ORDER]
    sites = [
        SiteStat(
            site=s,
            rounds=agg[s]["rounds"],
            pct=agg[s]["rounds"] / total_rounds if total_rounds else 0.0,
            wins=agg[s]["wins"],
            win_rate=agg[s]["wins"] / agg[s]["rounds"] if agg[s]["rounds"] else 0.0,
        )
        for s in ordered
    ]
    return SiteDistributionOut(
        map_id=map_id,
        team=teams[0] if teams and len(teams) == 1 else None,
        total_rounds=total_rounds,
        total_demos=total_demos,
        overall_win_rate=total_wins / total_rounds if total_rounds else 0.0,
        sites=sites,
    )


_ROSTER_SIZE = 5


def _demo_rosters(
        session: Session, conds: list
) -> tuple[dict[int, dict], dict[int, dict[str, str]]]:
    """per-demo match meta and the line-up fielded, as {player key: name}"""
    rows = session.execute(
        select(
            Round.demo_id,
            Demo.match_date,
            Demo.hltv_match_id,
            Round.team,
            Round.opponent_hltv_id,
            Round.opponent,
        )
        .join(Demo, Demo.id == Round.demo_id)
        .where(*conds)
        .distinct()
    ).all()

    meta: dict[int, dict] = {}
    for demo_id, mdate, match_id, clan, opp_id, opp_clan in rows:
        meta.setdefault(
            demo_id,
            {"date": mdate, "match_id": match_id, "clan": clan,
             "opp_id": opp_id, "opp_clan": opp_clan},
        )

    roster_by_demo: dict[int, dict[str, str]] = {}
    if meta:
        prows = session.execute(
            select(PlayerStat.demo_id, PlayerStat.steamid, PlayerStat.name, PlayerStat.team)
            .where(PlayerStat.demo_id.in_(list(meta)))
        ).all()
        for demo_id, sid, name, pteam in prows:
            if name and pteam is not None and pteam == meta[demo_id]["clan"]:
                key = sid or f"name:{name}"
                roster_by_demo.setdefault(demo_id, {})[key] = name
    return meta, roster_by_demo


def _ordered_demos(meta: dict[int, dict]) -> list[int]:
    """demo ids oldest first"""
    def _match_id_int(v: str | None) -> int:
        return int(v) if v and v.isdigit() else -1

    return sorted(
        meta,
        key=lambda d: (
            meta[d]["date"] is None,
            meta[d]["date"] or date.min,
            _match_id_int(meta[d]["match_id"]),
            d,
        ),
    )


def _lineup_id(keys: Iterable[str]) -> str:
    """stable id for a line-up: a hash of its player keys"""
    return sha1("|".join(sorted(keys)).encode()).hexdigest()[:10]


def _lineup_groups(
        ordered: list[int], roster_by_demo: dict[int, dict[str, str]]
) -> dict[str, dict]:
    """{lineup id: {keys, names, demos}} over full line-ups, oldest first"""
    groups: dict[str, dict] = {}
    for demo_id in ordered:
        roster = roster_by_demo.get(demo_id, {})
        if len(roster) != _ROSTER_SIZE:
            continue
        g = groups.setdefault(_lineup_id(roster), {"keys": set(roster), "names": {}, "demos": []})
        g["names"].update(roster)
        g["demos"].append(demo_id)
    for demo_id in ordered:
        roster = roster_by_demo.get(demo_id, {})
        if not roster or len(roster) == _ROSTER_SIZE:
            continue
        owners = [g for g in groups.values() if set(roster) <= g["keys"]]
        if len(owners) == 1:
            owners[0]["demos"].append(demo_id)
    return groups


def roster_demo_ids(
        session: Session, user: User, *, map_id: str, team: str, roster: str
) -> list[int]:
    """demos where team fielded the line-up roster"""
    conds = _base_conditions(session, user, map_id) + [_team_filter(team)]
    meta, roster_by_demo = _demo_rosters(session, conds)
    group = _lineup_groups(_ordered_demos(meta), roster_by_demo).get(roster)
    return sorted(group["demos"]) if group else []


def _roster_conditions(
        session: Session,
        user: User,
        *,
        map_id: str,
        teams: list[str] | None,
        roster: str | None,
) -> list:
    """restrict to one line-up's demos"""
    if not roster or not teams or len(teams) != 1:
        return []
    ids = roster_demo_ids(session, user, map_id=map_id, team=teams[0], roster=roster)
    return [Round.demo_id.in_(ids)]


def team_rosters(
        session: Session,
        user: User,
        *,
        map_id: str,
        team: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
) -> TeamRostersOut:
    """roster the analysed team fielded per demo"""
    if not team:
        return TeamRostersOut(map_id=map_id, team=team)

    conds = _base_conditions(session, user, map_id)
    conds.append(_team_filter(team))
    conds += _date_conditions(date_from, date_to)

    meta, roster_by_demo = _demo_rosters(session, conds)
    if not meta:
        return TeamRostersOut(map_id=map_id, team=team)

    from app.demos.service import resolve_team_names

    opp_names = resolve_team_names(session, {m["opp_id"] for m in meta.values()})
    ordered = _ordered_demos(meta)

    entries: list[RosterEntry] = []
    has_changes = False
    prev_full: dict[str, str] | None = None  # player key name
    full_rosters: list[set[str]] = []  # sets of player keys
    name_of: dict[str, str] = {}  # player_key
    for demo_id in ordered:
        roster = roster_by_demo.get(demo_id, {})
        keys = set(roster)
        complete = len(keys) == _ROSTER_SIZE
        added: list[str] = []
        removed: list[str] = []
        # Only compare full line-ups
        if complete and prev_full is not None:
            added = sorted(roster[k] for k in keys - set(prev_full))
            removed = sorted(prev_full[k] for k in set(prev_full) - keys)
            if added or removed:
                has_changes = True
        m = meta[demo_id]
        entries.append(
            RosterEntry(
                demo_id=demo_id,
                match_date=m["date"],
                opponent=opp_names.get(m["opp_id"]) or m["opp_clan"],
                players=sorted(roster.values()),
                added=added,
                removed=removed,
                complete=complete,
            )
        )
        if complete:
            prev_full = roster
            full_rosters.append(keys)
            name_of.update(roster)  # ordered oldest 2 newest

    core_keys = set.intersection(*full_rosters) if full_rosters else set()
    core = sorted(name_of[k] for k in core_keys)

    lineups: list[RosterLineup] = []
    for lid, g in _lineup_groups(ordered, roster_by_demo).items():
        dates = sorted(d for d in (meta[i]["date"] for i in g["demos"]) if d)
        lineups.append(
            RosterLineup(
                id=lid,
                players=sorted(g["names"].values()),
                n_demos=len(g["demos"]),
                first_date=dates[0] if dates else None,
                last_date=dates[-1] if dates else None,
            )
        )

    return TeamRostersOut(
        map_id=map_id,
        team=team,
        has_changes=has_changes,
        n_demos=len(entries),
        core=core,
        entries=entries,
        lineups=lineups,
    )


def utility_heatmap(
        session: Session,
        user: User,
        *,
        map_id: str,
        teams: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        roster: str | None = None,
) -> list[ZoneUtilStat]:
    """T-side utility counts per callout zone (and type), aggregated over ``teams``."""
    conds = _base_conditions(session, user, map_id)
    if teams:
        conds.append(_teams_filter(teams))
    conds += _date_conditions(date_from, date_to)
    conds += _roster_conditions(session, user, map_id=map_id, teams=teams, roster=roster)

    rows = session.execute(
        select(UtilityEvent.zone, UtilityEvent.region, UtilityEvent.util_type, func.count())
        .join(Round, Round.id == UtilityEvent.round_id)
        .join(Demo, Demo.id == Round.demo_id)
        .where(*conds, UtilityEvent.team == "t", UtilityEvent.zone.is_not(None))
        .group_by(UtilityEvent.zone, UtilityEvent.region, UtilityEvent.util_type)
    ).all()

    agg: dict[str, dict] = {}
    for zone, region, util, n in rows:
        b = agg.setdefault(
            zone,
            {"zone": zone, "region": region, "smoke": 0,
             "flash": 0, "molotov": 0, "he": 0, "total": 0},
        )
        if util in _UTIL_TYPES:
            b[util] += n
        b["total"] += n
    return sorted(
        (ZoneUtilStat(**b) for b in agg.values()),
        key=lambda z: z.total,
        reverse=True,
    )
