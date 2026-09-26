"""
Typed Pydantic models for USGS Earthquake Omi Integration.
"""

from typing import Any, Dict, Optional

try:
    from pydantic import BaseModel, Field
except ImportError:
    class BaseModel:
        def __init__(self, **kwargs):
            for key, value in kwargs.items():
                setattr(self, key, value)

    def Field(default=None, **kwargs):
        return default


class ChatToolResponse(BaseModel):
    success: bool
    message: str
    data: Optional[Dict[str, Any]] = None


class RecentEarthquakesRequest(BaseModel):
    hours: Optional[int] = Field(
        default=24,
        description="How many hours back to search. Defaults to 24 and is capped at 168.",
    )
    min_magnitude: Optional[float] = Field(
        default=2.5,
        description="Minimum earthquake magnitude. Defaults to 2.5.",
    )
    limit: Optional[int] = Field(
        default=5,
        description="Number of events to return. Defaults to 5 and is capped at 10.",
    )
    orderby: Optional[str] = Field(
        default="time",
        description="Sort order: time, time-asc, magnitude, or magnitude-asc.",
    )


class NearbyEarthquakesRequest(BaseModel):
    latitude: float = Field(
        description="Latitude in decimal degrees (-90 to 90).",
    )
    longitude: float = Field(
        description="Longitude in decimal degrees (-180 to 180).",
    )
    radius_km: Optional[float] = Field(
        default=250.0,
        description="Search radius in kilometers. Defaults to 250 and is capped at 2000.",
    )
    hours: Optional[int] = Field(
        default=168,
        description="How many hours back to search. Defaults to 168 and is capped at 168.",
    )
    min_magnitude: Optional[float] = Field(
        default=2.5,
        description="Minimum earthquake magnitude. Defaults to 2.5.",
    )
    limit: Optional[int] = Field(
        default=5,
        description="Number of events to return. Defaults to 5 and is capped at 10.",
    )


class EarthquakeDetailsRequest(BaseModel):
    event_id: str = Field(
        description="USGS event ID, such as us7000abcd.",
    )
