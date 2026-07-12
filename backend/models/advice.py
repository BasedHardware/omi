"""Advice — proactive coaching items.

Response wire shapes for /v1/advice*. Source of truth for the advice response
schema; routers/database construct dicts matching these fields.

Collection: users/{uid}/advice.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class AdviceFeedback(BaseModel):
    """The user's feedback on an advice item."""

    rating: int = Field(description='User rating: 1 (helpful) or -1 (not helpful).')
    reason: Optional[str] = Field(default=None, description='Optional free-text reason for the rating.')
    rated_at: datetime = Field(description='When the feedback was recorded (UTC).')


class Advice(BaseModel):
    """A single advice item shown to the user."""

    id: str = Field(description='Unique advice identifier.')
    content: str = Field(description='The advice text shown to the user.')
    category: str = Field(description='Advice category, e.g. "other", "focus".')
    reasoning: Optional[str] = Field(default=None, description='Why the advice was generated.')
    source_app: Optional[str] = Field(default=None, description='App that produced the advice, if any.')
    confidence: float = Field(default=0.5, ge=0.0, le=1.0, description='Model confidence, 0..1.')
    context_summary: Optional[str] = Field(default=None, description='Context the advice was based on.')
    current_activity: Optional[str] = Field(default=None, description='User activity when the advice was generated.')
    created_at: datetime = Field(description='Creation timestamp (UTC).')
    updated_at: datetime = Field(description='Last update timestamp (UTC).')
    is_read: bool = Field(default=False, description='Whether the user has read the advice.')
    is_dismissed: bool = Field(default=False, description='Whether the user dismissed the advice.')
    feedback: Optional[AdviceFeedback] = Field(
        default=None, description="The user's feedback on this advice, if they have rated it."
    )
