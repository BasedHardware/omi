"""Pydantic models for Semantic Scholar Omi integration."""
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""
    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if self.result is None and self.error is None:
            raise ValueError("Either result or error must be provided.")
        return self


class SearchPapersRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=200)
    max_results: int = Field(default=5, ge=1, le=10)
    min_year: Optional[int] = Field(default=None, ge=1800, le=2100)

    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("max_results", mode="before")
    @classmethod
    def coerce_max_results(cls, v: Any) -> int:
        if v is None or v == "":
            return 5
        try:
            val = int(v)
            return max(1, min(10, val))
        except (ValueError, TypeError):
            return 5

    @field_validator("min_year", mode="before")
    @classmethod
    def coerce_min_year(cls, v: Any) -> Optional[int]:
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None


class GetPaperRequest(BaseModel):
    paper_id_or_doi: str = Field(..., min_length=2, max_length=200)

    @field_validator("paper_id_or_doi", mode="before")
    @classmethod
    def strip_paper_id(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v


class GetAuthorPapersRequest(BaseModel):
    author_id: str = Field(..., min_length=1, max_length=100)
    max_results: int = Field(default=5, ge=1, le=10)

    @field_validator("author_id", mode="before")
    @classmethod
    def strip_author_id(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("max_results", mode="before")
    @classmethod
    def coerce_max_results(cls, v: Any) -> int:
        if v is None or v == "":
            return 5
        try:
            val = int(v)
            return max(1, min(10, val))
        except (ValueError, TypeError):
            return 5
