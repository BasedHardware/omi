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

    @classmethod
    def from_records(cls, records, on_error=None) -> List['CalendarMeetingContext']:
        """Build a list of contexts from raw stored records, skipping any that fail
        validation so a single malformed meeting cannot hide all of a user's meetings.
        `on_error(record, exception)`, when provided, is called for each skipped record.
        """
        parsed: List['CalendarMeetingContext'] = []
        for record in records:
            try:
                parsed.append(cls(**record))
            except Exception as exc:  # noqa: BLE001 - one bad record must not break the whole list
                if on_error is not None:
                    on_error(record, exc)
        return parsed
