from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from models.audio_file import AudioFile
from models.calendar_context import CalendarMeetingContext
from models.chat import Message
from models.conversation_enums import (
    ConversationSource,
    ConversationStatus,
    ConversationVisibility,
    ExternalIntegrationConversationSource,
    PostProcessingModel,
    PostProcessingStatus,
)
from models.conversation_photo import ConversationPhoto
from models.geolocation import Geolocation
from models.other import Person
from models.structured import Structured
from models.transcript_segment import TranscriptSegment

# Only locally-defined symbols are exported. Use canonical modules for moved types:
#   models.conversation_enums, models.structured, models.audio_file, etc.
__all__ = [
    'AppResult',
    'BulkAssignSegmentsRequest',
    'Conversation',
    'ConversationPostProcessing',
    'CreateConversation',
    'CreateConversationResponse',
    'CreateMemoryResponse',
    'DeleteActionItemRequest',
    'ExternalIntegrationCreateConversation',
    'MergeConversationsRequest',
    'MergeConversationsResponse',
    'PluginResult',
    'SearchRequest',
    'SetConversationActionItemsStateRequest',
    'SetConversationEventsStateRequest',
    'TestPromptRequest',
    'UpdateActionItemDescriptionRequest',
    'UpdateConversation',
    'UpdateSegmentTextRequest',
    'UpdateSummaryRequest',
]


class UpdateConversation(BaseModel):
    title: Optional[str] = None
    overview: Optional[str] = None


# TODO: remove this class when the app is updated to use apps_results
class PluginResult(BaseModel):
    plugin_id: Optional[str]
    content: str


class AppResult(BaseModel):
    app_id: Optional[str]
    content: str


class ConversationPostProcessing(BaseModel):
    status: PostProcessingStatus
    model: PostProcessingModel
    fail_reason: Optional[str] = None


class Conversation(BaseModel):
    id: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    source: Optional[ConversationSource] = ConversationSource.omi
    language: Optional[str] = None  # applies only to Friend # TODO: once released migrate db to default 'en'

    structured: Structured
    transcript_segments: List[TranscriptSegment] = []
    transcript_segments_compressed: Optional[bool] = False
    geolocation: Optional[Geolocation] = None
    photos: List[ConversationPhoto] = []
    audio_files: List[AudioFile] = []
    private_cloud_sync_enabled: bool = False

    apps_results: List[AppResult] = []
    suggested_summarization_apps: List[str] = []

    # TODO: plugins_results for backward compatibility with the old memories routes and app
    plugins_results: List[PluginResult] = []

    external_data: Optional[Dict] = None
    app_id: Optional[str] = None

    discarded: bool = False
    visibility: ConversationVisibility = ConversationVisibility.private
    starred: bool = False

    # TODO: processing_memory_id for backward compatibility with the old memories routes and app
    processing_memory_id: Optional[str] = None

    processing_conversation_id: Optional[str] = None

    status: Optional[ConversationStatus] = ConversationStatus.completed
    is_locked: bool = False
    data_protection_level: Optional[str] = None
    folder_id: Optional[str] = Field(default=None, description="ID of the folder this conversation belongs to")
    call_id: Optional[str] = Field(default=None, description="Twilio call SID for phone call conversations")

    def __init__(self, **data):
        super().__init__(**data)
        # Update plugins_results based on apps_results
        self.plugins_results = [PluginResult(plugin_id=app.app_id, content=app.content) for app in self.apps_results]
        self.processing_memory_id = self.processing_conversation_id

    def get_transcript(self, include_timestamps: bool, people: List[Person] = None, user_name: str = None) -> str:
        # Warn: missing transcript for workflow source, external integration source
        return TranscriptSegment.segments_as_string(
            self.transcript_segments, include_timestamps=include_timestamps, user_name=user_name, people=people
        )

    def get_photos_descriptions(self, include_timestamps: bool = False) -> str:
        return ConversationPhoto.photos_as_string(self.photos, include_timestamps=include_timestamps)

    def get_person_ids(self) -> List[str]:
        if not self.transcript_segments:
            return []
        return list(set(segment.person_id for segment in self.transcript_segments if segment.person_id))

    def as_dict_cleaned_dates(self):
        def convert_datetime_to_iso(obj):
            """Recursively convert datetime objects to ISO format strings"""
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {key: convert_datetime_to_iso(value) for key, value in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetime_to_iso(item) for item in obj]
            else:
                return obj

        conversation_dict = self.dict()
        # Convert all datetime objects recursively
        conversation_dict = convert_datetime_to_iso(conversation_dict)
        return conversation_dict


class CreateConversation(BaseModel):
    started_at: datetime
    finished_at: datetime
    transcript_segments: List[TranscriptSegment]
    geolocation: Optional[Geolocation] = None

    photos: List[ConversationPhoto] = []

    source: ConversationSource = ConversationSource.omi
    language: Optional[str] = None

    processing_conversation_id: Optional[str] = None
    calendar_meeting_context: Optional[CalendarMeetingContext] = None
    is_locked: bool = False

    def get_transcript(self, include_timestamps: bool, people: List[Person] = None, user_name: str = None) -> str:
        return TranscriptSegment.segments_as_string(
            self.transcript_segments, include_timestamps=include_timestamps, user_name=user_name, people=people
        )

    def get_person_ids(self) -> List[str]:
        if not self.transcript_segments:
            return []
        return list(set(segment.person_id for segment in self.transcript_segments if segment.person_id))


class ExternalIntegrationCreateConversation(BaseModel):
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    text: str
    text_source: ExternalIntegrationConversationSource = ExternalIntegrationConversationSource.audio
    text_source_spec: Optional[str] = None
    geolocation: Optional[Geolocation] = None

    source: ConversationSource = ConversationSource.workflow
    language: Optional[str] = None

    app_id: Optional[str] = None

    def get_transcript(self, include_timestamps: bool) -> str:
        return self.text

    def get_person_ids(self) -> List[str]:
        return []


class CreateConversationResponse(BaseModel):
    conversation: Conversation
    messages: List[Message] = []


# MIGRATE: For backward compatibility with the old memories routes and app
class CreateMemoryResponse(BaseModel):
    memory: Conversation
    messages: List[Message] = []


class SetConversationEventsStateRequest(BaseModel):
    events_idx: List[int]
    values: List[bool]


class SetConversationActionItemsStateRequest(BaseModel):
    items_idx: List[int]
    values: List[bool]


class BulkAssignSegmentsRequest(BaseModel):
    segment_ids: List[str]
    assign_type: str
    value: Optional[str] = None


class UpdateSegmentTextRequest(BaseModel):
    segment_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=10000)


class UpdateSummaryRequest(BaseModel):
    app_id: Optional[str] = None
    content: str = Field(min_length=1, max_length=10000)


class DeleteActionItemRequest(BaseModel):
    description: str
    completed: bool


class UpdateActionItemDescriptionRequest(BaseModel):
    old_description: str
    description: str


class SearchRequest(BaseModel):
    query: str
    page: Optional[int] = 1
    per_page: Optional[int] = 10
    include_discarded: Optional[bool] = True
    start_date: Optional[str] = None  # ISO format datetime string
    end_date: Optional[str] = None  # ISO format datetime string


class TestPromptRequest(BaseModel):
    prompt: str


class MergeConversationsRequest(BaseModel):
    """Request model for merging multiple conversations."""

    conversation_ids: List[str] = Field(description="IDs of conversations to merge (minimum 2)", min_length=2)
    reprocess: bool = Field(default=True, description="Whether to regenerate summary from merged transcript")


class MergeConversationsResponse(BaseModel):
    """Response model for merge initiation."""

    status: str = Field(default="merging", description="Current merge status")
    message: str = Field(default="Merge started", description="Status message")
    warning: Optional[str] = Field(default=None, description="Warning message (e.g., large time gaps)")
    conversation_ids: List[str] = Field(description="All conversation IDs being merged")
