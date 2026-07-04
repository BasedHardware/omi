"""Focus sessions — focus/distraction tracking and statistics.

Response wire shapes for /v1/focus-sessions* and /v1/focus-stats. Source of
truth for the focus-session response schema; routers/database construct dicts
matching these fields.

Collection: users/{uid}/focus_sessions.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FocusSession(BaseModel):
    """A single focus/distraction session record."""

    id: str = Field(description='Unique session identifier.')
    status: str = Field(description='Session status, "focused" or "distracted".')
    app_or_site: str = Field(description='App or website the session refers to.')
    description: str = Field(description='Free-text description of the session.')
    message: Optional[str] = Field(default=None, description='Optional user message attached to the session.')
    created_at: datetime = Field(description='When the session was recorded (UTC).')
    duration_seconds: Optional[int] = Field(default=None, ge=0, description='Session duration in seconds, if known.')


class FocusDistraction(BaseModel):
    """One entry in the top-distractions breakdown of /v1/focus-stats."""

    app_or_site: str = Field(description='App or website that caused the distraction.')
    total_seconds: int = Field(ge=0, description='Total distracted seconds attributed to this app/site.')
    count: int = Field(ge=0, description='Number of distracted sessions for this app/site.')


class FocusStats(BaseModel):
    """Aggregated focus statistics returned by /v1/focus-stats."""

    date: str = Field(description='The date (YYYY-MM-DD) the stats cover.')
    focused_minutes: int = Field(ge=0, description='Total focused time, in whole minutes.')
    distracted_minutes: int = Field(ge=0, description='Total distracted time, in whole minutes.')
    session_count: int = Field(ge=0, description='Total number of sessions considered.')
    focused_count: int = Field(ge=0, description='Number of focused sessions.')
    distracted_count: int = Field(ge=0, description='Number of distracted sessions.')
    top_distractions: list[FocusDistraction] = Field(
        default_factory=list,
        description='Up to five most distracting apps/sites by total distracted seconds.',
    )
