"""Pydantic models for the goal-tracking domain.

Consolidated from ``routers/goals.py`` so both ``goals.py`` and ``developer.py``
(router hierarchy: routers must not import from each other) share a single
source of truth for goal shapes.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class GoalType(str, Enum):
    """Types of goals supported."""

    boolean = "boolean"  # 0/1, true/false
    scale = "scale"  # e.g., 0-10
    numeric = "numeric"  # e.g., 0-1,000,000


class GoalCreate(BaseModel):
    """Model for creating a new goal."""

    title: str = Field(..., description="The goal title/description")
    goal_type: GoalType = Field(default=GoalType.scale, description="Type of goal metric")
    target_value: float = Field(..., description="Target value to achieve")
    current_value: float = Field(default=0, description="Current progress value")
    min_value: float = Field(default=0, description="Minimum value of the scale")
    max_value: float = Field(default=10, description="Maximum value of the scale")
    unit: Optional[str] = Field(default=None, description="Unit label (e.g., 'users', 'points')")


class GoalUpdate(BaseModel):
    """Model for updating a goal."""

    title: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    unit: Optional[str] = None


class GoalResponse(BaseModel):
    """Response model for a goal."""

    id: str
    title: str
    goal_type: str
    target_value: float
    current_value: float
    min_value: float
    max_value: float
    unit: Optional[str] = None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    advice: Optional[str] = None


class GoalSuggestionResponse(BaseModel):
    """Response model for AI-generated goal suggestion."""

    suggested_title: str
    suggested_type: str
    suggested_target: float
    suggested_min: float = 0
    suggested_max: float = 10
    reasoning: str


class AdviceResponse(BaseModel):
    """Response model for AI-generated goal advice."""

    advice: str


class GoalHistoryEntryResponse(BaseModel):
    """Response model for a goal progress history entry."""

    date: str
    value: float
    recorded_at: datetime


class GoalDeleteResponse(BaseModel):
    """Response model for deleting a goal."""

    success: bool
    deleted_id: str
