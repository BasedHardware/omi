"""Pydantic models for GitHub Public Omi integration."""
from typing import Optional

from pydantic import BaseModel, Field, model_validator


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""
    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of result or error must be provided.")
        return self


class SearchRepositoriesRequest(BaseModel):
    query: str = Field(..., min_length=2, max_length=200)
    language: Optional[str] = Field(default=None, min_length=1, max_length=50)
    sort: str = Field(default="best_match", pattern="^(best_match|stars|forks|updated)$")
    max_results: int = Field(default=5, ge=1, le=10)


class GetRepositoryRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=100)
    repo: str = Field(..., min_length=1, max_length=100)


class ListIssuesRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=100)
    repo: str = Field(..., min_length=1, max_length=100)
    state: str = Field(default="open", pattern="^(open|closed|all)$")
    labels: Optional[str] = Field(default=None, min_length=1, max_length=200)
    max_results: int = Field(default=5, ge=1, le=10)


class GetLatestReleaseRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=100)
    repo: str = Field(..., min_length=1, max_length=100)
