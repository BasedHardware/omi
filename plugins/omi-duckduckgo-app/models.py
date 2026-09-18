"""
Pydantic request and response models for the DuckDuckGo Omi integration app.
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class InstantAnswerRequest(BaseModel):
    """Request schema for /tools/instant_answer."""

    query: str = Field(
        ...,
        description="Search query or topic to look up (e.g., 'quantum computing', 'capital of France', 'caffeine half life').",
    )
    include_sources: Optional[bool] = Field(
        default=True,
        description="Whether to include source citation and URL in the result.",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Query string cannot be empty or whitespace only.")
        if len(cleaned) > 500:
            raise ValueError("Query string cannot exceed 500 characters.")
        return cleaned


class SearchTopicsRequest(BaseModel):
    """Request schema for /tools/search_topics."""

    query: str = Field(
        ...,
        description="Search term to retrieve related topics and disambiguations.",
    )
    limit: Optional[int] = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of related topics to return (1 to 10).",
    )

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Query string cannot be empty or whitespace only.")
        if len(cleaned) > 500:
            raise ValueError("Query string cannot exceed 500 characters.")
        return cleaned


class DefineTermRequest(BaseModel):
    """Request schema for /tools/define_term."""

    term: str = Field(
        ...,
        description="Word or term to define (e.g. 'serendipity', 'ephemeral', 'photosynthesis').",
    )

    @field_validator("term")
    @classmethod
    def validate_term(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Term string cannot be empty or whitespace only.")
        if len(cleaned) > 200:
            raise ValueError("Term string cannot exceed 200 characters.")
        return cleaned
