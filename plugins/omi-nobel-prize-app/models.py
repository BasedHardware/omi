"""Pydantic models for Omi Nobel Prize Global Laureates & Human Discovery App."""

from datetime import datetime
from typing import Dict, List, Optional
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


# Official category codes and user-friendly aliases
NOBEL_CATEGORY_MAP: Dict[str, str] = {
    "phy": "phy",
    "physics": "phy",
    "che": "che",
    "chem": "che",
    "chemistry": "che",
    "med": "med",
    "medicine": "med",
    "physiology": "med",
    "physiology or medicine": "med",
    "lit": "lit",
    "literature": "lit",
    "pea": "pea",
    "peace": "pea",
    "eco": "eco",
    "economics": "eco",
    "economy": "eco",
    "economic sciences": "eco",
}

CATEGORY_DISPLAY_NAMES: Dict[str, str] = {
    "phy": "Physics",
    "che": "Chemistry",
    "med": "Physiology or Medicine",
    "lit": "Literature",
    "pea": "Peace",
    "eco": "Economic Sciences",
}


def resolve_nobel_category(val: Optional[str]) -> Optional[str]:
    """Resolve a raw category string or alias to canonical Nobel category code."""
    if val is None:
        return None
    cleaned = val.strip().lower()
    if not cleaned:
        return None
    if cleaned in NOBEL_CATEGORY_MAP:
        return NOBEL_CATEGORY_MAP[cleaned]
    valid_options = ", ".join(sorted(set(CATEGORY_DISPLAY_NAMES.values())))
    raise ValueError(
        f"Unknown Nobel category '{val}'. Supported categories are: {valid_options}."
    )


def get_current_year() -> int:
    """Return the current calendar year dynamically."""
    return datetime.now().year


class NobelPrizesRequest(BaseModel):
    """Request model for querying Nobel Prizes by year and/or category."""

    year: Optional[int] = Field(
        None,
        description="Year the Nobel Prize was awarded (1901 to current year). If omitted, retrieves recent prizes.",
    )
    category: Optional[str] = Field(
        None,
        description="Category: physics, chemistry, medicine, literature, peace, or economics.",
    )
    limit: int = Field(
        5,
        ge=1,
        le=25,
        description="Maximum number of prizes to return (1-25, default 5).",
    )

    @field_validator("year")
    @classmethod
    def validate_year(cls, v: Optional[int]) -> Optional[int]:
        if v is not None:
            max_year = get_current_year()
            if v < 1901 or v > max_year:
                raise ValueError(f"Year must be between 1901 and {max_year}.")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: Optional[str]) -> Optional[str]:
        return resolve_nobel_category(v)


class SearchLaureatesRequest(BaseModel):
    """Request model for searching Nobel laureates by name."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name or surname of the laureate to search (e.g. 'Einstein', 'Curie', 'Mandela').",
    )
    limit: int = Field(
        5,
        ge=1,
        le=10,
        description="Maximum number of matching laureates to return (1-10, default 5).",
    )

    @field_validator("query")
    @classmethod
    def clean_query(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Search query cannot be empty.")
        return cleaned


class CategoryPrizesRequest(BaseModel):
    """Request model for fetching recent prizes in a specific discipline."""

    category: str = Field(
        ...,
        min_length=1,
        description="Nobel Prize category: physics, chemistry, medicine, literature, peace, or economics.",
    )
    limit: int = Field(
        5,
        ge=1,
        le=15,
        description="Number of recent prizes to retrieve (1-15, default 5).",
    )

    @field_validator("category")
    @classmethod
    def validate_category(cls, v: str) -> str:
        resolved = resolve_nobel_category(v)
        if not resolved:
            raise ValueError("Category is required.")
        return resolved


class LaureateDetailsRequest(BaseModel):
    """Request model for retrieving full biographical details of a laureate."""

    identifier: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Numeric laureate ID (e.g. '1', '6') or laureate name (e.g. 'Albert Einstein').",
    )

    @field_validator("identifier")
    @classmethod
    def clean_identifier(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Identifier cannot be empty.")
        return cleaned
