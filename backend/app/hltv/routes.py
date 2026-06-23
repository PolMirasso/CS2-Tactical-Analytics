from __future__ import annotations

from app.auth.deps import get_current_user, require_admin
from app.db import get_session, session_scope
from app.demos import service as demo_service
from app.domain.enums import DemoSource, JobStatus
from app.domain.models import DownloadJob, User
from app.domain.schemas import DownloadDemosIn, DownloadJobOut
from app.domain.schemas import TeamHit as TeamHitOut
from app.hltv import client
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from uuid import uuid4

router = APIRouter(prefix="/hltv", tags=["hltv"])


def _job_out(job: DownloadJob) -> DownloadJobOut:
    ids = [int(x) for x in job.demo_ids.split(",")] if job.demo_ids else []
    return DownloadJobOut(
        id=job.id,
        status=job.status,
        team_id=job.team_id,
        team_name=job.team_name,
        map_id=job.map_id,
        date_range=job.date_range,
        visibility=job.visibility,
        matches=job.matches,
        matches_total=job.matches_total,
        demos_ingested=job.demos_ingested,
        demos_total=job.demos_total,
        demo_ids=ids,
        error=job.error,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _run_download_job(job_id: str, owner_id: int, body: DownloadDemosIn) -> None:
    """Background worker: download + ingest demos, recording progress on the job.

    Each demo is committed in its own transaction so progress is visible while
    the (multi-GB, multi-minute) run is still going and a late failure does not
    discard already-ingested demos.
    """

    def _update(**fields) -> None:
        with session_scope() as session:
            job = session.get(DownloadJob, job_id)
            if job is not None:
                for key, value in fields.items():
                    setattr(job, key, value)

    _update(status=str(JobStatus.RUNNING))

    demo_ids: list[int] = []
    matches = 0
    demos_total = 0
    try:
        # Iterate lazily so each match's demos are persisted (and progress
        # reported) as soon as that archive finishes downloading.
        for archive in client.iter_team_demo_archives(
                body.team_id,
                body.map_id,
                body.date_range,
                on_total=lambda n: _update(matches_total=n),
        ):
            matches += 1
            # Each archive's demo count is only known once it's downloaded, so
            # the demos total grows as matches are processed.
            demos_total += len(archive.dem_paths)
            _update(matches=matches, demos_total=demos_total)
            try:
                for dem_path in archive.dem_paths:
                    demo_map = client.map_from_filename(dem_path.name) or body.map_id
                    with session_scope() as session:
                        owner = session.get(User, owner_id)
                        with dem_path.open("rb") as fh:
                            demo = demo_service.store_upload(
                                session,
                                owner,
                                fh,
                                filename=dem_path.name,
                                source=DemoSource.HLTV,
                                visibility=body.visibility,
                                map_id=demo_map,
                                # Tag with the real in-demo clans (a team may be
                                # renamed/rebranded vs the searched name on HLTV).
                                team=None,
                                event=archive.event,
                                match_date=archive.match_date,
                                hltv_match_id=archive.match_id,
                            )
                        demo_service.parse_and_store(session, demo)
                        demo_ids.append(demo.id)
                    _update(
                        matches=matches,
                        demos_ingested=len(demo_ids),
                        demo_ids=",".join(map(str, demo_ids)),
                    )
            finally:
                # Drop the multi-GB download once its demos are stored.
                client.cleanup_archive(archive)
    except client.HLTVError as exc:
        _update(status=str(JobStatus.FAILED), error=str(exc)[:500])
        return
    except Exception as exc:  # never leave a job stuck "running"
        _update(
            status=str(JobStatus.FAILED),
            error=f"ingest error: {exc}"[:500],
            matches=matches,
            demos_ingested=len(demo_ids),
            demo_ids=",".join(map(str, demo_ids)),
        )
        return

    _update(
        status=str(JobStatus.COMPLETED),
        matches=matches,
        demos_ingested=len(demo_ids),
        demo_ids=",".join(map(str, demo_ids)),
    )


@router.get("/search", response_model=list[TeamHitOut])
def search_teams(
        term: str = Query(min_length=2),
        _user: User = Depends(get_current_user),
) -> list[TeamHitOut]:
    try:
        hits = client.search_teams(term)
    except client.HLTVError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [TeamHitOut(id=h.id, name=h.name, url=h.url, logo=h.logo) for h in hits]


@router.post("/download", response_model=DownloadJobOut, status_code=202)
def download_demos(
        body: DownloadDemosIn,
        background_tasks: BackgroundTasks,
        admin: User = Depends(require_admin),
        session: Session = Depends(get_session),
) -> DownloadJobOut:
    # Start an async download/ingest run and return a job to poll
    job = DownloadJob(
        id=uuid4().hex,
        owner_id=admin.id,
        status=str(JobStatus.PENDING),
        team_id=body.team_id,
        team_name=body.team_name,
        map_id=body.map_id,
        date_range=str(body.date_range),
        visibility=str(body.visibility),
    )
    session.add(job)

    session.commit()
    session.refresh(job)  # load server-side created_at/updated_at
    background_tasks.add_task(_run_download_job, job.id, admin.id, body)
    return _job_out(job)


@router.get("/download/{job_id}", response_model=DownloadJobOut)
def get_download_job(
        job_id: str,
        admin: User = Depends(require_admin),
        session: Session = Depends(get_session),
) -> DownloadJobOut:
    job = session.get(DownloadJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Download job not found")
    return _job_out(job)


@router.get("/downloads", response_model=list[DownloadJobOut])
def list_download_jobs(
        admin: User = Depends(require_admin),
        session: Session = Depends(get_session),
) -> list[DownloadJobOut]:
    jobs = session.scalars(
        select(DownloadJob).order_by(DownloadJob.created_at.desc())
    ).all()
    return [_job_out(j) for j in jobs]
