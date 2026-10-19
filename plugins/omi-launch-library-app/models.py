import re
from datetime import datetime, timezone
from typing import Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)


UUID_PATTERN = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def normalize_utc_datetime(value: str, *, end_of_day: bool = False) -> str:
    """Validate an ISO date/time and return an API-safe UTC timestamp."""
    if not isinstance(value, str):
        raise ValueError("date values must be strings")

    cleaned = value.strip()
    if not cleaned:
        raise ValueError("date values must not be empty")

    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("date values must use ISO 8601 format") from exc

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)

    if end_of_day and len(cleaned) == 10:
        parsed = parsed.replace(hour=23, minute=59, second=59)

    return parsed.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class ChatToolResponse(BaseModel):
    """Omi chat-tool response containing exactly one of result or error."""

    result: Optional[str] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one_outcome(self):
        if (self.result is None) == (self.error is None):
            raise ValueError("exactly one of result or error must be provided")
        return self


class UpcomingLaunchesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    days: int = Field(default=30, ge=1, le=365)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=120)
    rocket: Optional[str] = Field(default=None, min_length=1, max_length=160)
    limit: int = Field(default=5, ge=1, le=10)


class SearchLaunchesRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    query: Optional[str] = Field(default=None, min_length=1, max_length=160)
    provider: Optional[str] = Field(default=None, min_length=1, max_length=120)
    rocket: Optional[str] = Field(default=None, min_length=1, max_length=160)
    start_date: Optional[str] = Field(default=None, min_length=10, max_length=40)
    end_date: Optional[str] = Field(default=None, min_length=10, max_length=40)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def validate_dates(cls, value, info: ValidationInfo):
        if value is None:
            return None
        return normalize_utc_datetime(
            value,
            end_of_day=info.field_name == "end_date" and len(value.strip()) == 10,
        )

    @model_validator(mode="after")
    def require_search_filter(self):
        if not any(
            (
                self.query,
                self.provider,
                self.rocket,
                self.start_date,
                self.end_date,
            )
        ):
            raise ValueError(
                "provide at least one of query, provider, rocket, start_date, or end_date"
            )
        if self.start_date and self.end_date and self.start_date > self.end_date:
            raise ValueError("start_date must not be later than end_date")
        return self


class LaunchDetailsRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    launch_id: str = Field(..., min_length=36, max_length=300)

    @field_validator("launch_id", mode="before")
    @classmethod
    def normalize_launch_id(cls, value):
        if not isinstance(value, str):
            raise ValueError("launch_id must be a string")
        match = UUID_PATTERN.search(value)
        if not match:
            raise ValueError("launch_id must contain a Launch Library UUID")
        return match.group(0).lower()
