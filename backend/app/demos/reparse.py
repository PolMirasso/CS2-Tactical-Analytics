from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from app.db import session_scope
from app.demos.service import apply_canonical_teams, parse_and_store, team_name
from app.domain.models import Demo


@dataclass
class ReparseState:
    running: bool = False
    total: int = 0
    done: int = 0
    ok: int = 0
    failed: int = 0
    map_id: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


_state = ReparseState()
_lock = threading.Lock()


def status() -> ReparseState:
    with _lock:
        return ReparseState(**_state.__dict__)


def start(map_id: str | None = None) -> ReparseState:
    """Kick off a background re-parse of every demo (optionally one map)."""
    global _state
    with _lock:
        if _state.running:
            return ReparseState(**_state.__dict__)
        _state = ReparseState(running=True, map_id=map_id, started_at=datetime.now(UTC))
    threading.Thread(target=_run, args=(map_id,), daemon=True).start()
    return status()


def _run(map_id: str | None) -> None:
    try:
        with session_scope() as session:
            q = select(Demo.id)
            if map_id:
                q = q.where(Demo.map_id == map_id)
            ids = [i for i in session.scalars(q)]
        with _lock:
            _state.total = len(ids)
        for did in ids:
            try:
                with session_scope() as session:
                    demo = session.get(Demo, did)
                    if demo is not None:
                        # tag rounds with the demo's HLTV ids
                        hint = team_name(session, demo.team_hltv_id)
                        parse_and_store(session, demo, team_hint=hint)
                        if demo.team_hltv_id:
                            apply_canonical_teams(
                                session, demo,
                                team_hltv_id=demo.team_hltv_id,
                                opponent_hltv_id=demo.opponent_hltv_id,
                            )
                with _lock:
                    _state.ok += 1
            except Exception:
                with _lock:
                    _state.failed += 1
            with _lock:
                _state.done += 1
    finally:
        with _lock:
            _state.running = False
            _state.finished_at = datetime.now(UTC)
