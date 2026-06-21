from __future__ import annotations

from app.analytics.maps import calibration, list_maps, radar_file
from app.domain.schemas import MapCalibration, MapOut, ZoneOut
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(prefix="/maps", tags=["maps"])


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
