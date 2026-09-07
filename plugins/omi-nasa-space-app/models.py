"""Pydantic models for the NASA Space & Astronomy Intelligence Omi integration plugin."""

import datetime as dt
from datetime import datetime, timezone
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ApodRequest(BaseModel):
    """Request model for NASA Astronomy Picture of the Day (APOD)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    date: Optional[dt.date] = Field(
        default=None,
        description="The date of the APOD image to retrieve in YYYY-MM-DD format (defaults to today).",
    )
    thumbs: bool = Field(
        default=True,
        description="Whether to include thumbnail URL for video APOD items.",
    )

    @field_validator("date", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: Any) -> Any:
        if isinstance(v, str):
            v_stripped = v.strip()
            if not v_stripped:
                return None
        return v


class ApodDetail(BaseModel):
    """Parsed model representing NASA Astronomy Picture of the Day."""

    date: str
    title: str
    explanation: str
    media_type: str = "image"
    url: str
    hdurl: Optional[str] = None
    thumbnail_url: Optional[str] = None
    copyright: Optional[str] = None


class AsteroidFeedRequest(BaseModel):
    """Request model for near-Earth asteroids passing by Earth."""

    model_config = ConfigDict(str_strip_whitespace=True)

    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of near-earth asteroids to return (1-10, default 5).",
    )
    hazardous_only: bool = Field(
        default=False,
        description="Filter exclusively for asteroids classified as potentially hazardous to Earth.",
    )


class AsteroidItem(BaseModel):
    """Parsed model representing a near-Earth asteroid."""

    name: str
    estimated_diameter_min_m: float
    estimated_diameter_max_m: float
    is_potentially_hazardous: bool
    close_approach_time: datetime
    miss_distance_km: float
    relative_velocity_kmh: float

    @field_validator("close_approach_time", mode="before")
    @classmethod
    def parse_close_approach_time(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            return v.astimezone(timezone.utc) if v.tzinfo else v.replace(tzinfo=timezone.utc)
        if isinstance(v, str):
            v_str = v.strip()
            # Try formats returned by NASA NeoWs
            for fmt in ("%Y-%b-%d %H:%M", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(v_str, fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            # Try standard ISO parsing
            try:
                dt = datetime.fromisoformat(v_str)
                return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        raise ValueError(f"Unable to parse close_approach_time timestamp: {v}")


class NasaSearchRequest(BaseModel):
    """Request model for searching official NASA image and video archive."""

    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Search term (e.g. 'James Webb', 'Mars Perseverance', 'Saturn rings', 'Europa Clipper', 'Andromeda').",
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of NASA media items to return (1-10, default 5).",
    )

    @field_validator("query")
    @classmethod
    def query_must_not_be_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("query cannot be empty or whitespace only")
        return stripped


class NasaMediaSummary(BaseModel):
    """Parsed summary of a NASA multimedia asset."""

    nasa_id: str
    title: str
    date_created: str
    description: str
    center: Optional[str] = None
    thumbnail_url: Optional[str] = None
    media_type: str = "image"


class ChatToolResponse(BaseModel):
    """Standardized response format for Omi Chat Tools."""

    result: Optional[str] = None
    error: Optional[str] = None

    def __init__(self, **data: Any):
        # Support response alias if passed
        if "response" in data and "result" not in data:
            data["result"] = data.pop("response")
        super().__init__(**data)
