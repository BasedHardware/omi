"""Request/response models for the Crossref Omi chat tools.

Validators trim whitespace, clamp result bounds, and enforce the
exactly-one-of result/error chat-tool envelope (#13983).
"""

from typing import Any, Optional

from pydantic import BaseModel, field_validator, model_validator

MIN_RESULTS = 1
MAX_RESULTS = 10
DEFAULT_RESULTS = 5


def _stripped(value: Any) -> Any:
    return value.strip() if isinstance(value, str) else value


def _bounded_max_results(value: Any) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RESULTS
    return max(MIN_RESULTS, min(MAX_RESULTS, number))


class ChatToolResponse(BaseModel):
    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def _exactly_one_of_result_or_error(self) -> "ChatToolResponse":
        if (self.result is None) == (self.error is None):
            raise ValueError("exactly one of 'result' or 'error' must be provided")
        return self


class SearchWorksInput(BaseModel):
    query: str
    max_results: int = DEFAULT_RESULTS

    @field_validator("query", mode="before")
    @classmethod
    def _strip_query(cls, value: Any) -> Any:
        return _stripped(value)

    @field_validator("max_results", mode="before")
    @classmethod
    def _clamp_max_results(cls, value: Any) -> int:
        return _bounded_max_results(value)


class GetWorkInput(BaseModel):
    doi: str

    @field_validator("doi", mode="before")
    @classmethod
    def _strip_doi(cls, value: Any) -> Any:
        return _stripped(value)


class AuthorWorksInput(BaseModel):
    author: str
    max_results: int = DEFAULT_RESULTS

    @field_validator("author", mode="before")
    @classmethod
    def _strip_author(cls, value: Any) -> Any:
        return _stripped(value)

    @field_validator("max_results", mode="before")
    @classmethod
    def _clamp_max_results(cls, value: Any) -> int:
        return _bounded_max_results(value)
