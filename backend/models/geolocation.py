from typing import Optional

from pydantic import BaseModel, Field


class Geolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: Optional[str] = None
    location_type: Optional[str] = None


class GeolocationInput(BaseModel):
    """Released wire contract for coordinates accepted at legacy API boundaries.

    Bounds are enforced before any value is cached, geocoded, or persisted. Keeping
    this transport shape broad preserves clients released before the bound contract
    existed, while ``Geolocation`` remains the only usable server-side value.
    """

    google_place_id: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    location_type: Optional[str] = None


def validated_geolocation_or_none(geolocation: Optional[GeolocationInput]) -> Optional[Geolocation]:
    if geolocation is None:
        return None
    try:
        return Geolocation.model_validate(geolocation.model_dump())
    except ValueError:
        return None
