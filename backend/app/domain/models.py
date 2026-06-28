from __future__ import annotations

from app.db import Base
from app.domain.enums import (
    DemoSource,
    DemoStatus,
    InviteStatus,
    JobStatus,
    Role,
    Visibility,
)
from datetime import date, datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default=str(Role.USER))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def is_admin(self) -> bool:
        return self.role == str(Role.ADMIN)


class Group(Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    memberships: Mapped[list[GroupMembership]] = relationship(
        back_populates="group", cascade="all, delete-orphan"
    )


class GroupMembership(Base):
    __tablename__ = "group_memberships"
    __table_args__ = (UniqueConstraint("group_id", "user_id", name="uq_group_user"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    group: Mapped[Group] = relationship(back_populates="memberships")


class Invitation(Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), index=True)
    inviter_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    invitee_email: Mapped[str] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default=str(InviteStatus.PENDING))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Demo(Base):
    __tablename__ = "demos"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source: Mapped[str] = mapped_column(String, default=str(DemoSource.UPLOAD))
    status: Mapped[str] = mapped_column(String, default=str(DemoStatus.PENDING))
    visibility: Mapped[str] = mapped_column(String, default=str(Visibility.PRIVATE), index=True)

    map_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    team: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    opponent: Mapped[str | None] = mapped_column(String, nullable=True)
    event: Mapped[str | None] = mapped_column(String, nullable=True)
    match_date: Mapped[date | None] = mapped_column(nullable=True)
    hltv_match_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    file_path: Mapped[str | None] = mapped_column(String, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class DownloadJob(Base):
    # Tracks an async HLTV demo-download/ingest run started via the API

    __tablename__ = "download_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String, default=str(JobStatus.PENDING), index=True)

    team_id: Mapped[str] = mapped_column(String)
    team_name: Mapped[str | None] = mapped_column(String, nullable=True)
    map_id: Mapped[str | None] = mapped_column(String, nullable=True)
    date_range: Mapped[str] = mapped_column(String)
    visibility: Mapped[str] = mapped_column(String)
    max_matches: Mapped[int | None] = mapped_column(nullable=True)

    matches: Mapped[int] = mapped_column(default=0)
    matches_total: Mapped[int] = mapped_column(default=0)
    demos_ingested: Mapped[int] = mapped_column(default=0)
    demos_total: Mapped[int] = mapped_column(default=0)
    # CSV of ingested demo ids (kept simple; no JSON column needed).
    demo_ids: Mapped[str | None] = mapped_column(String, nullable=True)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    demo_id: Mapped[int] = mapped_column(ForeignKey("demos.id"), index=True)
    round_number: Mapped[int] = mapped_column()
    map_id: Mapped[str] = mapped_column(String, index=True)
    team: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    opponent: Mapped[str | None] = mapped_column(String, nullable=True)
    buy_type: Mapped[str] = mapped_column(String)
    equip_value: Mapped[int] = mapped_column(default=0)
    target_site: Mapped[str] = mapped_column(String)
    winner: Mapped[str | None] = mapped_column(String, nullable=True)
    win_reason: Mapped[str | None] = mapped_column(String, nullable=True)


class UtilityEvent(Base):
    __tablename__ = "utility_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    demo_id: Mapped[int] = mapped_column(ForeignKey("demos.id"), index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), index=True)
    util_type: Mapped[str] = mapped_column(String)
    zone: Mapped[str | None] = mapped_column(String, nullable=True)
    region: Mapped[str | None] = mapped_column(String, nullable=True)
    # position in 1024-space radar pixels (drives the DeepSets model)
    radar_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    radar_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    round_time_s: Mapped[float] = mapped_column(default=0.0)
    team: Mapped[str | None] = mapped_column(String, nullable=True)


class Kill(Base):
    __tablename__ = "kills"

    id: Mapped[int] = mapped_column(primary_key=True)
    demo_id: Mapped[int] = mapped_column(ForeignKey("demos.id"), index=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"), index=True)
    round_number: Mapped[int] = mapped_column(index=True)
    time_s: Mapped[float] = mapped_column(default=0.0)
    killer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    killer_side: Mapped[str | None] = mapped_column(String, nullable=True)
    victim_name: Mapped[str | None] = mapped_column(String, nullable=True)
    victim_side: Mapped[str | None] = mapped_column(String, nullable=True)
    assister_name: Mapped[str | None] = mapped_column(String, nullable=True)
    weapon: Mapped[str | None] = mapped_column(String, nullable=True)
    headshot: Mapped[bool] = mapped_column(Boolean, default=False)
    # Victim death position (world space).
    x: Mapped[float | None] = mapped_column(Float, nullable=True)
    y: Mapped[float | None] = mapped_column(Float, nullable=True)


class PlayerStat(Base):
    __tablename__ = "player_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    demo_id: Mapped[int] = mapped_column(ForeignKey("demos.id"), index=True)
    name: Mapped[str] = mapped_column(String, index=True)
    team: Mapped[str | None] = mapped_column(String, nullable=True)
    kills: Mapped[int] = mapped_column(default=0)
    deaths: Mapped[int] = mapped_column(default=0)
    assists: Mapped[int] = mapped_column(default=0)
    headshots: Mapped[int] = mapped_column(default=0)
    rounds: Mapped[int] = mapped_column(default=0)
    adr: Mapped[float | None] = mapped_column(Float, nullable=True)
