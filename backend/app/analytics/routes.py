from __future__ import annotations

from app.analytics.maps import list_maps
from app.domain.schemas import MapOut, ZoneOut
from fastapi import APIRouter

router = APIRouter(prefix="/maps", tags=["maps"])


@router.get("", response_model=list[MapOut])
def get_maps() -> list[MapOut]:
    return [
        MapOut(
            id=m.id,
            name=m.name,
            zones=[
                ZoneOut(id=z.id, name=z.name, region=z.region.value, centroid=z.centroid)
                for z in m.zones
            ],
        )
        for m in list_maps()
    ]
