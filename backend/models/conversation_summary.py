from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


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
    def from_conversation(cls, c: 'Conversation', **kwargs) -> 'ConversationSummary':
        from models.conversation import Conversation

        return cls(
            id=c.id,
            title=c.structured.title,
            overview=c.structured.overview,
            category=c.structured.category.value,
            transcript_text=c.get_transcript(include_timestamps=False),
            created_at=c.created_at,
            person_ids=c.get_person_ids(),
        )
