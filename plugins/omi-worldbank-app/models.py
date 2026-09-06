"""Pydantic models for Omi World Bank Global Economic Intelligence Integration App."""

from typing import Any, Dict, Optional
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

# Common country aliases for model-level canonicalization and self-comparison detection
COMMON_COUNTRY_ALIASES: Dict[str, str] = {
    "us": "USA",
    "usa": "USA",
    "united states": "USA",
    "united states of america": "USA",
    "america": "USA",
    "uk": "GBR",
    "gbr": "GBR",
    "united kingdom": "GBR",
    "great britain": "GBR",
    "britain": "GBR",
    "england": "GBR",
    "germany": "DEU",
    "deu": "DEU",
    "de": "DEU",
    "deutschland": "DEU",
    "france": "FRA",
    "fra": "FRA",
    "fr": "FRA",
    "india": "IND",
    "ind": "IND",
    "in": "IND",
    "bharat": "IND",
    "china": "CHN",
    "chn": "CHN",
    "cn": "CHN",
    "prc": "CHN",
    "japan": "JPN",
    "jpn": "JPN",
    "jp": "JPN",
    "nippon": "JPN",
    "south korea": "KOR",
    "korea": "KOR",
    "kor": "KOR",
    "republic of korea": "KOR",
    "north korea": "PRK",
    "prk": "PRK",
    "russia": "RUS",
    "rus": "RUS",
    "russian federation": "RUS",
    "brazil": "BRA",
    "bra": "BRA",
    "br": "BRA",
    "brasil": "BRA",
    "canada": "CAN",
    "can": "CAN",
    "ca": "CAN",
    "australia": "AUS",
    "aus": "AUS",
    "mexico": "MEX",
    "mex": "MEX",
    "italy": "ITA",
    "ita": "ITA",
    "spain": "ESP",
    "esp": "ESP",
    "indonesia": "IDN",
    "idn": "IDN",
    "saudi arabia": "SAU",
    "sau": "SAU",
    "turkey": "TUR",
    "tur": "TUR",
    "turkiye": "TUR",
    "netherlands": "NLD",
    "nld": "NLD",
    "holland": "NLD",
    "switzerland": "CHE",
    "che": "CHE",
    "singapore": "SGP",
    "sgp": "SGP",
    "uae": "ARE",
    "are": "ARE",
    "united arab emirates": "ARE",
    "dubai": "ARE",
    "south africa": "ZAF",
    "zaf": "ZAF",
    "argentina": "ARG",
    "arg": "ARG",
    "sweden": "SWE",
    "swe": "SWE",
    "poland": "POL",
    "pol": "POL",
    "belgium": "BEL",
    "bel": "BEL",
    "norway": "NOR",
    "nor": "NOR",
    "ireland": "IRL",
    "irl": "IRL",
    "israel": "ISR",
    "isr": "ISR",
    "world": "WLD",
    "wld": "WLD",
    "global": "WLD",
}


def _clean_and_validate_country(v: Any) -> str:
    """Helper to strip whitespace and enforce minimum length after trimming."""
    if not isinstance(v, str):
        raise ValueError("Country identifier must be a string.")
    cleaned = v.strip()
    if len(cleaned) < 2:
        raise ValueError("Country identifier must be at least 2 characters long after trimming.")
    return cleaned


class CountryProfileRequest(BaseModel):
    """Request model for fetching a comprehensive country economic profile."""

    country: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Country name, common nickname, ISO-2, or ISO-3 code (e.g. 'United States', 'Germany', 'USA', 'DEU', 'IN', 'Japan').",
    )

    @field_validator("country", mode="before")
    @classmethod
    def clean_country(cls, v: Any) -> str:
        return _clean_and_validate_country(v)


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

    @field_validator("country", mode="before")
    @classmethod
    def clean_country(cls, v: Any) -> str:
        return _clean_and_validate_country(v)

    @field_validator("indicator", mode="before")
    @classmethod
    def normalize_indicator(cls, v: Any) -> str:
        if not isinstance(v, str):
            return "gdp"
        cleaned = v.strip().lower().replace(" ", "_").replace("-", "_")
        if not cleaned:
            return "gdp"
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

    @field_validator("country_a", "country_b", mode="before")
    @classmethod
    def clean_country(cls, v: Any) -> str:
        return _clean_and_validate_country(v)

    @model_validator(mode="after")
    def validate_different_countries(self):
        clean_a = self.country_a.strip().lower()
        clean_b = self.country_b.strip().lower()
        if clean_a == clean_b:
            raise ValueError("Cannot compare a country to itself. Please provide two distinct countries.")

        canon_a = COMMON_COUNTRY_ALIASES.get(clean_a, clean_a.upper())
        canon_b = COMMON_COUNTRY_ALIASES.get(clean_b, clean_b.upper())
        if canon_a == canon_b:
            raise ValueError(f"Cannot compare a country to itself ('{self.country_a}' and '{self.country_b}' refer to the same nation). Please provide two distinct countries.")

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

    @field_validator("query", "region", "income_level", mode="before")
    @classmethod
    def clean_optional_strings(cls, v: Any) -> Optional[str]:
        if v is None:
            return None
        if isinstance(v, str):
            cleaned = v.strip()
            return cleaned if cleaned else None
        return v
