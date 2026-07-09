from __future__ import annotations

from datetime import date

from app.auth.deps import get_current_user
from app.db import get_session
from app.demos import reparse, service
from app.domain.enums import DemoSource, DemoStatus, Visibility
from app.domain.models import Demo, User
from app.analytics.maps import bomb_damage_meta, calibration, radar_file
from app.domain.schemas import (
    BombDamageMeta,
    DemoAnalysisOut,
    DemoListOut,
    DemoOut,
    MapCalibration,
    PlayerStatOut,
    ReplayMetaOut,
    ReparseStatusOut,
    RoundOut,
    UploadResult,
    UtilityEventOut,
)
from app.parsing.replay import round_meta
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

router = APIRouter(prefix="/demos", tags=["demos"])


@router.post("/upload", response_model=UploadResult, status_code=201)
def upload_demo(
        file: UploadFile = File(...),
        visibility: Visibility = Form(Visibility.PRIVATE),
        map_id: str | None = Form(None),
        team: str | None = Form(None),
        opponent: str | None = Form(None),
        event: str | None = Form(None),
        match_date: date | None = Form(None),
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> UploadResult:
    # Only admins may publish into the shared public corpus.
    if visibility is Visibility.PUBLIC and not user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can upload public demos")
    if not (file.filename or "").lower().endswith(".dem"):
        raise HTTPException(status_code=400, detail="Expected a .dem file")

    demo, created = service.store_upload(
        session,
        user,
        file.file,
        filename=file.filename or "upload.dem",
        source=DemoSource.UPLOAD,
        visibility=visibility,
        map_id=map_id,
        team=team,
        opponent=opponent,
        event=event,
        match_date=match_date,
    )
    if created or demo.status != str(DemoStatus.PARSED):
        n_rounds, n_util = service.parse_and_store(session, demo)
    else:
        n_rounds, n_util = service.count_analysis(session, demo)
    return UploadResult(
        demo=_demo_out(session, demo), rounds=n_rounds, utility_events=n_util,
        duplicate=not created,
    )


@router.get("", response_model=DemoListOut)
def list_demos(
        map_id: str | None = None,
        team: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        limit: int = 50,
        offset: int = 0,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> DemoListOut:
    demos, total = service.list_visible(
        session, user,
        map_id=map_id, team=team, date_from=date_from, date_to=date_to,
        limit=limit, offset=offset,
    )
    ids = {i for d in demos for i in (d.team_hltv_id, d.opponent_hltv_id)}
    names = service.resolve_team_names(session, ids)
    return DemoListOut(items=[_to_out(d, names) for d in demos], total=total)


@router.get("/{demo_id}", response_model=DemoOut)
def get_demo(
        demo_id: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> DemoOut:
    return _demo_out(session, service.get_visible(session, user, demo_id))


@router.get("/{demo_id}/analysis", response_model=DemoAnalysisOut)
def demo_analysis(
        demo_id: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> DemoAnalysisOut:
    # Parsed rounds + utility for one demo (respects the demo's visibility).
    demo = service.get_visible(session, user, demo_id)
    analysis = service.load_analysis(session, demo)
    names = service.resolve_team_names(
        session,
        {demo.team_hltv_id, demo.opponent_hltv_id}
        | {r.team_hltv_id for r, _ in analysis}
        | {r.opponent_hltv_id for r, _ in analysis},
    )
    rounds = [
        RoundOut(
            id=r.id,
            round_number=r.round_number,
            map_id=r.map_id,
            team=names.get(r.team_hltv_id) or r.team,
            opponent=names.get(r.opponent_hltv_id) or r.opponent,
            buy_type=r.buy_type,
            equip_value=r.equip_value,
            target_site=r.target_site,
            winner=r.winner,
            win_reason=r.win_reason,
            utility=[
                UtilityEventOut.model_validate(u, from_attributes=True) for u in utils
            ],
        )
        for r, utils in analysis
    ]
    players = [
        PlayerStatOut.model_validate(p, from_attributes=True)
        for p in service.load_players(session, demo)
    ]
    return DemoAnalysisOut(demo=_to_out(demo, names), rounds=rounds, players=players)


@router.get("/{demo_id}/replay", response_model=ReplayMetaOut)
def demo_replay_meta(
        demo_id: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> ReplayMetaOut:
    # Per-round summary of the 2D-replay artifact (no heavy frame data).
    service.get_visible(session, user, demo_id)
    replay = service.load_replay(demo_id)
    if replay is None:
        raise HTTPException(status_code=404, detail="No replay data for this demo")
    map_id = replay["map_id"]
    cal = calibration(map_id)
    bomb = bomb_damage_meta(map_id)
    return ReplayMetaOut(
        demo_id=demo_id,
        map_id=map_id,
        sample_hz=replay["sample_hz"],
        rounds=round_meta(replay),
        has_radar=radar_file(map_id) is not None,
        calibration=MapCalibration(**cal) if cal else None,
        bomb_damage=BombDamageMeta(**bomb) if bomb else None,
    )


@router.get("/{demo_id}/replay/{round_number}")
def demo_replay_round(
        demo_id: int,
        round_number: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> dict:
    # Player frames + grenade lines for one round (the heavy payload).
    service.get_visible(session, user, demo_id)
    replay = service.load_replay(demo_id)
    if replay is None:
        raise HTTPException(status_code=404, detail="No replay data for this demo")
    for r in replay.get("rounds", []):
        if r["round_number"] == round_number:
            return r
    raise HTTPException(status_code=404, detail="Round not found in replay")


@router.post("/{demo_id}/parse", response_model=UploadResult)
def reparse_demo(
        demo_id: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> UploadResult:
    demo = service.get_visible(session, user, demo_id)
    if demo.owner_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="Only the owner can re-parse this demo")
    n_rounds, n_util = service.parse_and_store(session, demo)
    return UploadResult(demo=_to_out(demo), rounds=n_rounds, utility_events=n_util)


def _reparse_status_out(st) -> ReparseStatusOut:
    return ReparseStatusOut(
        running=st.running,
        total=st.total,
        done=st.done,
        ok=st.ok,
        failed=st.failed,
        map_id=st.map_id,
        started_at=st.started_at,
        finished_at=st.finished_at,
    )


@router.post("/reparse-all", response_model=ReparseStatusOut)
def reparse_all(
        map_id: str | None = None,
        user: User = Depends(get_current_user),
) -> ReparseStatusOut:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can re-parse all demos")
    return _reparse_status_out(reparse.start(map_id))


@router.get("/reparse-all/status", response_model=ReparseStatusOut)
def reparse_all_status(
        user: User = Depends(get_current_user),
) -> ReparseStatusOut:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can view this")
    return _reparse_status_out(reparse.status())


@router.delete("/{demo_id}", status_code=204)
def remove_demo(
        demo_id: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> None:
    demo = service.get_visible(session, user, demo_id)
    service.delete_demo(session, user, demo)


def _to_out(demo: Demo, names: dict[str, str] | None = None) -> DemoOut:
    names = names or {}
    return DemoOut(
        id=demo.id,
        owner_id=demo.owner_id,
        source=demo.source,
        status=demo.status,
        visibility=demo.visibility,
        map_id=demo.map_id,
        team=names.get(demo.team_hltv_id) or demo.team,
        opponent=names.get(demo.opponent_hltv_id) or demo.opponent,
        team_hltv_id=demo.team_hltv_id,
        opponent_hltv_id=demo.opponent_hltv_id,
        event=demo.event,
        match_date=demo.match_date,
        size_bytes=demo.size_bytes,
        error=demo.error,
        created_at=demo.created_at,
    )


def _demo_out(session: Session, demo: Demo) -> DemoOut:
    """Serialize one demo with its team names resolved from the registry"""
    names = service.resolve_team_names(
        session, {demo.team_hltv_id, demo.opponent_hltv_id}
    )
    return _to_out(demo, names)
