from __future__ import annotations

import hashlib
import shutil
from app.config import get_settings
from app.domain.enums import DemoSource, DemoStatus, Visibility
from app.domain.models import Demo, Round, User, UtilityEvent
from app.groups.service import group_peer_ids
from app.parsing.parser import ParseError, parse_demo
from fastapi import HTTPException
from pathlib import Path
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from typing import BinaryIO

_CHUNK = 1 << 20  # 1 MiB


def _hash_and_save(src: BinaryIO, dest: Path) -> tuple[str, int]:
    """Stream ``src`` to ``dest`` while hashing; returns (sha256, size_bytes)."""
    sha = hashlib.sha256()
    size = 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as out:
        while chunk := src.read(_CHUNK):
            sha.update(chunk)
            size += len(chunk)
            out.write(chunk)
    return sha.hexdigest(), size


def store_upload(
        session: Session,
        owner: User,
        fileobj: BinaryIO,
        *,
        filename: str,
        source: DemoSource = DemoSource.UPLOAD,
        visibility: Visibility = Visibility.PRIVATE,
        map_id: str | None = None,
        team: str | None = None,
        opponent: str | None = None,
        event: str | None = None,
        hltv_match_id: str | None = None,
) -> Demo:
    """Persist an uploaded demo file (dedup per-owner by sha256)."""
    settings = get_settings()
    tmp = settings.demos_dir / f".incoming-{owner.id}-{filename}"
    sha, size = _hash_and_save(fileobj, tmp)

    existing = session.scalar(
        select(Demo).where(Demo.owner_id == owner.id, Demo.sha256 == sha)
    )
    if existing is not None:
        tmp.unlink(missing_ok=True)
        return existing

    final = settings.demos_dir / f"{sha}.dem"
    if final.exists():
        tmp.unlink(missing_ok=True)
    else:
        shutil.move(str(tmp), final)

    demo = Demo(
        owner_id=owner.id,
        source=str(source),
        status=str(DemoStatus.PENDING),
        visibility=str(visibility),
        map_id=map_id,
        team=team,
        opponent=opponent,
        event=event,
        hltv_match_id=hltv_match_id,
        file_path=str(final),
        sha256=sha,
        size_bytes=size,
    )
    session.add(demo)
    session.flush()
    return demo


def parse_and_store(session: Session, demo: Demo) -> tuple[int, int]:
    # Parse ``demo`` into rounds + utility events. Returns (n_rounds, n_utility)
    # Wipe any prior parse so re-parsing is idempotent
    session.execute(delete(UtilityEvent).where(UtilityEvent.demo_id == demo.id))
    session.execute(delete(Round).where(Round.demo_id == demo.id))

    try:
        parsed = parse_demo(
            Path(demo.file_path) if demo.file_path else Path(),
            map_hint=demo.map_id,
            team_hint=demo.team,
        )
    except ParseError as exc:
        demo.status = str(DemoStatus.FAILED)
        demo.error = str(exc)[:500]
        session.flush()
        return (0, 0)

    demo.map_id = parsed.map_id
    demo.team = demo.team or parsed.team
    demo.opponent = demo.opponent or parsed.opponent

    round_id_by_number: dict[int, int] = {}
    for r in parsed.rounds:
        row = Round(
            demo_id=demo.id,
            round_number=r.round_number,
            map_id=parsed.map_id,
            team=r.team or parsed.team,
            opponent=r.opponent or parsed.opponent,
            buy_type=r.buy_type,
            equip_value=r.equip_value,
            target_site=r.target_site,
        )
        session.add(row)
        session.flush()
        round_id_by_number[r.round_number] = row.id

    for u in parsed.utility:
        rid = round_id_by_number.get(u.round_number)
        if rid is None:
            continue
        session.add(
            UtilityEvent(
                demo_id=demo.id,
                round_id=rid,
                util_type=u.util_type,
                zone=u.zone_id,
                region=u.region,
                round_time_s=u.round_time_s,
                team=u.side,
            )
        )

    demo.status = str(DemoStatus.PARSED)
    demo.error = None
    session.flush()
    return (len(parsed.rounds), len(parsed.utility))


# visibility
def _visibility_clause(session: Session, user: User):
    """SQLAlchemy clause selecting demos ``user`` is allowed to see."""
    if user.is_admin:
        return Demo.id.is_not(None)
    peer_ids = group_peer_ids(session, user.id)
    allowed_owner_ids = peer_ids | {user.id}
    return (Demo.visibility == str(Visibility.PUBLIC)) | (
        Demo.owner_id.in_(allowed_owner_ids)
    )


def list_visible(session: Session, user: User) -> list[Demo]:
    return list(
        session.scalars(
            select(Demo).where(_visibility_clause(session, user)).order_by(Demo.created_at.desc())
        )
    )


def load_analysis(
        session: Session, demo: Demo
) -> list[tuple[Round, list[UtilityEvent]]]:
    """Return the demo's rounds (ordered) each paired with its utility events."""
    rounds = list(
        session.scalars(
            select(Round).where(Round.demo_id == demo.id).order_by(Round.round_number)
        )
    )
    utils = list(
        session.scalars(select(UtilityEvent).where(UtilityEvent.demo_id == demo.id))
    )
    by_round: dict[int, list[UtilityEvent]] = {}
    for u in utils:
        by_round.setdefault(u.round_id, []).append(u)
    for events in by_round.values():
        events.sort(key=lambda e: e.round_time_s)
    return [(r, by_round.get(r.id, [])) for r in rounds]


def get_visible(session: Session, user: User, demo_id: int) -> Demo:
    demo = session.get(Demo, demo_id)
    if demo is None:
        raise HTTPException(status_code=404, detail="Demo not found")
    visible = session.scalar(
        select(Demo.id).where(Demo.id == demo_id, _visibility_clause(session, user))
    )
    if visible is None:
        raise HTTPException(status_code=403, detail="Not allowed to access this demo")
    return demo


def delete_demo(session: Session, user: User, demo: Demo) -> None:
    if demo.owner_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Only the owner can delete this demo")
    session.execute(delete(UtilityEvent).where(UtilityEvent.demo_id == demo.id))
    session.execute(delete(Round).where(Round.demo_id == demo.id))
    # Remove the file only if no other demo row references the same stored blob.
    if demo.file_path:
        others = session.scalar(
            select(Demo.id).where(Demo.sha256 == demo.sha256, Demo.id != demo.id)
        )
        if others is None:
            Path(demo.file_path).unlink(missing_ok=True)
    session.delete(demo)
    session.flush()
