"""Pydantic models for Omi World Time & Solar Ephemeris Integration App."""

from datetime import date as dt_date
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    model_config = ConfigDict(extra="ignore")

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class GetCurrentTimeRequest(BaseModel):
    """Request model for getting current time in a city or timezone."""

    model_config = ConfigDict(extra="ignore")

    location: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="City name (e.g. 'Tokyo', 'London', 'New York') or IANA timezone (e.g. 'Asia/Tokyo', 'UTC').",
    )

    @field_validator("location")
    @classmethod
    def sanitize_location(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Location must not be empty.")
        return cleaned


class CalculateTimeDifferenceRequest(BaseModel):
    """Request model for converting time or calculating difference between two locations."""

    model_config = ConfigDict(extra="ignore")

    source_location: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Source city or IANA timezone (e.g. 'New York', 'America/New_York').",
    )
    target_location: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Target city or IANA timezone (e.g. 'Tokyo', 'Asia/Tokyo').",
    )
    source_time: Optional[str] = Field(
        default=None,
        max_length=30,
        description="Optional time in HH:MM or YYYY-MM-DD HH:MM format (e.g. '14:30' or '2026-09-08 14:30'). Defaults to current time if omitted.",
    )

    @field_validator("source_location", "target_location")
    @classmethod
    def sanitize_locations(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Location must not be empty.")
        return cleaned


class GetSolarTimesRequest(BaseModel):
    """Request model for getting sunrise, sunset, and solar ephemeris for a location."""

    model_config = ConfigDict(extra="ignore")

    location: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="City name or location (e.g. 'Paris', 'San Francisco', 'Sydney').",
    )
    date: Optional[str] = Field(
        default=None,
        max_length=10,
        description="Optional date in YYYY-MM-DD format (e.g. '2026-09-08'). Defaults to today if omitted.",
    )

    @field_validator("location")
    @classmethod
    def sanitize_location(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Location must not be empty.")
        return cleaned

    @field_validator("date")
    @classmethod
    def validate_date(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        try:
            parsed = dt_date.fromisoformat(v)
            return parsed.isoformat()
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format (e.g. '2026-09-08').")

