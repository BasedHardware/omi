"""Pydantic models for Omi PubMed Integration App."""

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


def _clean_pmid(v: Any) -> str:
    if not isinstance(v, str):
        raise ValueError("pmid must be a string.")
    cleaned = v.strip()
    if not cleaned:
        raise ValueError("pmid is required.")
    if not cleaned.isdigit() or len(cleaned) > 12:
        raise ValueError("pmid must be a numeric PubMed ID (1-12 digits).")
    return cleaned


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class SearchPubmedRequest(BaseModel):
    """Request model for searching PubMed."""

    query: str = Field(..., min_length=1, max_length=500, description="PubMed search query.")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of results (1-10).")

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("query must be a string.")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("query cannot be empty.")
        return cleaned

    @field_validator("max_results", mode="before")
    @classmethod
    def clamp_max_results(cls, v: Any) -> int:
        if v is None or v == "":
            return 5
        try:
            val = int(v)
        except (TypeError, ValueError):
            return 5
        return max(1, min(val, 10))


class GetPubmedArticleRequest(BaseModel):
    """Request model for retrieving a PubMed article by PMID."""

    pmid: str = Field(..., description="Numeric PubMed ID.")

    @field_validator("pmid", mode="before")
    @classmethod
    def normalize_pmid(cls, v: Any) -> str:
        return _clean_pmid(v)


class GetRelatedPubmedRequest(BaseModel):
    """Request model for finding related PubMed articles."""

    pmid: str = Field(..., description="Numeric PubMed ID.")
    max_results: int = Field(default=5, ge=1, le=10, description="Maximum number of results (1-10).")

    @field_validator("pmid", mode="before")
    @classmethod
    def normalize_pmid(cls, v: Any) -> str:
        return _clean_pmid(v)

    @field_validator("max_results", mode="before")
    @classmethod
    def clamp_max_results(cls, v: Any) -> int:
        if v is None or v == "":
            return 5
        try:
            val = int(v)
        except (TypeError, ValueError):
            return 5
        return max(1, min(val, 10))
