"""Pydantic models for Semantic Scholar Omi integration."""
from typing import Optional
from pydantic import BaseModel, Field
from pydantic import model_validator


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
    max_results: Optional[int] = Field(default=5, ge=1, le=10)
    min_year: Optional[int] = Field(default=None, ge=1800, le=2100)

    @model_validator(mode="after")
    def coerce_defaults(self):
        if getattr(self, "max_results", None) is None:
            self.max_results = 5
        else:
            try:
                self.max_results = min(max(1, int(self.max_results)), 10)
            except (ValueError, TypeError):
                self.max_results = 5
        return self


class GetPaperRequest(BaseModel):
    paper_id_or_doi: str = Field(..., min_length=2, max_length=500)


class GetAuthorPapersRequest(BaseModel):
    author_id: str = Field(..., min_length=1, max_length=500)
    max_results: Optional[int] = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def coerce_defaults(self):
        if getattr(self, "max_results", None) is None:
            self.max_results = 5
        else:
            try:
                self.max_results = min(max(1, int(self.max_results)), 10)
            except (ValueError, TypeError):
                self.max_results = 5
        return self
