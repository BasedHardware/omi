"""Wire models for L5 from-segments ingestion (re-exported by developer.py)."""

from datetime import datetime
from typing import Any, List, Literal, Optional
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator
from models.calendar_context import DevCalendarMeetingContext
from models.conversation_enums import ConversationSource
from models.geolocation import GeolocationInput
from routers import developer_segments


class DevTranscriptSegment(BaseModel):
    stt_provider: Optional[str] = Field(default=None, max_length=120)
    model_config = ConfigDict(title='CreateConversationTranscriptSegment')

    text: str = Field(description="The text spoken in this segment")
    speaker: Optional[str] = Field(
        default='SPEAKER_00', description="Speaker identifier (e.g., 'SPEAKER_00', 'SPEAKER_01')"
    )
    speaker_id: Optional[int] = Field(default=None, description="Numeric speaker ID")
    is_user: bool = Field(default=False, description="Whether this segment is from the user")
    person_id: Optional[str] = Field(default=None, description="ID of person speaking (if known)")
    start: float = Field(description="Start time in seconds (e.g., 0.0, 1.5, 60.2)")
    end: float = Field(description="End time in seconds (e.g., 1.5, 3.0, 65.8)")


class CaptureEvidenceLineageUnit(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)


class CaptureEvidenceLineage(BaseModel):
    version: Literal[1] = 1
    capability: Literal['stable_artifact']
    capture_root: str = Field(min_length=1, max_length=200)
    clock_domain: Literal['desktop_session_ms']
    lineage: Literal['complete', 'incomplete']
    units: List[CaptureEvidenceLineageUnit] = Field(max_length=64)


class CreateConversationFromTranscriptRequest(developer_segments.ContinuationFields):
    model_config = ConfigDict(title='CreateConversationFromTranscriptRequest')

    transcript_segments: List[DevTranscriptSegment] = Field(
        description="List of transcript segments with speaker and timing info", min_length=1, max_length=500
    )
    client_processing: Optional[Any] = Field(
        default=None,
        description=(
            "Untrusted client-authored display projection. Accepted as a raw payload "
            "and validated in the handler: a malformed projection is dropped and the "
            "conversation still lands. Display only — never an input to intelligence."
        ),
    )
    capture_evidence: Optional[CaptureEvidenceLineage] = None
    client_session_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices('client_session_id', 'client_conversation_id', 'session_id', 'client_id'),
        min_length=1,
        max_length=200,
        description="Stable client-generated session ID. When provided, retries return the same conversation ID.",
    )
    source: Optional[ConversationSource] = Field(
        default=ConversationSource.phone,
        description="Source of the conversation (e.g., omi, friend, openglass, phone, external_integration)",
    )
    started_at: Optional[datetime] = Field(default=None, description="When conversation started (defaults to now)")
    finished_at: Optional[datetime] = Field(
        default=None, description="When conversation finished (calculated from segments duration if not provided)"
    )
    language: Optional[str] = Field(default='en', description="Language code (ISO 639-1, e.g., 'en', 'es', 'fr')")
    geolocation: Optional[GeolocationInput] = Field(default=None, description="Geolocation where conversation occurred")
    client_device_id: Optional[str] = Field(default=None, description="Capture device id ({platform}_{hash})")
    client_platform: Optional[str] = Field(default=None, description="Client platform (ios/android/macos)")
    conversation_role: Literal['ambient', 'meeting'] = 'ambient'
    folder_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=200,
        description="ID of one of your folders (GET /v1/dev/user/folders). Files the conversation there instead of "
        "letting AI pick a folder.",
    )
    calendar_meeting_context: Optional[DevCalendarMeetingContext] = Field(
        default=None,
        description="Calendar meeting this conversation belongs to. Used as context for the summary and to identify "
        "participants, like the meetings Omi reads from a connected calendar.",
    )
    # Optional for backwards compatibility. When supplied, rotation fragments
    # are persisted but do not create a notes-ready receipt.
    # Plain string, not a Literal: this is opaque client-versioned metadata
    # (only 'max_duration_rotation' is ever compared downstream), and a closed
    # enum here previously fell out of sync with the desktop client's finalization
    # reasons, causing every upload carrying a newer reason to fail with a 422.
    conversation_finalization_reason: Optional[str] = None

    @field_validator('client_session_id')
    @classmethod
    def normalize_client_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError('client_session_id cannot be empty')
        return value

    @field_validator('started_at', 'finished_at')
    @classmethod
    def require_timezone_offset(cls, value: Optional[datetime]) -> Optional[datetime]:
        """Reject offset-naive timestamps with a 422 instead of a 500.

        A naive ``finished_at`` against the tz-aware ``started_at`` default (or
        the reverse) makes the handler's ``finished_at <= started_at`` check
        raise TypeError — an uncaught 500 on a malformed body. Both from-segments
        routes (developer and first-party) share this model, so both get the 422.
        """
        if value is not None and value.tzinfo is None:
            raise ValueError('must include a timezone offset (e.g. 2026-09-11T12:00:00Z)')
        return value
