"""
Pydantic request and response models for the REST Countries & World Info Omi integration app.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class CountryOverviewRequest(BaseModel):
    """Request schema for /tools/country_overview."""

    country: str = Field(
        ...,
        description="Country common name, official name, or ISO 2/3 code (e.g. 'Japan', 'France', 'DE', 'BRA').",
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


class CapitalSearchRequest(BaseModel):
    """Request schema for /tools/search_by_capital."""

    capital: str = Field(
        ...,
        description="Capital city name to look up (e.g. 'Tokyo', 'Paris', 'Canberra', 'Nairobi').",
    )

    @field_validator("capital")
    @classmethod
    def validate_capital(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Capital city name cannot be empty or whitespace only.")
        if len(cleaned) > 100:
            raise ValueError("Capital city name cannot exceed 100 characters.")
        return cleaned


class CurrencySearchRequest(BaseModel):
    """Request schema for /tools/search_by_currency."""

    currency: str = Field(
        ...,
        description="Currency code or name (e.g. 'EUR', 'USD', 'JPY', 'Peso', 'Rupee').",
    )
    limit: Optional[int] = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum number of countries to return (1 to 25).",
    )

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Currency identifier cannot be empty or whitespace only.")
        if len(cleaned) > 50:
            raise ValueError("Currency identifier cannot exceed 50 characters.")
        return cleaned


class LanguageSearchRequest(BaseModel):
    """Request schema for /tools/search_by_language."""

    language: str = Field(
        ...,
        description="Language name or code (e.g. 'Spanish', 'French', 'Arabic', 'Portuguese').",
    )
    limit: Optional[int] = Field(
        default=10,
        ge=1,
        le=25,
        description="Maximum number of countries to return (1 to 25).",
    )

    @field_validator("language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Language identifier cannot be empty or whitespace only.")
        if len(cleaned) > 50:
            raise ValueError("Language identifier cannot exceed 50 characters.")
        return cleaned
