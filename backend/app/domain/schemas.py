from __future__ import annotations

from app.domain.enums import DateRange, Visibility
from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


# auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    role: str
    created_at: datetime


# groups
class GroupCreateIn(BaseModel):
    name: str = Field(min_length=1)


class GroupOut(BaseModel):
    id: int
    name: str
    owner_id: int
    member_count: int
    is_owner: bool


class InviteIn(BaseModel):
    email: EmailStr


class InvitationOut(BaseModel):
    id: int
    group_id: int
    group_name: str
    inviter_email: str
    status: str
    created_at: datetime


# demos
class DemoOut(BaseModel):
    id: int
    owner_id: int
    source: str
    status: str
    visibility: str
    map_id: str | None
    team: str | None
    opponent: str | None
    event: str | None
    match_date: date | None
    size_bytes: int | None
    error: str | None
    created_at: datetime


class UploadResult(BaseModel):
    demo: DemoOut
    rounds: int
    utility_events: int


# HLTV
class TeamHit(BaseModel):
    id: str
    name: str
    url: str
    logo: str | None = None


class DownloadJobOut(BaseModel):
    id: str
    status: str
    team_id: str
    team_name: str | None = None
    map_id: str | None = None
    date_range: str
    visibility: str
    matches: int
    demos_ingested: int
    demo_ids: list[int]
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class DownloadDemosIn(BaseModel):
    team_id: str
    team_name: str | None = None
    map_id: str | None = None
    date_range: DateRange = DateRange.LAST_3_MONTHS
    visibility: Visibility = Visibility.PUBLIC


# maps
class ZoneOut(BaseModel):
    id: str
    name: str
    region: str
    centroid: tuple[float, float]


class MapOut(BaseModel):
    id: str
    name: str
    zones: list[ZoneOut]
