"""Scores — daily, weekly, and overall productivity scores computed from action items.

Response wire shapes for /v1/daily-score and /v1/scores. Source of truth for the
score response schema; the database layer (database.action_items) constructs dicts
matching these fields.
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

DATE_REGEX = re.compile(r'^\d{4}-\d{2}-\d{2}$')


class DailyScore(BaseModel):
    """Single-day productivity score (`get_daily_score`)."""

    date: str = Field(description='Calendar date the score covers, `YYYY-MM-DD` (UTC).')
    score: int = Field(ge=0, le=100, description='Completion percentage for the day, 0..100 (rounded).')
    completed_tasks: int = Field(ge=0, description='Number of completed, non-deleted tasks due that day.')
    total_tasks: int = Field(ge=0, description='Total non-deleted tasks due that day.')

    @field_validator('date')
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        value = value.strip()
        if not DATE_REGEX.match(value):
            raise ValueError('date must be in YYYY-MM-DD format')
        return value

    @model_validator(mode='after')
    def validate_task_counts(self):
        if self.completed_tasks > self.total_tasks:
            raise ValueError('completed_tasks cannot exceed total_tasks')
        return self


class ScorePeriod(BaseModel):
    """One scoring window (daily / weekly / overall) inside `get_scores`."""

    score: float = Field(ge=0.0, le=100.0, description='Completion percentage for the window, 0..100 (1 decimal).')
    completed_tasks: int = Field(ge=0, description='Completed, non-deleted tasks in the window.')
    total_tasks: int = Field(ge=0, description='Total non-deleted tasks in the window.')

    @model_validator(mode='after')
    def validate_task_counts(self):
        if self.completed_tasks > self.total_tasks:
            raise ValueError('completed_tasks cannot exceed total_tasks')
        return self


class Scores(BaseModel):
    """Daily, weekly, and overall scores plus the recommended default tab (`get_scores`)."""

    daily: ScorePeriod = Field(description='Score for tasks due on the given date.')
    weekly: ScorePeriod = Field(description='Score for tasks created in the 7 days ending on the given date.')
    overall: ScorePeriod = Field(description='Score across all non-deleted tasks.')
    default_tab: Literal['daily', 'weekly', 'overall'] = Field(
        description='Recommended default UI tab: "daily", "weekly", or "overall".'
    )
    date: str = Field(description='Calendar date the scores are anchored on, `YYYY-MM-DD` (UTC).')

    @field_validator('date')
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        value = value.strip()
        if not DATE_REGEX.match(value):
            raise ValueError('date must be in YYYY-MM-DD format')
        return value
