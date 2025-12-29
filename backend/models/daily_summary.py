from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid


class ActionItemSummary(BaseModel):
    description: str
    priority: str = "medium"  # high, medium, low
    completed: bool = False
    source_conversation_id: Optional[str] = None


class TopicHighlight(BaseModel):
    topic: str
    emoji: str
    summary: str  # Keep it snappy - 1-2 sentences max
    conversation_ids: List[str] = []


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
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Headline & Overview
    headline: str  # Catchy one-liner for the day
    overview: str  # 2-3 snappy lines, 1 paragraph
    day_emoji: str = "📅"

    # Stats
    stats: DayStats = Field(default_factory=DayStats)

    # Core content (all optional - skip if not enough quality data)
    highlights: List[TopicHighlight] = []
    action_items: List[ActionItemSummary] = []
    unresolved_questions: List[UnresolvedQuestion] = []  # Max 3
    decisions_made: List[DecisionMade] = []  # Max 3
    knowledge_nuggets: List[KnowledgeNugget] = []  # Max 3

    # Locations
    locations: List[LocationPin] = []

    def dict(self, **kwargs):
        data = super().dict(**kwargs)
        if isinstance(data.get('created_at'), datetime):
            data['created_at'] = data['created_at'].isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'DailySummary':
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'].replace('Z', '+00:00'))
        return cls(**data)
