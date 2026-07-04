from __future__ import annotations

import difflib
import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import get_settings
from app.db import session_scope
from app.demos.service import upsert_team
from app.domain.models import Demo, Round
from app.hltv import client


@dataclass
class BackfillState:
    running: bool = False
    total: int = 0
    done: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None


_state = BackfillState()
_lock = threading.Lock()


def status() -> BackfillState:
    with _lock:
        return BackfillState(**_state.__dict__)


def start() -> BackfillState:
    # backfill HLTV team ids for every demo that has a match id but no opponent id
    global _state
    with _lock:
        if _state.running:
            return BackfillState(**_state.__dict__)
        _state = BackfillState(running=True, started_at=datetime.now(UTC))
    threading.Thread(target=_run, daemon=True).start()
    return status()


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _clan_to_id(clans: list[str], teams: list[tuple[str, str]]) -> dict[str, str]:
    """Map each in-demo clan to the best-matching HLTV team id.

    For the usual 2-clan / 2-team case we pick the pairing that maximises total
    name similarity so the two clans never collapse onto the same id.
    """
    def score(clan: str, name: str) -> float:
        c, n = _norm(clan), _norm(name)
        if not c or not n:
            return 0.0
        if c == n:
            return 3.0
        if c in n or n in c:
            return 2.0
        return difflib.SequenceMatcher(None, c, n).ratio()

    if len(clans) == 2 and len(teams) == 2:
        (c0, c1), (t0, t1) = clans, teams
        straight = score(c0, t0[1]) + score(c1, t1[1])
        swapped = score(c0, t1[1]) + score(c1, t0[1])
        if swapped > straight:
            return {c0: t1[0], c1: t0[0]}
        return {c0: t0[0], c1: t1[0]}

    out: dict[str, str] = {}
    for clan in clans:
        best_id, best = None, -1.0
        for tid, name in teams:
            s = score(clan, name)
            if s > best:
                best, best_id = s, tid
        if best_id is not None:
            out[clan] = best_id
    return out


def _backfill_one(session, demo: Demo) -> str:
    """Returns 'updated' | 'skipped' for one demo."""
    if not demo.hltv_match_id:
        return "skipped"
    settings = get_settings()
    html = client._flaresolverr_get(
        f"{settings.hltv_base_url}/matches/{demo.hltv_match_id}/x"
    )
    teams = client._parse_match_teams(html)
    if len(teams) < 2:
        return "skipped"

    for tid, name in teams:
        upsert_team(session, tid, name)

    ids = [tid for tid, _ in teams]
    our_id = demo.team_hltv_id if demo.team_hltv_id in ids else ids[0]
    opp_id = next((tid for tid in ids if tid != our_id), None)
    demo.team_hltv_id = our_id
    demo.opponent_hltv_id = opp_id

    rounds = list(session.scalars(select(Round).where(Round.demo_id == demo.id)))
    clans = {r.team for r in rounds if r.team} | {r.opponent for r in rounds if r.opponent}
    clan_to_id = _clan_to_id(sorted(clans), teams)
    for r in rounds:
        r.team_hltv_id = clan_to_id.get(r.team)
        r.opponent_hltv_id = clan_to_id.get(r.opponent)

    demo.team = None
    demo.opponent = None
    session.flush()
    return "updated"


def _run() -> None:
    try:
        with session_scope() as session:
            ids = [
                i for i in session.scalars(
                    select(Demo.id).where(Demo.hltv_match_id.is_not(None))
                )
            ]
        with _lock:
            _state.total = len(ids)
        for did in ids:
            try:
                with session_scope() as session:
                    demo = session.get(Demo, did)
                    result = _backfill_one(session, demo) if demo else "skipped"
                with _lock:
                    if result == "updated":
                        _state.updated += 1
                    else:
                        _state.skipped += 1
            except Exception:
                with _lock:
                    _state.failed += 1
            with _lock:
                _state.done += 1
    finally:
        with _lock:
            _state.running = False
            _state.finished_at = datetime.now(UTC)
