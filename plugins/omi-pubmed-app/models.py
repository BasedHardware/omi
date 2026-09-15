"""Pydantic models for Omi PubMed App."""

from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator


def _normalized_pmid(value):
    """Strip and validate a PubMed ID (numeric, at most 12 digits)."""
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        return value
    cleaned = value.strip()
    if not cleaned.isdigit() or len(cleaned) > 12:
        raise ValueError("pmid must be a numeric PubMed ID")
    return cleaned


def _clamped_max_results(value, default: int = 5) -> int:
    """Coerce max_results into [1, 10], falling back to the default."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(parsed, 10))


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class SearchPubmedRequest(BaseModel):
    """Request model for PubMed keyword search."""

    query: str = Field(..., min_length=1, max_length=300, description="Search query.")
    max_results: int = Field(default=5, description="Number of results (clamped to 1-10).")

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, v) -> str:
        if not isinstance(v, str):
            return v
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("query is required")
        return cleaned

    @field_validator("max_results", mode="before")
    @classmethod
    def clamp_max_results(cls, v) -> int:
        return _clamped_max_results(v)


class GetPubmedArticleRequest(BaseModel):
    """Request model for fetching a single PubMed article."""

    pmid: str = Field(..., min_length=1, max_length=12, description="PubMed ID (numeric).")

    @field_validator("pmid", mode="before")
    @classmethod
    def normalize_pmid(cls, v) -> str:
        return _normalized_pmid(v)


class GetRelatedPubmedRequest(BaseModel):
    """Request model for finding related PubMed articles."""

    pmid: str = Field(..., min_length=1, max_length=12, description="PubMed ID (numeric).")
    max_results: int = Field(default=5, description="Number of results (clamped to 1-10).")

    @field_validator("pmid", mode="before")
    @classmethod
    def normalize_pmid(cls, v) -> str:
        return _normalized_pmid(v)

    @field_validator("max_results", mode="before")
    @classmethod
    def clamp_max_results(cls, v) -> int:
        return _clamped_max_results(v)
