from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domain.models import Demo, Round, User, UtilityEvent
from app.ml.features import round_context, round_tokens, timing_label


def build_dataset(
    session: Session, user: User
) -> tuple[list[dict], list[str], list[str | None], dict]:
    # all visible T-side rounds (samples, target sites, timing labels, meta)
    from app.demos.service import _visibility_clause

    rounds = list(
        session.scalars(
            select(Round)
            .join(Demo, Demo.id == Round.demo_id)
            .where(
                _visibility_clause(session, user),
                or_(Round.team_hltv_id.is_not(None), Round.team.is_not(None)),
            )
        )
    )
    if not rounds:
        return [], [], [], {"n_rounds": 0, "n_teams": 0}

    util_by_round: dict[int, list[UtilityEvent]] = {}
    for u in session.scalars(
        select(UtilityEvent).where(UtilityEvent.round_id.in_([r.id for r in rounds]))
    ):
        util_by_round.setdefault(u.round_id, []).append(u)

    samples: list[dict] = []
    targets: list[str] = []
    timing_targets: list[str | None] = []
    teams: set[str] = set()
    for r in rounds:
        util = util_by_round.get(r.id, [])
        team = r.team_hltv_id or r.team
        opponent = r.opponent_hltv_id or r.opponent
        samples.append(
            {
                "tokens": round_tokens(r.map_id, util),
                "context": round_context(
                    map_id=r.map_id,
                    team=team,
                    opponent=opponent,
                    buy_type=r.buy_type,
                    equip_value=r.equip_value,
                    utility=util,
                ),
            }
        )
        targets.append(r.target_site)
        timing_targets.append(timing_label(getattr(r, "plant_time_s", None)))
        if team:
            teams.add(team)
    return samples, targets, timing_targets, {"n_rounds": len(samples), "n_teams": len(teams)}
