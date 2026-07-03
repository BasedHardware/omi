from pydantic import BaseModel, Field


class DailySummaryHighlight(BaseModel):
    topic: str
    emoji: str = ""
    summary: str
    conversation_numbers: list[int] = Field(default_factory=list[int])


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
    highlights: list[DailySummaryHighlight] = Field(default_factory=list[DailySummaryHighlight])
    unresolved_questions: list[DailySummaryQuestion] = Field(default_factory=list[DailySummaryQuestion])
    decisions_made: list[DailySummaryDecision] = Field(default_factory=list[DailySummaryDecision])
    knowledge_nuggets: list[DailySummaryKnowledgeNugget] = Field(default_factory=list[DailySummaryKnowledgeNugget])
