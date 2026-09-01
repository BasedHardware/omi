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


class DailySummaryDayStatsPayload(BaseModel):
    total_conversations: int = 0
    total_duration_minutes: int = 0
    action_items_count: int = 0
    memories_created: int = 0
    action_items_created: int = 0
    watching_minutes: int = 0
    proactive_moments: int = 0


class DailySummaryPayload(BaseModel):
    headline: str = "Your Day in Review"
    overview: str = ""
    day_emoji: str = "📅"
    highlights: list[DailySummaryHighlight] = Field(default_factory=list)
    unresolved_questions: list[DailySummaryQuestion] = Field(default_factory=list)
    decisions_made: list[DailySummaryDecision] = Field(default_factory=list)
    knowledge_nuggets: list[DailySummaryKnowledgeNugget] = Field(default_factory=list)
    stats: DailySummaryDayStatsPayload | None = None
