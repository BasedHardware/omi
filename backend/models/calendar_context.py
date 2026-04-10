from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class MeetingParticipant(BaseModel):
    """Represents a participant in a calendar meeting"""

    name: Optional[str] = Field(default=None, description="Participant's display name")
    email: Optional[str] = Field(default=None, description="Participant's email address")


class CalendarMeetingContext(BaseModel):
    """Calendar meeting metadata to provide context for conversation processing"""

    calendar_event_id: str = Field(description="System calendar event ID")
    title: str = Field(description="Meeting title from calendar")
    participants: List[MeetingParticipant] = Field(default_factory=list, description="List of meeting participants")
    platform: Optional[str] = Field(default=None, description="Meeting platform (Zoom, Teams, Google Meet, etc.)")
    meeting_link: Optional[str] = Field(default=None, description="URL to join the meeting")
    start_time: datetime = Field(description="Meeting start time")
    duration_minutes: int = Field(description="Meeting duration in minutes")
    notes: Optional[str] = Field(default=None, description="Meeting notes/description from calendar")
    calendar_source: Optional[str] = Field(
        default='system_calendar', description="Calendar source (system_calendar, google, outlook, etc.)"
    )
