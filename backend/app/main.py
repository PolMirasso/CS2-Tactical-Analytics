from __future__ import annotations

from app.analytics.routes import router as maps_router
from app.auth.routes import router as auth_router
from app.auth.security import hash_password
from app.config import get_settings
from app.db import init_db, session_scope
from app.demos.routes import router as demos_router
from app.domain.enums import JobStatus, Role
from app.domain.models import DownloadJob, User
from app.groups.routes import router as groups_router
from app.hltv.routes import router as hltv_router
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select


def _bootstrap_admin() -> None:
    settings = get_settings()
    if not (settings.bootstrap_admin_email and settings.bootstrap_admin_password):
        return
    with session_scope() as session:
        exists = session.scalar(select(User).where(User.email == settings.bootstrap_admin_email))
        if exists is None:
            session.add(
                User(
                    email=settings.bootstrap_admin_email,
                    hashed_password=hash_password(settings.bootstrap_admin_password),
                    role=str(Role.ADMIN),
                )
            )


def _fail_orphaned_jobs() -> None:
    with session_scope() as session:
        stale = session.scalars(
            select(DownloadJob).where(
                DownloadJob.status.in_([str(JobStatus.PENDING), str(JobStatus.RUNNING)])
            )
        ).all()
        for job in stale:
            job.status = str(JobStatus.FAILED)
            job.error = "interrupted by server restart"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    _bootstrap_admin()
    _fail_orphaned_jobs()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["meta"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    for router in (
            auth_router,
            groups_router,
            demos_router,
            maps_router,
            hltv_router,
    ):
        app.include_router(router)
    return app


app = create_app()
