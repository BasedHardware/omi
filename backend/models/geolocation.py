import json
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Geolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    address: Optional[str] = None
    location_type: Optional[str] = None
    captured_at: Optional[datetime] = None
    capture_source: Optional[Literal['current_position', 'last_known_position', 'manual', 'integration']] = None
    accuracy: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    altitude: Optional[float] = Field(default=None, allow_inf_nan=False)


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
    captured_at: Optional[datetime] = None
    capture_source: Optional[Literal['current_position', 'last_known_position', 'manual', 'integration']] = None
    accuracy: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    altitude: Optional[float] = Field(default=None, allow_inf_nan=False)


def validated_geolocation_or_none(geolocation: Optional[GeolocationInput]) -> Optional[Geolocation]:
    if geolocation is None:
        return None
    try:
        return Geolocation.model_validate(geolocation.model_dump())
    except (RecursionError, ValueError):
        return None


def geolocation_from_private_header(value: Optional[str]) -> Optional[Geolocation]:
    """Parse a bounded, authenticated transport header without ever logging coordinates."""
    # Direct endpoint calls in tests (and internal callers) can leave FastAPI's
    # Header sentinel in place. Treat every non-string as absent.
    if not isinstance(value, str) or not value or len(value) > 4096:
        return None
    try:
        payload = json.loads(value)
        return validated_geolocation_or_none(GeolocationInput.model_validate(payload))
    except (RecursionError, json.JSONDecodeError, TypeError, ValueError):
        return None
