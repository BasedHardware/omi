"""Pydantic request and response models for Omi Stack Overflow Integration App."""

from typing import Any, Optional
import re
from pydantic import BaseModel, Field, field_validator


MAX_LIMIT = 10
DEFAULT_SITE = "stackoverflow"


def _safe_limit(limit: Any, default: int = 5) -> int:
    if limit is None or limit == "":
        return default
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(limit, MAX_LIMIT))


def _safe_site(site: Optional[str]) -> str:
    value = (site or DEFAULT_SITE).strip().lower()
    if not re.fullmatch(r"[a-z0-9.-]{2,40}", value):
        return DEFAULT_SITE
    return value


def _safe_tags(tags: Any) -> Optional[str]:
    if not tags:
        return None
    if isinstance(tags, list):
        values = tags
    else:
        values = re.split(r"[,;]", str(tags))

    cleaned = []
    for tag in values:
        tag = str(tag).strip().lower()
        if re.fullmatch(r"[a-z0-9.+#-]{1,35}", tag):
            cleaned.append(tag)

    return ";".join(cleaned[:5]) if cleaned else None


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if value is None or value == "":
        return None
    if str(value).strip().lower() in {"1", "true", "yes", "y"}:
        return True
    if str(value).strip().lower() in {"0", "false", "no", "n"}:
        return False
    return None


class ChatToolResponse(BaseModel):
    """Response model for Omi chat tool endpoints."""

    result: Optional[str] = None
    error: Optional[str] = None


class SearchQuestionsRequest(BaseModel):
    """Request model for searching Stack Overflow / Stack Exchange questions."""

    query: str = Field(..., description="Free-form search query.")
    tags: Optional[str] = Field(default=None, description="Optional comma- or semicolon-separated tags.")
    site: Optional[str] = Field(default=DEFAULT_SITE, description="Stack Exchange site slug.")
    accepted: Optional[bool] = Field(default=None, description="Optional filter for questions with accepted answers.")
    limit: Optional[int] = Field(default=5, description="Maximum questions to return (1-10).")

    @field_validator("query", mode="before")
    @classmethod
    def validate_query(cls, v: Any) -> str:
        if v is None:
            raise ValueError("Missing required field: query")
        s = str(v).strip()
        if not s:
            raise ValueError("Missing required field: query")
        return s

    @field_validator("site", mode="before")
    @classmethod
    def validate_site(cls, v: Any) -> str:
        return _safe_site(str(v) if v is not None else None)

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: Any) -> Optional[str]:
        return _safe_tags(v)

    @field_validator("accepted", mode="before")
    @classmethod
    def validate_accepted(cls, v: Any) -> Optional[bool]:
        return _coerce_bool(v)

    @field_validator("limit", mode="before")
    @classmethod
    def validate_limit(cls, v: Any) -> int:
        return _safe_limit(v, default=5)


class GetQuestionRequest(BaseModel):
    """Request model for retrieving a Stack Overflow / Stack Exchange question by ID."""

    question_id: int = Field(..., description="Stack Overflow question ID.")
    site: Optional[str] = Field(default=DEFAULT_SITE, description="Stack Exchange site slug.")

    @field_validator("question_id", mode="before")
    @classmethod
    def validate_question_id(cls, v: Any) -> int:
        if v is None or v == "":
            raise ValueError("Missing required field: question_id")
        try:
            return int(v)
        except (TypeError, ValueError):
            raise ValueError("question_id must be an integer")

    @field_validator("site", mode="before")
    @classmethod
    def validate_site(cls, v: Any) -> str:
        return _safe_site(str(v) if v is not None else None)


class GetTopAnswersRequest(BaseModel):
    """Request model for retrieving top answers for a question."""

    question_id: int = Field(..., description="Stack Overflow question ID.")
    site: Optional[str] = Field(default=DEFAULT_SITE, description="Stack Exchange site slug.")
    limit: Optional[int] = Field(default=3, description="Maximum answers to return (1-10).")

    @field_validator("question_id", mode="before")
    @classmethod
    def validate_question_id(cls, v: Any) -> int:
        if v is None or v == "":
            raise ValueError("Missing required field: question_id")
        try:
            return int(v)
        except (TypeError, ValueError):
            raise ValueError("question_id must be an integer")

    @field_validator("site", mode="before")
    @classmethod
    def validate_site(cls, v: Any) -> str:
        return _safe_site(str(v) if v is not None else None)

    @field_validator("limit", mode="before")
    @classmethod
    def validate_limit(cls, v: Any) -> int:
        return _safe_limit(v, default=3)
