from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional, Protocol

from pydantic import BaseModel, Field


class _CategorySummarySource(Protocol):
    value: str


class _StructuredSummarySource(Protocol):
    title: str
    overview: str
    category: _CategorySummarySource


class _ConversationSummarySource(Protocol):
    id: str
    structured: _StructuredSummarySource
    created_at: Optional[datetime]

    def get_transcript(self, include_timestamps: bool = False) -> str: ...

    def get_person_ids(self) -> List[str]: ...


class ConversationSummary(BaseModel):
    """Lightweight read-only view for consumers that don't need the full Conversation.

    Use this instead of Conversation when you only need title/overview/transcript
    (e.g., LLM utils, vector_db, notifications).
    """

    id: str
    title: str = ''
    overview: str = ''
    category: str = 'other'
    transcript_text: str = ''
    created_at: Optional[datetime] = None
    person_ids: List[str] = Field(default_factory=list)

    @classmethod
    def from_conversation(cls, c: _ConversationSummarySource, **kwargs: Any) -> ConversationSummary:
        return cls(
            id=c.id,
            title=c.structured.title,
            overview=c.structured.overview,
            category=c.structured.category.value,
            transcript_text=c.get_transcript(include_timestamps=False),
            created_at=c.created_at,
            person_ids=c.get_person_ids(),
        )
