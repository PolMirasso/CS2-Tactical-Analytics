from __future__ import annotations

from datetime import date

from app.domain.models import Demo, Round, User
from app.domain.schemas import SiteDistributionOut, SiteStat
from sqlalchemy import func, select
from sqlalchemy.orm import Session

# Canonical plant-site order so the chart stays stable even when a site is unused.
_SITE_ORDER = ("A", "B", "Mid", "NoPlant")


def _base_conditions(session: Session, user: User, map_id: str):
    # Local import avoids an analytics→demos cycle at module load.
    from app.demos.service import _visibility_clause

    return [Round.map_id == map_id, _visibility_clause(session, user)]


def teams_for_map(session: Session, user: User, map_id: str) -> list[str]:
    """Distinct executing-team names with parsed rounds on a map, most rounds first."""
    conds = _base_conditions(session, user, map_id)
    rows = session.execute(
        select(Round.team)
        .join(Demo, Demo.id == Round.demo_id)
        .where(*conds, Round.team.is_not(None))
        .group_by(Round.team)
        .order_by(func.count().desc())
    ).all()
    return [t for (t,) in rows if t]


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
        conds.append(Round.team.ilike(f"%{team}%"))
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
