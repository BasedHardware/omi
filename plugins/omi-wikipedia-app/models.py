"""Typed request and response models for the Omi Wikipedia integration.

The Omi backend forwards optional manifest parameters verbatim — including
JSON null for arguments the LLM omitted — so every model normalizes untyped
input in ``mode="before"`` validators before a handler sees it.
"""

from typing import Any, Optional

from pydantic import BaseModel, field_validator


DEFAULT_LANGUAGE = "en"
DEFAULT_LIMIT = 5
MAX_LIMIT = 10


def normalize_language(value: Any) -> str:
    """Coerce an untyped language parameter into a Wikipedia language code."""
    if not isinstance(value, str):
        return DEFAULT_LANGUAGE
    language = value.strip().lower()
    if not language.replace("-", "").isalpha() or len(language) > 12:
        return DEFAULT_LANGUAGE
    return language


def normalize_limit(value: Any) -> int:
    """Coerce an untyped limit parameter into the inclusive [1, MAX_LIMIT] range."""
    if value is None or isinstance(value, bool):
        return DEFAULT_LIMIT
    if isinstance(value, str) and not value.strip():
        return DEFAULT_LIMIT
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(parsed, MAX_LIMIT))


def _strip(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


class _BaseToolRequest(BaseModel):
    language: str = DEFAULT_LANGUAGE

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: Any) -> str:
        return normalize_language(value)


class SearchArticlesRequest(_BaseToolRequest):
    """Payload for POST /tools/search_articles."""

    query: str
    limit: int = DEFAULT_LIMIT

    @field_validator("query", mode="before")
    @classmethod
    def _normalize_query(cls, value: Any) -> Any:
        return _strip(value)

    @field_validator("limit", mode="before")
    @classmethod
    def _normalize_limit(cls, value: Any) -> int:
        return normalize_limit(value)


class GetArticleSummaryRequest(_BaseToolRequest):
    """Payload for POST /tools/get_article_summary."""

    title: str

    @field_validator("title", mode="before")
    @classmethod
    def _normalize_title(cls, value: Any) -> Any:
        return _strip(value)


class GetRandomArticleRequest(_BaseToolRequest):
    """Payload for POST /tools/get_random_article."""


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None
