from __future__ import annotations

from datetime import date

from app.analytics import aggregate
from app.analytics.maps import calibration, list_maps, radar_file
from app.auth.deps import get_current_user
from app.db import get_session
from app.domain.models import User
from app.domain.schemas import MapCalibration, MapOut, SiteDistributionOut, ZoneOut
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

router = APIRouter(prefix="/maps", tags=["maps"])
analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=list[MapOut])
def get_maps() -> list[MapOut]:
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


@analytics_router.get("/teams", response_model=list[str])
def get_teams(
        map_id: str,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> list[str]:
    return aggregate.teams_for_map(session, user, map_id)


@analytics_router.get("/site-distribution", response_model=SiteDistributionOut)
def get_site_distribution(
        map_id: str,
        team: str | None = None,
        buy_type: list[str] | None = Query(None),
        date_from: date | None = None,
        date_to: date | None = None,
        user: User = Depends(get_current_user),
        session: Session = Depends(get_session),
) -> SiteDistributionOut:
    return aggregate.site_distribution(
        session, user,
        map_id=map_id, team=team, buy_types=buy_type,
        date_from=date_from, date_to=date_to,
    )
