from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DailySummaryHighlight(BaseModel):
    topic: str
    emoji: str = ""
    summary: str
    conversation_numbers: list[int] = Field(default_factory=list)


class DailySummaryQuestion(BaseModel):
    question: str
    conversation_number: int | None = None


class DailySummaryDecision(BaseModel):
    decision: str
    conversation_number: int | None = None


class DailySummaryKnowledgeNugget(BaseModel):
    insight: str
    conversation_number: int | None = None


class DailySummaryPayload(BaseModel):
    headline: str = "Your Day in Review"
    overview: str = ""
    day_emoji: str = "📅"
    highlights: list[DailySummaryHighlight] = Field(default_factory=list)
    unresolved_questions: list[DailySummaryQuestion] = Field(default_factory=list)
    decisions_made: list[DailySummaryDecision] = Field(default_factory=list)
    knowledge_nuggets: list[DailySummaryKnowledgeNugget] = Field(default_factory=list)


class LearnedMemoryRef(BaseModel):
    """One memory the day actually produced, addressed by its canonical id.

    This is the identity `knowledge_nuggets` never had: a client can render a
    native review card and vote or correct through the existing memory
    endpoints. Review state (`user_review`, `edited`) is deliberately absent —
    clients read it live from the memory so a vote on one device shows on the
    other.
    """

    memory_id: str
    content: str
    category: str = ""
    captured_at: Optional[datetime] = None
