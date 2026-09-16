"""
Pydantic models for Stack Overflow Integration App.
"""

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class SearchQuestionsRequest(BaseModel):
    query: str = Field(..., description="Search query terms")
    site: Optional[str] = Field(default="stackoverflow", description="Stack Exchange API site slug")
    tags: Optional[Any] = Field(default=None, description="Optional tags filter")
    accepted: Optional[Any] = Field(default=None, description="Optional filter for accepted answers")
    limit: Optional[Any] = Field(default=5, description="Maximum questions to return (defaults to 5, max 10)")

    @field_validator("site", mode="before")
    @classmethod
    def default_site_if_none(cls, v: Any) -> str:
        if v is None or v == "":
            return "stackoverflow"
        return str(v)

    @field_validator("limit", mode="before")
    @classmethod
    def default_limit_if_none(cls, v: Any) -> int:
        if v is None or v == "":
            return 5
        return v


class GetQuestionRequest(BaseModel):
    question_id: Any = Field(..., description="Stack Overflow question ID")
    site: Optional[str] = Field(default="stackoverflow", description="Stack Exchange API site slug")

    @field_validator("site", mode="before")
    @classmethod
    def default_site_if_none(cls, v: Any) -> str:
        if v is None or v == "":
            return "stackoverflow"
        return str(v)


class GetTopAnswersRequest(BaseModel):
    question_id: Any = Field(..., description="Stack Overflow question ID")
    site: Optional[str] = Field(default="stackoverflow", description="Stack Exchange API site slug")
    limit: Optional[Any] = Field(default=3, description="Maximum answers to return (defaults to 3, max 10)")

    @field_validator("site", mode="before")
    @classmethod
    def default_site_if_none(cls, v: Any) -> str:
        if v is None or v == "":
            return "stackoverflow"
        return str(v)

    @field_validator("limit", mode="before")
    @classmethod
    def default_limit_if_none(cls, v: Any) -> int:
        if v is None or v == "":
            return 3
        return v
