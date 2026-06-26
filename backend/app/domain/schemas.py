from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.domain.enums import DateRange, Visibility


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


class DemoListOut(BaseModel):
    items: list[DemoOut]
    total: int


class UploadResult(BaseModel):
    demo: DemoOut
    rounds: int
    utility_events: int
    # True when the same file was already stored (deduped by sha256, not re-parsed).
    duplicate: bool = False


# demo analysis (parsed rounds + utility)
class UtilityEventOut(BaseModel):
    id: int
    util_type: str
    zone: str | None
    region: str | None
    round_time_s: float
    team: str | None  # side that threw it ("t" / "ct")


class RoundOut(BaseModel):
    id: int
    round_number: int
    map_id: str
    team: str | None
    opponent: str | None
    buy_type: str
    equip_value: int
    target_site: str
    winner: str | None = None
    win_reason: str | None = None
    utility: list[UtilityEventOut]


class PlayerStatOut(BaseModel):
    name: str
    team: str | None
    kills: int
    deaths: int
    assists: int
    headshots: int
    rounds: int
    adr: float | None = None


class DemoAnalysisOut(BaseModel):
    demo: DemoOut
    rounds: list[RoundOut]
    players: list[PlayerStatOut] = []


# 2D replay
class MapCalibration(BaseModel):
    # World→radar-pixel transform: px = (x - pos_x) / scale, py = (pos_y - y) / scale
    pos_x: float
    pos_y: float
    scale: float
    # Two-level maps (e.g. nuke): players below ``lower_level_max_units`` (world z)
    # project with ``lower``, which the SimpleRadar draws as a separate inset.
    lower: MapCalibration | None = None
    lower_level_max_units: float | None = None


class ReplayRoundMeta(BaseModel):
    round_number: int
    duration_s: float
    n_frames: int
    n_players: int
    n_utility: int
    winner: str | None = None


class ReplayMetaOut(BaseModel):
    demo_id: int
    map_id: str
    sample_hz: float
    rounds: list[ReplayRoundMeta]
    # Radar background for the viewer (decoupled from the /maps zone catalogue).
    has_radar: bool = False
    calibration: MapCalibration | None = None


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
    matches_total: int = 0
    demos_ingested: int
    demos_total: int = 0
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


# analytics (aggregated historical insights)
class SiteStat(BaseModel):
    site: str  # A / B / Mid / NoPlant
    rounds: int
    pct: float  # 0..1
    wins: int
    win_rate: float  # 0..1


class SiteDistributionOut(BaseModel):
    map_id: str
    team: str | None = None
    total_rounds: int
    total_demos: int
    overall_win_rate: float
    sites: list[SiteStat]


# scouting / site prediction (ML)
class UtilityInput(BaseModel):
    util_type: str  # smoke / flash / molotov / he
    zone: str | None = None
    region: str | None = None
    time_from: float | None = None
    time_to: float | None = None
    round_time_s: float = 0.0
    side: str = "t"


class PredictIn(BaseModel):
    map_id: str
    team: str | None = None
    opponent: str | None = None
    buy_type: str = "full"
    equip_value: int = 0
    utility: list[UtilityInput] = []


class SiteProb(BaseModel):
    site: str  # A / B / Mid / NoPlant
    prob: float  # 0..1


class PredictOut(BaseModel):
    map_id: str
    team: str | None = None
    predicted_site: str
    confidence: float
    source: str  # "model" (MLP) or "baseline" (historical base rate fallback)
    sites: list[SiteProb]
    baseline: list[SiteProb]


class ZoneUtilStat(BaseModel):
    zone: str
    region: str | None = None
    smoke: int = 0
    flash: int = 0
    molotov: int = 0
    he: int = 0
    total: int = 0


class TendenciesOut(BaseModel):
    map_id: str
    team: str | None = None
    total_rounds: int
    sites: list[SiteStat]
    heatmap: list[ZoneUtilStat]


class ModelStatusOut(BaseModel):
    trained: bool
    trained_at: datetime | None = None
    n_rounds: int = 0
    n_teams: int = 0
    classes: list[str] = []
    accuracy: float | None = None
    baseline_accuracy: float | None = None
    params: dict[str, str] | None = None


# maps
class ZoneOut(BaseModel):
    id: str
    name: str
    region: str
    centroid: tuple[float, float]
    bounds: tuple[float, float, float, float]  # world x_min, y_min, x_max, y_max
    polygon: list[tuple[float, float]] | None = None


class MapOut(BaseModel):
    id: str
    name: str
    zones: list[ZoneOut]
    # Present only when awpy radar assets + calibration exist for the map.
    has_radar: bool = False
    calibration: MapCalibration | None = None
