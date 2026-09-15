"""Pydantic models for Omi Wikipedia Integration App."""

from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


DEFAULT_LANGUAGE = "en"
MAX_LANGUAGE_LENGTH = 12


def normalize_language(v: Any) -> str:
    """Normalize language code and provide fallback.

    Accepts ISO language codes (e.g., 'en', 'es', 'zh-cn').
    Falls back to 'en' if invalid, empty, or None.
    """
    if v is None or v == "":
        return DEFAULT_LANGUAGE
    if not isinstance(v, str):
        raise ValueError("language must be a string.")
    cleaned = v.strip().lower()
    if not cleaned.replace("-", "").isalpha() or len(cleaned) > MAX_LANGUAGE_LENGTH:
        return DEFAULT_LANGUAGE
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


class SearchArticlesRequest(BaseModel):
    """Request model for searching Wikipedia articles."""

    query: str = Field(..., min_length=1, max_length=200, description="Search query string.")
    language: Optional[str] = Field(default=DEFAULT_LANGUAGE, max_length=MAX_LANGUAGE_LENGTH, description="Wikipedia language code.")
    limit: int = Field(default=5, ge=1, le=10, description="Maximum number of results (1-10).")

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("query must be a string.")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("query cannot be empty.")
        return cleaned

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: Any) -> str:
        return normalize_language(v)


class GetArticleSummaryRequest(BaseModel):
    """Request model for fetching article summary."""

    title: str = Field(..., min_length=1, max_length=250, description="Article title.")
    language: Optional[str] = Field(default=DEFAULT_LANGUAGE, max_length=MAX_LANGUAGE_LENGTH, description="Wikipedia language code.")

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, v: Any) -> str:
        if not isinstance(v, str):
            raise ValueError("title must be a string.")
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("title cannot be empty.")
        return cleaned

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: Any) -> str:
        return normalize_language(v)


class GetRandomArticleRequest(BaseModel):
    """Request model for random article discovery."""

    language: Optional[str] = Field(default=DEFAULT_LANGUAGE, max_length=MAX_LANGUAGE_LENGTH, description="Wikipedia language code.")

    @field_validator("language", mode="before")
    @classmethod
    def validate_language(cls, v: Any) -> str:
        return normalize_language(v)
