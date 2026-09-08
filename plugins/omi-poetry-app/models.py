"""Pydantic models for Omi Classical Poetry & Verse Integration App."""

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


class GetRandomPoemRequest(BaseModel):
    """Request model for retrieving a random or short classical poem."""

    model_config = ConfigDict(extra="ignore")

    author: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional author/poet filter (e.g. 'Emily Dickinson', 'Shakespeare', 'Robert Frost').",
    )
    max_lines: Optional[int] = Field(
        default=30,
        ge=1,
        le=200,
        description="Maximum lines in the returned poem (default 30, optimal for voice/wearables).",
    )

    @field_validator("author")
    @classmethod
    def sanitize_author(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = " ".join(v.strip().split())
        return cleaned or None


class SearchPoemsByAuthorRequest(BaseModel):
    """Request model for finding poems by a specific poet."""

    model_config = ConfigDict(extra="ignore")

    author: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Poet or author name (e.g. 'Edgar Allan Poe', 'Walt Whitman', 'John Keats', 'Emily Dickinson').",
    )
    max_results: Optional[int] = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of poems to return (1-10, default 3).",
    )

    @field_validator("author")
    @classmethod
    def sanitize_author(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Author name must not be empty.")
        return cleaned


class GetPoemByTitleRequest(BaseModel):
    """Request model for looking up a specific poem by its title."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(
        ...,
        min_length=1,
        max_length=150,
        description="Poem title (e.g. 'Ozymandias', 'The Raven', 'Sonnet 18', 'Annabel Lee').",
    )
    author: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional poet name to disambiguate or narrow search.",
    )

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, v: str) -> str:
        cleaned = " ".join(v.strip().split())
        if not cleaned:
            raise ValueError("Title must not be empty.")
        return cleaned

    @field_validator("author")
    @classmethod
    def sanitize_author(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = " ".join(v.strip().split())
        return cleaned or None


class ListPoetsRequest(BaseModel):
    """Request model for browsing classical poets in the library."""

    model_config = ConfigDict(extra="ignore")

    query: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional search filter to find matching poets (e.g. 'Shelley', 'Dickinson', 'Blake').",
    )

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        cleaned = " ".join(v.strip().split())
        return cleaned or None
