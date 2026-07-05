from datetime import datetime, timezone
from typing import Any, List, Mapping, Optional, Self
from pydantic import BaseModel, Field
import uuid


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ActionItemSummary(BaseModel):
    description: str
    priority: str = "medium"  # high, medium, low
    completed: bool = False
    source_conversation_id: Optional[str] = None


class TopicHighlight(BaseModel):
    topic: str
    emoji: str
    summary: str  # Keep it snappy - 1-2 sentences max
    conversation_ids: List[str] = Field(default_factory=list)


class UnresolvedQuestion(BaseModel):
    question: str
    conversation_id: Optional[str] = None


class DecisionMade(BaseModel):
    decision: str
    conversation_id: Optional[str] = None


class KnowledgeNugget(BaseModel):
    insight: str
    conversation_id: Optional[str] = None


class DayStats(BaseModel):
    total_conversations: int = 0  # Excluding discarded
    total_duration_minutes: int = 0  # Excluding discarded
    action_items_count: int = 0


class LocationPin(BaseModel):
    latitude: float
    longitude: float
    address: Optional[str] = None
    conversation_id: Optional[str] = None
    time: Optional[str] = None  # HH:MM format


class DailySummary(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    date: str  # YYYY-MM-DD format
    created_at: datetime = Field(default_factory=_utc_now)

    # Headline & Overview
    headline: str  # Catchy one-liner for the day
    overview: str  # 2-3 snappy lines, 1 paragraph
    day_emoji: str = "📅"

    # Stats
    stats: DayStats = Field(default_factory=DayStats)

    # Core content (all optional - skip if not enough quality data)
    highlights: List[TopicHighlight] = Field(default_factory=list)
    action_items: List[ActionItemSummary] = Field(default_factory=list)
    unresolved_questions: List[UnresolvedQuestion] = Field(default_factory=list)  # Max 3
    decisions_made: List[DecisionMade] = Field(default_factory=list)  # Max 3
    knowledge_nuggets: List[KnowledgeNugget] = Field(default_factory=list)  # Max 3

    # Locations
    locations: List[LocationPin] = Field(default_factory=list)

    def dict(self, **kwargs: Any) -> dict[str, Any]:
        data = self.model_dump(**kwargs)
        if isinstance(data.get('created_at'), datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Self:
        values = dict(data)
        created_at = values.get('created_at')
        if isinstance(created_at, str):
            values['created_at'] = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
        return cls(**values)
