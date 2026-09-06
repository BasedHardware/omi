"""Pydantic models for Omi World Bank Global Economic Intelligence Integration App."""

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


# Canonical indicator map with aliases
INDICATOR_MAP = {
    "gdp": "NY.GDP.MKTP.CD",
    "gdp_usd": "NY.GDP.MKTP.CD",
    "gross_domestic_product": "NY.GDP.MKTP.CD",
    "gdp_per_capita": "NY.GDP.PCAP.CD",
    "gdp_pcap": "NY.GDP.PCAP.CD",
    "income_per_capita": "NY.GDP.PCAP.CD",
    "inflation": "FP.CPI.TOTL.ZG",
    "cpi": "FP.CPI.TOTL.ZG",
    "inflation_rate": "FP.CPI.TOTL.ZG",
    "population": "SP.POP.TOTL",
    "total_population": "SP.POP.TOTL",
    "life_expectancy": "SP.DYN.LE00.IN",
    "longevity": "SP.DYN.LE00.IN",
    "unemployment": "SL.UEM.TOTL.ZS",
    "unemployment_rate": "SL.UEM.TOTL.ZS",
    "co2_emissions": "EN.ATM.CO2E.PC",
    "co2": "EN.ATM.CO2E.PC",
    "carbon": "EN.ATM.CO2E.PC",
}


class CountryProfileRequest(BaseModel):
    """Request model for fetching a comprehensive country economic profile."""

    country: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Country name, common nickname, ISO-2, or ISO-3 code (e.g. 'United States', 'Germany', 'USA', 'DEU', 'IN', 'Japan').",
    )

    @field_validator("country")
    @classmethod
    def clean_country(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Country identifier cannot be empty or whitespace.")
        return cleaned


class EconomicIndicatorRequest(BaseModel):
    """Request model for querying a specific macroeconomic indicator."""

    country: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Country name or ISO code (e.g. 'United States', 'BRA', 'India').",
    )
    indicator: str = Field(
        default="gdp",
        description="Economic indicator: 'gdp', 'gdp_per_capita', 'inflation', 'population', 'life_expectancy', 'unemployment', or 'co2_emissions'.",
    )
    years: int = Field(
        default=1,
        ge=1,
        le=10,
        description="Number of recent annual data points to retrieve (1-10, default 1 for latest).",
    )

    @field_validator("country")
    @classmethod
    def clean_country(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Country identifier cannot be empty or whitespace.")
        return cleaned

    @field_validator("indicator")
    @classmethod
    def normalize_indicator(cls, v: str) -> str:
        cleaned = v.strip().lower().replace(" ", "_").replace("-", "_")
        if cleaned not in INDICATOR_MAP:
            valid_keys = ", ".join(sorted(list(set(["gdp", "gdp_per_capita", "inflation", "population", "life_expectancy", "unemployment", "co2_emissions"]))))
            raise ValueError(f"Unknown indicator '{v}'. Supported indicators are: {valid_keys}")
        return cleaned


class CompareEconomiesRequest(BaseModel):
    """Request model for side-by-side comparative analysis of two nations."""

    country_a: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="First country name or code (e.g. 'United States', 'USA').",
    )
    country_b: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Second country name or code (e.g. 'China', 'CHN').",
    )

    @field_validator("country_a", "country_b")
    @classmethod
    def clean_country(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Country identifiers cannot be empty or whitespace.")
        return cleaned

    @model_validator(mode="after")
    def validate_different_countries(self):
        if self.country_a.strip().lower() == self.country_b.strip().lower():
            raise ValueError("Cannot compare a country to itself. Please provide two distinct countries.")
        return self


class SearchCountriesRequest(BaseModel):
    """Request model for discovering countries by region or income classification."""

    query: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Search term matching country name, code, or capital city.",
    )
    region: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Geographic region (e.g. 'Europe & Central Asia', 'East Asia & Pacific', 'Latin America', 'South Asia', 'Sub-Saharan Africa', 'North America', 'Middle East').",
    )
    income_level: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Income bracket (e.g. 'High income', 'Upper middle income', 'Lower middle income', 'Low income').",
    )
    limit: int = Field(
        default=10,
        ge=1,
        le=30,
        description="Maximum number of countries to return (1-30).",
    )
