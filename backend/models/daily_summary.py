from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from models.daily_summary_payload import LearnedMemoryRef


class DailySummaryActionItem(BaseModel):
    description: Optional[str] = None
    priority: Optional[str] = None
    source_conversation_id: Optional[str] = None
    completed: Optional[bool] = None


class DailySummaryTopicHighlight(BaseModel):
    topic: Optional[str] = None
    emoji: Optional[str] = None
    summary: Optional[str] = None
    conversation_ids: Optional[List[str]] = None


class DailySummaryUnresolvedQuestion(BaseModel):
    question: Optional[str] = None
    conversation_id: Optional[str] = None


class DailySummaryDecisionMade(BaseModel):
    decision: Optional[str] = None
    conversation_id: Optional[str] = None


class DailySummaryKnowledgeNugget(BaseModel):
    insight: Optional[str] = None
    conversation_id: Optional[str] = None


class DailySummaryDayStats(BaseModel):
    total_conversations: Optional[int] = None
    total_duration_minutes: Optional[int] = None
    action_items_count: Optional[int] = None
    memories_created: Optional[int] = None
    action_items_created: Optional[int] = None
    watching_minutes: Optional[int] = None
    proactive_moments: Optional[int] = None


class DailySummaryLocationPin(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    address: Optional[str] = None
    conversation_id: Optional[str] = None
    time: Optional[str] = None


class DailySummaryResponse(BaseModel):
    model_config = ConfigDict(extra='allow')

    id: Optional[str] = None
    date: Optional[str] = None
    created_at: Optional[datetime] = None
    headline: Optional[str] = None
    overview: Optional[str] = None
    day_emoji: Optional[str] = None
    stats: Optional[DailySummaryDayStats] = None
    highlights: Optional[List[DailySummaryTopicHighlight]] = None
    action_items: Optional[List[DailySummaryActionItem]] = None
    unresolved_questions: Optional[List[DailySummaryUnresolvedQuestion]] = None
    decisions_made: Optional[List[DailySummaryDecisionMade]] = None
    knowledge_nuggets: Optional[List[DailySummaryKnowledgeNugget]] = None
    # Memories the day actually produced, addressed by canonical memory id, so a
    # shell can render a native review card. Older summaries have no field;
    # clients prefer this over `knowledge_nuggets` when it is non-empty.
    memories_learned: List[LearnedMemoryRef] = Field(default_factory=list)
    locations: Optional[List[DailySummaryLocationPin]] = None


class DailySummariesResponse(BaseModel):
    summaries: List[DailySummaryResponse] = Field(default_factory=list)
