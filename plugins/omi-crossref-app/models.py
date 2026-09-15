"""Pydantic models for Omi Crossref Integration App."""

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


def _clean_text(v: Any) -> str:
    if not isinstance(v, str):
        raise ValueError("Value must be a string.")
    cleaned = v.strip()
    return cleaned


def _clamp_max_results(v: Any, default: int = 5) -> int:
    if v is None or v == "":
        return default
    try:
        parsed = int(v)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 10))


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class SearchWorksInput(BaseModel):
    """Request model for searching Crossref works."""

    query: str = Field(..., min_length=2, max_length=500, description="Search query string.")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of results (1-10).")

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, v: Any) -> str:
        cleaned = _clean_text(v)
        if len(cleaned) < 2:
            raise ValueError("Query must be at least 2 characters.")
        return cleaned

    @field_validator("max_results", mode="before")
    @classmethod
    def clamp_max_results(cls, v: Any) -> int:
        return _clamp_max_results(v)


class GetWorkInput(BaseModel):
    """Request model for retrieving a Crossref work by DOI."""

    doi: str = Field(..., min_length=3, max_length=250, description="DOI, e.g. 10.1038/nphys1170.")

    @field_validator("doi", mode="before")
    @classmethod
    def normalize_doi(cls, v: Any) -> str:
        cleaned = _clean_text(v)
        if not cleaned:
            raise ValueError("DOI is required.")
        if "/" not in cleaned:
            raise ValueError("Invalid DOI format. Example: 10.1038/nphys1170")
        if ".." in cleaned:
            raise ValueError("Invalid DOI value.")
        return cleaned


class AuthorWorksInput(BaseModel):
    """Request model for retrieving recent works by author."""

    author: str = Field(..., min_length=2, max_length=200, description="Author name.")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of results (1-10).")

    @field_validator("author", mode="before")
    @classmethod
    def normalize_author(cls, v: Any) -> str:
        cleaned = _clean_text(v)
        if len(cleaned) < 2:
            raise ValueError("Author must be at least 2 characters.")
        return cleaned

    @field_validator("max_results", mode="before")
    @classmethod
    def clamp_max_results(cls, v: Any) -> int:
        return _clamp_max_results(v)
