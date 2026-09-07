"""
Pydantic data models for Omi OpenSky Flight Tracker Integration App.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ChatToolResponse(BaseModel):
    """
    Standard Omi response format for chat tool endpoints.
    Either `result` contains the voice-optimized response or `error` details the issue.
    """
    result: Optional[str] = None
    error: Optional[str] = None


class FlightsOverheadRequest(BaseModel):
    """Request model for finding aircraft overhead or near a geographic location."""
    latitude: Optional[float] = Field(
        default=None,
        ge=-90.0,
        le=90.0,
        description="Observer latitude in decimal degrees (-90.0 to 90.0)."
    )
    longitude: Optional[float] = Field(
        default=None,
        ge=-180.0,
        le=180.0,
        description="Observer longitude in decimal degrees (-180.0 to 180.0)."
    )
    location: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Named city or airport (e.g. 'London', 'New York', 'Tokyo', 'Paris') if coordinates not provided."
    )
    radius_km: float = Field(
        default=30.0,
        gt=0.0,
        le=150.0,
        description="Search radius in kilometers around the observer (max 150 km)."
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of nearby aircraft to return."
    )

    @field_validator("location")
    @classmethod
    def clean_location(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v = v.strip()
            if not v:
                return None
        return v


class TrackFlightRequest(BaseModel):
    """Request model for tracking a specific flight by callsign or ICAO 24-bit address."""
    callsign: str = Field(
        ...,
        min_length=2,
        max_length=12,
        description="Commercial flight callsign (e.g. 'UAL123', 'DLH400', 'BAW28') or 6-character hex ICAO address."
    )

    @field_validator("callsign")
    @classmethod
    def normalize_callsign(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not cleaned:
            raise ValueError("Callsign cannot be empty.")
        return cleaned


class AirspaceActivityRequest(BaseModel):
    """Request model for summarizing active air traffic across a region or country."""
    country: Optional[str] = Field(
        default=None,
        max_length=80,
        description="Country of aircraft registration to filter by (e.g. 'United States', 'United Kingdom', 'Germany')."
    )
    location: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Major metro area or airspace hub (e.g. 'New York', 'Frankfurt', 'London')."
    )
    min_altitude_meters: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Filter for aircraft above a minimum barometric altitude in meters (e.g. 9000 for cruising flight)."
    )
    limit: int = Field(
        default=8,
        ge=1,
        le=25,
        description="Maximum number of aircraft to list in the regional summary."
    )
