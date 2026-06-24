from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from datetime import date
from app.config import get_settings
from app.domain.enums import DemoSource, DemoStatus, Visibility
from app.domain.models import Demo, Kill, PlayerStat, Round, User, UtilityEvent
from app.groups.service import group_peer_ids
from app.parsing.parser import ParseError
from app.parsing.runner import run_parse
from app.parsing.replay import replay_to_dict
from fastapi import HTTPException
from pathlib import Path
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session
from typing import BinaryIO

_CHUNK = 1 << 20  # 1 MiB


def replay_path(demo_id: int) -> Path:
    """Filesystem path of a demo's 2D-replay artifact (derived from its id)."""
    return get_settings().replays_dir / f"{demo_id}.json.gz"


def _write_replay(demo_id: int, replay) -> None:
    path = replay_path(demo_id)
    if replay is None:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        json.dump(replay_to_dict(replay), fh, separators=(",", ":"))


def load_replay(demo_id: int) -> dict | None:
    """Read the gzip-JSON replay artifact, or ``None`` if it was never built."""
    path = replay_path(demo_id)
    if not path.exists():
        return None
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


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
        match_date: date | None = None,
        hltv_match_id: str | None = None,
) -> tuple[Demo, bool]:
    """Persist an uploaded demo file, deduped per-owner by sha256.

    Returns ``(demo, created)``; ``created`` is ``False`` when the same file was
    already stored, so the caller can skip a redundant re-parse.
    """
    settings = get_settings()
    tmp = settings.demos_dir / f".incoming-{owner.id}-{filename}"
    sha, size = _hash_and_save(fileobj, tmp)

    existing = session.scalar(
        select(Demo).where(Demo.owner_id == owner.id, Demo.sha256 == sha)
    )
    if existing is not None:
        tmp.unlink(missing_ok=True)
        return existing, False

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
        match_date=match_date,
        hltv_match_id=hltv_match_id,
        file_path=str(final),
        sha256=sha,
        size_bytes=size,
    )
    session.add(demo)
    session.flush()
    return demo, True


def count_analysis(session: Session, demo: Demo) -> tuple[int, int]:
    """(n_rounds, n_utility) already stored for a demo, without loading the rows."""
    n_rounds = session.scalar(
        select(func.count()).select_from(Round).where(Round.demo_id == demo.id)
    ) or 0
    n_util = session.scalar(
        select(func.count()).select_from(UtilityEvent).where(UtilityEvent.demo_id == demo.id)
    ) or 0
    return n_rounds, n_util


def parse_and_store(session: Session, demo: Demo) -> tuple[int, int]:
    # Parse ``demo`` into rounds + utility events. Returns (n_rounds, n_utility)
    # Wipe any prior parse so re-parsing is idempotent
    session.execute(delete(UtilityEvent).where(UtilityEvent.demo_id == demo.id))
    session.execute(delete(Kill).where(Kill.demo_id == demo.id))
    session.execute(delete(PlayerStat).where(PlayerStat.demo_id == demo.id))
    session.execute(delete(Round).where(Round.demo_id == demo.id))
    replay_path(demo.id).unlink(missing_ok=True)

    try:
        parsed = run_parse(
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
            winner=r.winner,
            win_reason=r.win_reason,
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

    for k in parsed.kills:
        rid = round_id_by_number.get(k.round_number)
        if rid is None:
            continue
        session.add(
            Kill(
                demo_id=demo.id,
                round_id=rid,
                round_number=k.round_number,
                time_s=k.time_s,
                killer_name=k.killer_name,
                killer_side=k.killer_side,
                victim_name=k.victim_name,
                victim_side=k.victim_side,
                assister_name=k.assister_name,
                weapon=k.weapon,
                headshot=k.headshot,
                x=k.x,
                y=k.y,
            )
        )

    for p in parsed.player_stats:
        session.add(
            PlayerStat(
                demo_id=demo.id,
                name=p.name,
                team=p.team,
                kills=p.kills,
                deaths=p.deaths,
                assists=p.assists,
                headshots=p.headshots,
                rounds=p.rounds,
                adr=p.adr,
            )
        )

    _write_replay(demo.id, parsed.replay)

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


def list_visible(
        session: Session,
        user: User,
        *,
        map_id: str | None = None,
        team: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int | None = None,
        offset: int = 0,
) -> tuple[list[Demo], int]:
    """Visible demos matching the filters, plus the unpaginated total count."""
    conds = [_visibility_clause(session, user)]
    if map_id:
        conds.append(Demo.map_id == map_id)
    if team:
        like = f"%{team}%"
        conds.append(or_(Demo.team.ilike(like), Demo.opponent.ilike(like)))
    if date_from:
        conds.append(Demo.match_date >= date_from)
    if date_to:
        conds.append(Demo.match_date <= date_to)

    total = session.scalar(select(func.count()).select_from(Demo).where(*conds)) or 0
    q = select(Demo).where(*conds).order_by(Demo.created_at.desc())
    if limit is not None:
        q = q.limit(limit).offset(offset)
    return list(session.scalars(q)), total


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


def load_players(session: Session, demo: Demo) -> list[PlayerStat]:
    """Per-player scoreboard for a demo, ordered by kills."""
    return list(
        session.scalars(
            select(PlayerStat)
            .where(PlayerStat.demo_id == demo.id)
            .order_by(PlayerStat.kills.desc())
        )
    )


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
    replay_path(demo.id).unlink(missing_ok=True)
    # Remove the file only if no other demo row references the same stored blob.
    if demo.file_path:
        others = session.scalar(
            select(Demo.id).where(Demo.sha256 == demo.sha256, Demo.id != demo.id)
        )
        if others is None:
            Path(demo.file_path).unlink(missing_ok=True)
    session.delete(demo)
    session.flush()
