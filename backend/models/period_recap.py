"""Weekly and monthly recap responses (GET /v1/users/recaps/{period})."""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class PeriodRecapStats(BaseModel):
    total_conversations: int = 0
    total_duration_minutes: int = 0
    action_items_created: int = 0
    memories_created: int = 0


class PeriodRecapPrevious(BaseModel):
    start_date: str = Field(description='First local date compared (YYYY-MM-DD)')
    end_date: str = Field(
        description=(
            'Last local date compared (YYYY-MM-DD). The previous period\'s last day once the current period has '
            'ended, or reached its last day with that day\'s daily recap; before that, as many days in as the current '
            'period so far: through today once its daily recap exists, else through yesterday'
        )
    )
    total_conversations: int = 0
    total_duration_minutes: int = 0


class PeriodRecapBusiestDay(BaseModel):
    date: str
    summary_id: Optional[str] = None
    total_conversations: int = 0
    total_duration_minutes: int = 0


class PeriodRecapHighlight(BaseModel):
    date: str
    topic: Optional[str] = None
    emoji: Optional[str] = None
    summary: Optional[str] = None
    conversation_ids: List[str] = Field(default_factory=list)


class PeriodRecapDecision(BaseModel):
    date: str
    decision: str
    conversation_id: Optional[str] = None


class PeriodRecapQuestion(BaseModel):
    date: str
    question: str
    conversation_id: Optional[str] = None


class PeriodRecapActionItem(BaseModel):
    id: str
    date: str = Field(description='Local date the task was created (YYYY-MM-DD)')
    description: str
    source_conversation_id: Optional[str] = None
    due_at: Optional[str] = Field(default=None, description='When the task is due (ISO 8601), if it has a due date')


class PeriodRecapPerson(BaseModel):
    person_id: str
    name: str
    conversations: int = 0
    talk_minutes: int = 0


class PeriodRecapResponse(BaseModel):
    period: Literal['week', 'month']
    start_date: str = Field(description='First local date of the period (YYYY-MM-DD)')
    end_date: str = Field(description='Last local date of the period (YYYY-MM-DD)')
    days_recorded: int = Field(default=0, description='Days in the period that have a daily recap')
    stats: PeriodRecapStats = Field(default_factory=PeriodRecapStats)
    busiest_day: Optional[PeriodRecapBusiestDay] = None
    highlights: List[PeriodRecapHighlight] = Field(default_factory=list)
    decisions: List[PeriodRecapDecision] = Field(default_factory=list)
    open_questions: List[PeriodRecapQuestion] = Field(default_factory=list)
    open_action_items: List[PeriodRecapActionItem] = Field(
        default_factory=list, description='Tasks created in the period that are still open now'
    )
    top_people: List[PeriodRecapPerson] = Field(
        default_factory=list,
        description='People talked to most, ranked from up to 500 conversations in the period, newest first',
    )
    previous: Optional[PeriodRecapPrevious] = Field(
        default=None,
        description=(
            'Totals for the same stretch of the period just before, for trends; absent when unknown or before '
            'the current period has a day to compare (today counts once its daily recap exists)'
        ),
    )
