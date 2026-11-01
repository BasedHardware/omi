"""Pydantic models for Omi CityBikes Global Micro-Mobility & Transit Integration App."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class SearchNetworksRequest(BaseModel):
    """Request model for finding bike-share networks by city, country, or system name."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="City name, country code, or network brand (e.g. 'Paris', 'New York', 'Citi Bike', 'London').",
    )
    limit: int = Field(
        5,
        ge=1,
        le=20,
        description="Maximum number of networks to return (1-20, default 5).",
    )

    @field_validator("query")
    @classmethod
    def clean_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Search query cannot be empty.")
        return cleaned


class NearbyStationsRequest(BaseModel):
    """Request model for searching bike stations within a specific network."""

    network_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="CityBikes network ID (e.g. 'citi-bike-nyc', 'velib-metropole', 'santander-cycles').",
    )
    query: Optional[str] = Field(
        None,
        max_length=100,
        description="Optional street or station name filter (e.g. 'Broadway', 'Union Square', 'Eiffel').",
    )
    latitude: Optional[float] = Field(
        None,
        ge=-90.0,
        le=90.0,
        description="Optional GPS latitude to sort stations by physical distance.",
    )
    longitude: Optional[float] = Field(
        None,
        ge=-180.0,
        le=180.0,
        description="Optional GPS longitude to sort stations by physical distance.",
    )
    limit: int = Field(
        5,
        ge=1,
        le=25,
        description="Number of stations to return (1-25, default 5).",
    )

    @field_validator("network_id")
    @classmethod
    def clean_network_id(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("Network ID cannot be empty.")
        return cleaned

    @field_validator("query")
    @classmethod
    def clean_optional_query(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = v.strip()
        return cleaned if cleaned else None

    @model_validator(mode="after")
    def validate_coordinate_pair(self):
        has_lat = self.latitude is not None
        has_lon = self.longitude is not None
        if has_lat != has_lon:
            raise ValueError("Both latitude and longitude must be provided together for distance sorting.")
        return self


class StationStatusRequest(BaseModel):
    """Request model for checking detailed live status of a specific bike station."""

    network_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="CityBikes network ID (e.g. 'citi-bike-nyc').",
    )
    station_id_or_name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Station ID or station name to check.",
    )

    @field_validator("network_id")
    @classmethod
    def clean_network_id(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("Network ID cannot be empty.")
        return cleaned

    @field_validator("station_id_or_name")
    @classmethod
    def clean_station_id_or_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Station ID or name cannot be empty.")
        return cleaned


class CityOverviewRequest(BaseModel):
    """Request model for high-level citywide bike transit statistics."""

    city_or_network: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="City name (e.g. 'Barcelona') or CityBikes network ID (e.g. 'bicing').",
    )

    @field_validator("city_or_network")
    @classmethod
    def clean_identifier(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("City or network identifier cannot be empty.")
        return cleaned
