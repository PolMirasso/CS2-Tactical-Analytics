from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.analytics import aggregate
from app.analytics.maps import bomb_overlay_file, calibration, list_maps, radar_file
from app.auth.deps import get_current_user
from app.db import get_session
from app.domain.models import User
from app.domain.schemas import (
    MapCalibration,
    MapOut,
    SiteDistributionOut,
    TeamRef,
    TeamRostersOut,
    ZoneOut,
)

router = APIRouter(prefix="/maps", tags=["maps"])
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=list[MapOut])
def get_maps(session: Session = Depends(get_session)) -> list[MapOut]:
    from sqlalchemy import select as _select

    from app.domain.models import Round

    maps_with_data = {
        m for (m,) in session.execute(
            _select(Round.map_id).where(Round.map_id.is_not(None)).distinct()
        ).all()
    }
    out = []
    for m in list_maps():
        cal = calibration(m.id)
        out.append(
            MapOut(
                id=m.id,
                name=m.name,
                zones=[
                    ZoneOut(
                        id=z.id,
                        name=z.name,
                        region=z.region.value,
                        centroid=z.centroid,
                        bounds=z.bounds,
                        polygon=list(z.polygon) if z.polygon else None,
                    )
                    for z in m.zones
                ],
                has_radar=radar_file(m.id) is not None,
                has_data=m.id in maps_with_data,
                calibration=MapCalibration(**cal) if cal else None,
            )
        )
    return out


@router.get("/{map_id}/radar.png")
def get_radar(map_id: str) -> FileResponse:
    path = radar_file(map_id)
    if path is None:
        raise HTTPException(status_code=404, detail="No radar image for this map")
    return FileResponse(path, media_type="image/png")


@router.get("/{map_id}/bomb/{site}.png")
def get_bomb_overlay(map_id: str, site: str) -> FileResponse:
    path = bomb_overlay_file(map_id, site.lower())
    if path is None:
        raise HTTPException(status_code=404, detail="No bomb damage overlay for this map/site")
    return FileResponse(path, media_type="image/png")


@analytics_router.get("/teams", response_model=list[TeamRef])
def get_teams(
        map_id: str,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> list[TeamRef]:
    return aggregate.teams_for_map(session, user, map_id)


@analytics_router.get("/roster", response_model=TeamRostersOut)
def get_roster(
        map_id: str,
        team: str | None = None,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> TeamRostersOut:
    return aggregate.team_rosters(session, user, map_id=map_id, team=team)


@analytics_router.get("/site-distribution", response_model=SiteDistributionOut)
def get_site_distribution(
        map_id: str,
        team: list[str] | None = Query(None),
        buy_type: list[str] | None = Query(None),
        date_from: date | None = None,
        date_to: date | None = None,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> SiteDistributionOut:
    return aggregate.site_distribution(
        session, user,
        map_id=map_id, teams=team, buy_types=buy_type,
        date_from=date_from, date_to=date_to,
    )
