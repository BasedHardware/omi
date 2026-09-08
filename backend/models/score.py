"""Scores — daily, weekly, and overall productivity scores computed from action items.

Response wire shapes for /v1/daily-score and /v1/scores. Source of truth for the
score response schema; the database layer (database.action_items) constructs dicts
matching these fields.
"""

from pydantic import BaseModel, Field


class DailyScore(BaseModel):
    """Single-day productivity score (`get_daily_score`)."""

    date: str = Field(description='Calendar date the score covers, `YYYY-MM-DD` (UTC).')
    score: int = Field(ge=0, le=100, description='Completion percentage for the day, 0..100 (rounded).')
    completed_tasks: int = Field(ge=0, description='Number of completed, non-deleted tasks due that day.')
    total_tasks: int = Field(ge=0, description='Total non-deleted tasks due that day.')


class ScorePeriod(BaseModel):
    """One scoring window (daily / weekly / overall) inside `get_scores`."""

    score: float = Field(ge=0.0, le=100.0, description='Completion percentage for the window, 0..100 (1 decimal).')
    completed_tasks: int = Field(ge=0, description='Completed, non-deleted tasks in the window.')
    total_tasks: int = Field(ge=0, description='Total non-deleted tasks in the window.')


class Scores(BaseModel):
    """Daily, weekly, and overall scores plus the recommended default tab (`get_scores`)."""

    daily: ScorePeriod = Field(description='Score for tasks due on the given date.')
    weekly: ScorePeriod = Field(description='Score for tasks created in the 7 days ending on the given date.')
    overall: ScorePeriod = Field(description='Score across all non-deleted tasks.')
    default_tab: str = Field(description='Recommended default UI tab: "daily", "weekly", or "overall".')
    date: str = Field(description='Calendar date the scores are anchored on, `YYYY-MM-DD` (UTC).')
