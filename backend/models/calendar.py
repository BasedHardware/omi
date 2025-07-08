from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel


class CalendarEvent(BaseModel):
    id: str
    summary: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    calendar_id: str
    event_id: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class CalendarIntegration(BaseModel):
    uid: str
    access_token: str
    refresh_token: str
    token_expiry: datetime
    calendar_id: str
    calendar_name: str
    timezone: str
    preferences: Dict[str, Any] = {}
    created_at: datetime
    updated_at: Optional[datetime] = None


class CalendarEventCreate(BaseModel):
    summary: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    timezone: str = "UTC"
    attendees: Optional[list] = []
    location: Optional[str] = None


class CalendarConfig(BaseModel):
    auto_create_events: bool = True
    event_duration_minutes: int = 60
    default_timezone: str = "UTC"
    include_transcript: bool = True
    include_summary: bool = True
    calendar_id: Optional[str] = None