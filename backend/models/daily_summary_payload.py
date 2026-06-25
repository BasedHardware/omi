from pydantic import BaseModel, Field


class DailySummaryPayload(BaseModel):
    headline: str = "Your Day in Review"
    overview: str = ""
    day_emoji: str = "📅"
    highlights: list[dict] = Field(default_factory=list)
    unresolved_questions: list[dict] = Field(default_factory=list)
    decisions_made: list[dict] = Field(default_factory=list)
    knowledge_nuggets: list[dict] = Field(default_factory=list)
