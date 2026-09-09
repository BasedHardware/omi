"""Pydantic models for Omi REST Countries & Global Geographic Intelligence App."""

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


class GetCountryInfoRequest(BaseModel):
    """Request model for looking up detailed information about a country."""

    model_config = ConfigDict(extra="ignore")

    country: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Country name, common nickname, or ISO code (e.g. 'France', 'Japan', 'USA', 'DEU', 'CHL').",
    )

    @field_validator("country")
    @classmethod
    def sanitize_country(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Country name or code must not be empty.")
        return cleaned


class SearchByCapitalRequest(BaseModel):
    """Request model for finding countries by their capital city."""

    model_config = ConfigDict(extra="ignore")

    capital: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Capital city name (e.g. 'Tokyo', 'Paris', 'Canberra', 'Ottawa', 'Berlin').",
    )

    @field_validator("capital")
    @classmethod
    def sanitize_capital(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Capital city name must not be empty.")
        return cleaned


class GetBorderCountriesRequest(BaseModel):
    """Request model for finding neighboring countries sharing borders."""

    model_config = ConfigDict(extra="ignore")

    country: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Country name or code to inspect land borders (e.g. 'Germany', 'Brazil', 'Switzerland').",
    )

    @field_validator("country")
    @classmethod
    def sanitize_country(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Country name or code must not be empty.")
        return cleaned


class SearchByCurrencyRequest(BaseModel):
    """Request model for finding countries that use a specific currency."""

    model_config = ConfigDict(extra="ignore")

    currency: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Currency code or name (e.g. 'EUR', 'USD', 'Yen', 'Peso', 'Pound', 'Franc').",
    )

    @field_validator("currency")
    @classmethod
    def sanitize_currency(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Currency code or name must not be empty.")
        return cleaned


class SearchByLanguageRequest(BaseModel):
    """Request model for finding countries where a specific language is spoken."""

    model_config = ConfigDict(extra="ignore")

    language: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Language name or code (e.g. 'Spanish', 'French', 'Arabic', 'Portuguese', 'German').",
    )

    @field_validator("language")
    @classmethod
    def sanitize_language(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Language name or code must not be empty.")
        return cleaned


class CompareCountriesRequest(BaseModel):
    """Request model for comparing demographic and geographic statistics between two countries."""

    model_config = ConfigDict(extra="ignore")

    country_a: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="First country name or code (e.g. 'Japan', 'France').",
    )
    country_b: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Second country name or code (e.g. 'Germany', 'United Kingdom').",
    )

    @field_validator("country_a", "country_b")
    @classmethod
    def sanitize_country(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Country name must not be empty.")
        return cleaned
