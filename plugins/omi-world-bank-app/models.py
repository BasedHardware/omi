"""
Pydantic request and response models for the World Bank Economic Indicators Omi integration app.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class EconomicSnapshotRequest(BaseModel):
    """Request schema for /tools/economic_snapshot."""

    country: str = Field(
        ...,
        description="Country name or ISO 2/3 letter code (e.g. 'United States', 'US', 'IND', 'Japan', 'DEU').",
    )

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Country identifier cannot be empty or whitespace only.")
        if len(cleaned) > 100:
            raise ValueError("Country identifier cannot exceed 100 characters.")
        return cleaned


class IndicatorHistoryRequest(BaseModel):
    """Request schema for /tools/indicator_history."""

    country: str = Field(
        ...,
        description="Country name or ISO code (e.g. 'US', 'China', 'India', 'Germany').",
    )
    indicator: str = Field(
        ...,
        description="Economic indicator (e.g. 'gdp', 'inflation', 'population', 'life_expectancy', 'unemployment', 'co2').",
    )
    years: Optional[int] = Field(
        default=5,
        ge=1,
        le=15,
        description="Number of recent years of data to return (1 to 15).",
    )

    @field_validator("country")
    @classmethod
    def validate_country(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Country identifier cannot be empty or whitespace only.")
        if len(cleaned) > 100:
            raise ValueError("Country identifier cannot exceed 100 characters.")
        return cleaned

    @field_validator("indicator")
    @classmethod
    def validate_indicator(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Indicator cannot be empty.")
        return cleaned


class CompareIndicatorRequest(BaseModel):
    """Request schema for /tools/compare_indicator."""

    country_a: str = Field(
        ...,
        description="First country name or ISO code (e.g. 'United States', 'US').",
    )
    country_b: str = Field(
        ...,
        description="Second country name or ISO code (e.g. 'China', 'CN', 'India').",
    )
    indicator: str = Field(
        ...,
        description="Indicator to compare (e.g. 'gdp', 'inflation', 'population', 'life_expectancy', 'unemployment', 'co2').",
    )

    @field_validator("country_a", "country_b")
    @classmethod
    def validate_country(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Country identifier cannot be empty.")
        if len(cleaned) > 100:
            raise ValueError("Country identifier cannot exceed 100 characters.")
        return cleaned

    @field_validator("indicator")
    @classmethod
    def validate_indicator(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise ValueError("Indicator cannot be empty.")
        return cleaned
