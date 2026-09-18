"""Pydantic models for Omi Stack Overflow Integration App.

Omi sends ``null`` for optional parameters (``{"site": null, "limit": null}``);
validators coerce that to the documented default instead of rejecting the
request. Validation failures surface as ``ChatToolResponse(error=...)`` with
HTTP 200 via the RequestValidationError handler in ``main.py`` — a raw 422
crashes the Omi chat agent.
"""

from typing import Any, Optional, Union

from pydantic import BaseModel, Field, field_validator, model_validator

DEFAULT_SITE = "stackoverflow"
MAX_LIMIT = 10


def _default_if_none(value: Any, default: Any) -> Any:
    """Omi's null-means-default contract for optional fields."""
    return default if value is None else value


class ChatToolResponse(BaseModel):
    """Standard response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def validate_result_or_error(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("Exactly one of 'result' or 'error' must be provided.")
        return self


class SearchQuestionsRequest(BaseModel):
    """Request model for searching Stack Exchange questions."""

    query: str = Field(
        ...,
        description="Free-form search query, such as an error message, API name, or programming problem.",
    )
    tags: Optional[Union[str, list]] = Field(
        default=None,
        description="Optional comma- or semicolon-separated tags, such as python, react, fastapi.",
    )
    site: Optional[str] = Field(
        default=DEFAULT_SITE,
        description="Stack Exchange API site slug. Defaults to stackoverflow.",
    )
    accepted: Optional[bool] = Field(
        default=None,
        description="Optional filter for questions with accepted answers.",
    )
    limit: Optional[int] = Field(
        default=5,
        description="Maximum questions to return. Defaults to 5, maximum 10.",
    )

    @field_validator("query")
    @classmethod
    def normalize_query(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("query must be a non-empty string.")
        return v.strip()

    @field_validator("site")
    @classmethod
    def null_site_means_default(cls, v: Optional[str]) -> str:
        v = _default_if_none(v, DEFAULT_SITE)
        return str(v).strip() or DEFAULT_SITE

    @field_validator("limit")
    @classmethod
    def null_limit_means_default(cls, v: Optional[int]) -> int:
        v = _default_if_none(v, 5)
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 5
        return max(1, min(v, MAX_LIMIT))


class GetQuestionRequest(BaseModel):
    """Request model for fetching a single question."""

    question_id: int = Field(
        ...,
        description="Stack Overflow question ID.",
    )
    site: Optional[str] = Field(
        default=DEFAULT_SITE,
        description="Stack Exchange API site slug. Defaults to stackoverflow.",
    )

    @field_validator("question_id")
    @classmethod
    def coerce_question_id(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise ValueError("question_id must be an integer.")
        if v <= 0:
            raise ValueError("question_id must be a positive integer.")
        return v

    @field_validator("site")
    @classmethod
    def null_site_means_default(cls, v: Optional[str]) -> str:
        v = _default_if_none(v, DEFAULT_SITE)
        return str(v).strip() or DEFAULT_SITE


class GetTopAnswersRequest(BaseModel):
    """Request model for fetching top answers to a question."""

    question_id: int = Field(
        ...,
        description="Stack Overflow question ID.",
    )
    site: Optional[str] = Field(
        default=DEFAULT_SITE,
        description="Stack Exchange API site slug. Defaults to stackoverflow.",
    )
    limit: Optional[int] = Field(
        default=3,
        description="Maximum answers to return. Defaults to 3, maximum 10.",
    )

    @field_validator("question_id")
    @classmethod
    def coerce_question_id(cls, v: Any) -> int:
        try:
            v = int(v)
        except (TypeError, ValueError):
            raise ValueError("question_id must be an integer.")
        if v <= 0:
            raise ValueError("question_id must be a positive integer.")
        return v

    @field_validator("site")
    @classmethod
    def null_site_means_default(cls, v: Optional[str]) -> str:
        v = _default_if_none(v, DEFAULT_SITE)
        return str(v).strip() or DEFAULT_SITE

    @field_validator("limit")
    @classmethod
    def null_limit_means_default(cls, v: Optional[int]) -> int:
        v = _default_if_none(v, 3)
        try:
            v = int(v)
        except (TypeError, ValueError):
            return 3
        return max(1, min(v, MAX_LIMIT))
