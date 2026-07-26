from typing import Optional

from pydantic import BaseModel, Field


class Geolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: Optional[str] = None
    location_type: Optional[str] = None
