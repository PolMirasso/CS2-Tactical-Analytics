from __future__ import annotations

from datetime import date

from app.auth.deps import get_current_user
from app.db import get_session
from app.demos import service
from app.domain.enums import DemoSource, DemoStatus, Visibility
from app.domain.models import Demo, User
from app.analytics.maps import calibration, radar_file
from app.domain.schemas import (
    DemoAnalysisOut,
    DemoListOut,
    DemoOut,
    MapCalibration,
    PlayerStatOut,
    ReplayMetaOut,
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
        demo=_to_out(demo), rounds=n_rounds, utility_events=n_util, duplicate=not created
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
    return DemoListOut(items=[_to_out(d) for d in demos], total=total)


@router.get("/{demo_id}", response_model=DemoOut)
def get_demo(
        demo_id: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> DemoOut:
    return _to_out(service.get_visible(session, user, demo_id))


@router.get("/{demo_id}/analysis", response_model=DemoAnalysisOut)
def demo_analysis(
        demo_id: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> DemoAnalysisOut:
    # Parsed rounds + utility for one demo (respects the demo's visibility).
    demo = service.get_visible(session, user, demo_id)
    rounds = [
        RoundOut(
            id=r.id,
            round_number=r.round_number,
            map_id=r.map_id,
            team=r.team,
            opponent=r.opponent,
            buy_type=r.buy_type,
            equip_value=r.equip_value,
            target_site=r.target_site,
            winner=r.winner,
            win_reason=r.win_reason,
            utility=[
                UtilityEventOut.model_validate(u, from_attributes=True) for u in utils
            ],
        )
        for r, utils in service.load_analysis(session, demo)
    ]
    players = [
        PlayerStatOut.model_validate(p, from_attributes=True)
        for p in service.load_players(session, demo)
    ]
    return DemoAnalysisOut(demo=_to_out(demo), rounds=rounds, players=players)


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
    return ReplayMetaOut(
        demo_id=demo_id,
        map_id=map_id,
        sample_hz=replay["sample_hz"],
        rounds=round_meta(replay),
        has_radar=radar_file(map_id) is not None,
        calibration=MapCalibration(**cal) if cal else None,
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


@router.delete("/{demo_id}", status_code=204)
def remove_demo(
        demo_id: int,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> None:
    demo = service.get_visible(session, user, demo_id)
    service.delete_demo(session, user, demo)


def _to_out(demo: Demo) -> DemoOut:
    return DemoOut.model_validate(demo, from_attributes=True)
