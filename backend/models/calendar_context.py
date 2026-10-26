from datetime import datetime
from typing import Any, Callable, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class MeetingParticipant(BaseModel):
    """Represents a participant in a calendar meeting"""

    name: Optional[str] = Field(default=None, description="Participant's display name")
    email: Optional[str] = Field(default=None, description="Participant's email address")


class MeetingParticipantSources(BaseModel):
    """Source sets, not attendance: None means that source was not supplied."""

    expected_calendar: Optional[List[MeetingParticipant]] = None
    observed_screen_listing: Optional[List[MeetingParticipant]] = None


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

    participant_sources: Optional[MeetingParticipantSources] = Field(
        default=None, description="Participant provenance retained before calendar/screen context merging"
    )

    def to_storage_dict(self) -> dict[str, Any]:
        """The stored shape under ``external_data['calendar_meeting_context']``.

        Hand-built rather than a model dump: the conversation trust-boundary
        guard keys on dump call sites, and a storage write for meeting metadata
        must not silently sweep up fields added to the model later.
        """
        return {
            'calendar_event_id': self.calendar_event_id,
            'title': self.title,
            'participants': [
                {'name': participant.name, 'email': participant.email} for participant in self.participants
            ],
            'platform': self.platform,
            'meeting_link': self.meeting_link,
            'start_time': self.start_time.isoformat(),
            'duration_minutes': self.duration_minutes,
            'notes': self.notes,
            'calendar_source': self.calendar_source,
            'participant_sources': self._participant_sources_storage_dict(),
        }

    def _participant_sources_storage_dict(self) -> Optional[dict[str, Any]]:
        sources = self.participant_sources
        if sources is None:
            return None
        return {
            'expected_calendar': (
                [{'name': participant.name, 'email': participant.email} for participant in sources.expected_calendar]
                if sources.expected_calendar is not None
                else None
            ),
            'observed_screen_listing': (
                [
                    {'name': participant.name, 'email': participant.email}
                    for participant in sources.observed_screen_listing
                ]
                if sources.observed_screen_listing is not None
                else None
            ),
        }

    def participants_by_source(self) -> MeetingParticipantSources:
        if self.participant_sources is not None:
            return self.participant_sources
        if self.calendar_source == 'screen_activity':
            return MeetingParticipantSources(observed_screen_listing=list(self.participants))
        return MeetingParticipantSources(expected_calendar=list(self.participants))

    @classmethod
    def from_records(
        cls,
        records: List[dict[str, Any]],
        on_error: Optional[Callable[[dict[str, Any], Exception], None]] = None,
    ) -> List['CalendarMeetingContext']:
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


class DevCalendarMeetingContext(BaseModel):
    """Calendar meeting a developer-API caller attaches to a conversation it uploads"""

    model_config = ConfigDict(title='CreateConversationCalendarMeeting')

    calendar_event_id: str = Field(min_length=1, max_length=1024, description="Event ID in your calendar")
    title: str = Field(min_length=1, max_length=500, description="Meeting title")
    participants: List[MeetingParticipant] = Field(
        default_factory=list, max_length=100, description="Invited participants (name and/or email)"
    )
    platform: Optional[str] = Field(default=None, max_length=100, description="Zoom, Teams, Google Meet, in person…")
    meeting_link: Optional[str] = Field(default=None, max_length=2048, description="URL to join the meeting")
    start_time: datetime = Field(description="Meeting start time")
    duration_minutes: int = Field(ge=0, le=1440, description="Meeting duration in minutes")
    notes: Optional[str] = Field(default=None, max_length=10000, description="Meeting description from the calendar")

    def to_context(self) -> CalendarMeetingContext:
        # 'screen_activity' has its own merge rules; an API caller always supplies calendar data.
        return CalendarMeetingContext(
            calendar_event_id=self.calendar_event_id,
            title=self.title,
            participants=self.participants,
            platform=self.platform,
            meeting_link=self.meeting_link,
            start_time=self.start_time,
            duration_minutes=self.duration_minutes,
            notes=self.notes,
            calendar_source='developer_api',
        )
