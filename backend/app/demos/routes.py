from __future__ import annotations

from app.auth.deps import get_current_user
from app.db import get_session
from app.demos import service
from app.domain.enums import DemoSource, Visibility
from app.domain.models import Demo, User
from app.domain.schemas import (
    DemoAnalysisOut,
    DemoOut,
    RoundOut,
    UploadResult,
    UtilityEventOut,
)
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
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> UploadResult:
    # Only admins may publish into the shared public corpus.
    if visibility is Visibility.PUBLIC and not user.is_admin:
        raise HTTPException(status_code=403, detail="Only admins can upload public demos")
    if not (file.filename or "").lower().endswith(".dem"):
        raise HTTPException(status_code=400, detail="Expected a .dem file")

    demo = service.store_upload(
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
    )
    n_rounds, n_util = service.parse_and_store(session, demo)
    return UploadResult(demo=_to_out(demo), rounds=n_rounds, utility_events=n_util)


@router.get("", response_model=list[DemoOut])
def list_demos(
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> list[DemoOut]:
    return [_to_out(d) for d in service.list_visible(session, user)]


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
            utility=[
                UtilityEventOut.model_validate(u, from_attributes=True) for u in utils
            ],
        )
        for r, utils in service.load_analysis(session, demo)
    ]
    return DemoAnalysisOut(demo=_to_out(demo), rounds=rounds)


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
