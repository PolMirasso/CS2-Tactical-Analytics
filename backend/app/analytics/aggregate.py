from __future__ import annotations

from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domain.models import Demo, Round, User, UtilityEvent
from app.domain.schemas import SiteDistributionOut, SiteStat, TeamRef, ZoneUtilStat

_UTIL_TYPES = ("smoke", "flash", "molotov", "he")

# Canonical plant-site order so the chart stays stable even when a site is unused.
_SITE_ORDER = ("A", "B", "NoPlant")


def _base_conditions(session: Session, user: User, map_id: str):
    # Local import avoids an analytics→demos cycle at module load.
    from app.demos.service import _visibility_clause

    return [Round.map_id == map_id, _visibility_clause(session, user)]


def _team_filter(team_id: str):
    """Match rounds executed by ``team_id`` (HLTV id) or a raw clan (uploads)."""
    return or_(Round.team_hltv_id == team_id, Round.team == team_id)


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
        team: str | None = None,
        buy_types: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
) -> SiteDistributionOut:
    """Historical plant-site split (and per-site win rate) over matching T rounds."""
    conds = _base_conditions(session, user, map_id)
    if team:
        conds.append(_team_filter(team))
    if buy_types:
        conds.append(Round.buy_type.in_(buy_types))
    if date_from:
        conds.append(Demo.match_date >= date_from)
    if date_to:
        conds.append(Demo.match_date <= date_to)

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
        team=team,
        total_rounds=total_rounds,
        total_demos=total_demos,
        overall_win_rate=total_wins / total_rounds if total_rounds else 0.0,
        sites=sites,
    )


def utility_heatmap(
        session: Session,
        user: User,
        *,
        map_id: str,
        team: str | None = None,
) -> list[ZoneUtilStat]:
    """T-side utility counts per callout zone (and type) for a team on a map."""
    conds = _base_conditions(session, user, map_id)
    if team:
        conds.append(_team_filter(team))

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
