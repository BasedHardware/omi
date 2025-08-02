from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class UsageStats(BaseModel):
    """Represents a set of usage metrics for a period."""

    transcription_seconds: int = 0
    words_transcribed: int = 0
    insights_gained: int = 0
    memories_created: int = 0


class UsagePeriod(str, Enum):
    TODAY = "today"
    MONTHLY = "monthly"
    YEARLY = "yearly"
    ALL_TIME = "all_time"


class UsageHistoryPoint(UsageStats):
    date: str


class UserUsageResponse(BaseModel):
    """The response model for the user usage API endpoint."""

    today: Optional[UsageStats] = None
    monthly: Optional[UsageStats] = None
    yearly: Optional[UsageStats] = None
    all_time: Optional[UsageStats] = None
    history: Optional[List[UsageHistoryPoint]] = None


class HourlyUsage(UsageStats):
    """Represents the hourly usage data stored in the database."""

    uid: str
    year: int
    month: int
    day: int
    hour: int
    last_updated: datetime = Field(default_factory=datetime.utcnow)
