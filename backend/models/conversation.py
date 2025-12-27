from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from models.chat import Message
from models.other import Person
from models.transcript_segment import TranscriptSegment


class AudioFile(BaseModel):
    id: str = Field(description="Unique identifier for the audio file")
    uid: str = Field(description="User ID who owns this audio file")
    conversation_id: str = Field(description="ID of the conversation this audio belongs to")
    chunk_timestamps: List[float] = Field(description="List of chunk timestamps (for on-demand merging)")
    provider: str = Field(default="gcp", description="Storage provider (e.g., 'gcp')")
    started_at: Optional[datetime] = Field(
        default=None, description="When this audio file started (absolute timestamp)"
    )
    duration: float = Field(description="Duration in seconds")


class CategoryEnum(str, Enum):
    personal = 'personal'
    education = 'education'
    health = 'health'
    finance = 'finance'
    legal = 'legal'
    philosophy = 'philosophy'
    spiritual = 'spiritual'
    science = 'science'
    entrepreneurship = 'entrepreneurship'
    parenting = 'parenting'
    romance = 'romantic'
    travel = 'travel'
    inspiration = 'inspiration'
    technology = 'technology'
    business = 'business'
    social = 'social'
    work = 'work'
    sports = 'sports'
    politics = 'politics'
    literature = 'literature'
    history = 'history'
    architecture = 'architecture'
    # Added at 2024-01-23
    music = 'music'
    weather = 'weather'
    news = 'news'
    entertainment = 'entertainment'
    psychology = 'psychology'
    real = 'real'
    design = 'design'
    family = 'family'
    economics = 'economics'
    environment = 'environment'
    other = 'other'


class UpdateConversation(BaseModel):
    title: Optional[str] = None
    overview: Optional[str] = None


class ConversationPhoto(BaseModel):
    id: Optional[str] = None
    base64: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discarded: bool = False
    data_protection_level: Optional[str] = None

    @staticmethod
    def photos_as_string(photos: List['ConversationPhoto'], include_timestamps: bool = False) -> str:
        if not photos:
            return 'None'
        descriptions = []
        for p in photos:
            if p.description and p.description.strip():
                timestamp_str = ''
                if include_timestamps:
                    timestamp_str = f"[{p.created_at.strftime('%H:%M:%S')}] "
                descriptions.append(f'- {timestamp_str}"{p.description}"')

        if not descriptions:
            return 'None'
        return '\n'.join(descriptions)


# TODO: remove this class when the app is updated to use apps_results
class PluginResult(BaseModel):
    plugin_id: Optional[str]
    content: str


class AppResult(BaseModel):
    app_id: Optional[str]
    content: str


class ActionItem(BaseModel):
    description: str = Field(description="The action item to be completed")
    completed: bool = False
    created_at: Optional[datetime] = Field(default=None, description="When the action item was created")
    updated_at: Optional[datetime] = Field(default=None, description="When the action item was last updated")
    due_at: Optional[datetime] = Field(default=None, description="When the action item is due")
    completed_at: Optional[datetime] = Field(default=None, description="When the action item was completed")
    conversation_id: Optional[str] = Field(
        default=None, description="ID of the conversation this action item came from"
    )

    @staticmethod
    def actions_to_string(action_items: List['ActionItem']) -> str:
        if not action_items:
            return 'None'

        result = []
        for item in action_items:
            status = 'completed' if item.completed else 'pending'
            line = f"- {item.description} ({status})"

            # Add timestamp information
            timestamps = []
            if item.created_at:
                timestamps.append(f"Created: {item.created_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            if item.due_at:
                timestamps.append(f"Due: {item.due_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            if item.completed_at:
                timestamps.append(f"Completed: {item.completed_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")

            if timestamps:
                line += f" [{', '.join(timestamps)}]"

            result.append(line)

        return '\n'.join(result)


class Event(BaseModel):
    title: str = Field(description="The title of the event")
    description: str = Field(description="A brief description of the event", default='')
    start: datetime = Field(description="The start date and time of the event")
    duration: int = Field(description="The duration of the event in minutes", default=30)
    created: bool = False

    def as_dict_cleaned_dates(self):
        event_dict = self.dict()
        event_dict['start'] = event_dict['start'].isoformat()
        return event_dict

    @staticmethod
    def events_to_string(events: List['Event']) -> str:
        if not events:
            return 'None'
        # Format the datetime for better readability in the prompt
        return '\n'.join(
            [
                f"- {event.title} (Starts: {event.start.strftime('%Y-%m-%d %H:%M:%S %Z')}, Duration: {event.duration} mins)"
                for event in events
            ]
        )


class ActionItemsExtraction(BaseModel):
    action_items: List[ActionItem] = Field(description="A list of action items from the conversation", default=[])


class Structured(BaseModel):
    title: str = Field(description="A title/name for this conversation", default='')
    overview: str = Field(
        description="A brief overview of the conversation, highlighting the key details from it",
        default='',
    )
    emoji: str = Field(description="An emoji to represent the conversation", default='🧠')
    category: CategoryEnum = Field(description="A category for this conversation", default=CategoryEnum.other)
    action_items: List[ActionItem] = Field(description="A list of action items from the conversation", default=[])
    events: List[Event] = Field(
        description="A list of events extracted from the conversation, that the user must have on his calendar.",
        default=[],
    )

    @field_validator('category', mode='before')
    @classmethod
    def set_category_default_on_error(cls, v: any) -> 'CategoryEnum':
        if isinstance(v, CategoryEnum):
            return v
        try:
            return CategoryEnum(v)
        except ValueError:
            return CategoryEnum.other

    def __str__(self):
        result = (
            f"{str(self.title).capitalize()} ({str(self.category.value).capitalize()})\n"
            f"{str(self.overview).capitalize()}\n"
        )

        if self.action_items:
            result += f"Action Items:\n{ActionItem.actions_to_string(self.action_items)}\n"

        if self.events:
            result += f"Events:\n{Event.events_to_string(self.events)}\n"
        return result.strip()


class Geolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    location_type: Optional[str] = None


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


class ConversationSource(str, Enum):
    friend = 'friend'
    omi = 'omi'
    fieldy = 'fieldy'
    bee = 'bee'
    plaud = 'plaud'
    frame = 'frame'
    friend_com = 'friend_com'
    apple_watch = 'apple_watch'
    phone = 'phone'
    desktop = 'desktop'
    openglass = 'openglass'
    screenpipe = 'screenpipe'
    workflow = 'workflow'
    sdcard = 'sdcard'
    external_integration = 'external_integration'
    limitless = 'limitless'
    onboarding = 'onboarding'


class ConversationVisibility(str, Enum):
    private = 'private'
    shared = 'shared'
    public = 'public'


class PostProcessingStatus(str, Enum):
    not_started = 'not_started'
    in_progress = 'in_progress'
    completed = 'completed'
    canceled = 'canceled'
    failed = 'failed'


class ConversationStatus(str, Enum):
    in_progress = 'in_progress'
    processing = 'processing'
    merging = 'merging'
    completed = 'completed'
    failed = 'failed'


class PostProcessingModel(str, Enum):
    fal_whisperx = 'fal_whisperx'


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

    def __init__(self, **data):
        super().__init__(**data)
        # Update plugins_results based on apps_results
        self.plugins_results = [PluginResult(plugin_id=app.app_id, content=app.content) for app in self.apps_results]
        self.processing_memory_id = self.processing_conversation_id

    @staticmethod
    def conversations_to_string(
        conversations: List['Conversation'],
        use_transcript: bool = False,
        include_timestamps: bool = False,
        people: List[Person] = None,
    ) -> str:
        result = []
        people_map = {p.id: p for p in people} if people else {}
        for i, conversation in enumerate(conversations):
            if isinstance(conversation, dict):
                conversation = Conversation(**conversation)
            formatted_date = conversation.created_at.astimezone(timezone.utc).strftime("%d %b %Y at %H:%M") + " UTC"
            conversation_str = (
                f"Conversation #{i + 1}\n"
                f"{formatted_date} ({str(conversation.structured.category.value).capitalize()})\n"
            )

            # Add started_at and finished_at if available
            if conversation.started_at:
                formatted_started = (
                    conversation.started_at.astimezone(timezone.utc).strftime("%d %b %Y at %H:%M") + " UTC"
                )
                conversation_str += f"Started: {formatted_started}\n"
            if conversation.finished_at:
                formatted_finished = (
                    conversation.finished_at.astimezone(timezone.utc).strftime("%d %b %Y at %H:%M") + " UTC"
                )
                conversation_str += f"Finished: {formatted_finished}\n"

            conversation_str += (
                f"{str(conversation.structured.title).capitalize()}\n"
                f"{str(conversation.structured.overview).capitalize()}\n"
            )

            # attendees
            if people_map:
                conv_person_ids = set(conversation.get_person_ids())
                if conv_person_ids:
                    attendees_names = [people_map[pid].name for pid in conv_person_ids if pid in people_map]
                    if attendees_names:
                        attendees = ", ".join(attendees_names)
                        conversation_str += f"Attendees: {attendees}\n"

            if conversation.structured.action_items:
                conversation_str += "Action Items:\n"
                for item in conversation.structured.action_items:
                    conversation_str += f"- {item.description}\n"

            if conversation.structured.events:
                conversation_str += "Events:\n"
                for event in conversation.structured.events:
                    conversation_str += f"- {event.title} ({event.start} - {event.duration} minutes)\n"

            if conversation.apps_results and len(conversation.apps_results) > 0:
                conversation_str += "Summarization:\n"
                conversation_str += f"{conversation.apps_results[0].content}"

            if use_transcript:
                conversation_str += f"\nTranscript:\n{conversation.get_transcript(include_timestamps=include_timestamps, people=people)}\n"
                # photos
                photo_descriptions = conversation.get_photos_descriptions(include_timestamps=include_timestamps)
                if photo_descriptions != 'None':
                    conversation_str += f"Photo Descriptions from a wearable camera:\n{photo_descriptions}\n"

            result.append(conversation_str.strip())

        return "\n\n---------------------\n\n".join(result).strip()

    def get_transcript(self, include_timestamps: bool, people: List[Person] = None) -> str:
        # Warn: missing transcript for workflow source, external integration source
        return TranscriptSegment.segments_as_string(
            self.transcript_segments, include_timestamps=include_timestamps, people=people
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

    def get_transcript(self, include_timestamps: bool, people: List[Person] = None) -> str:
        return TranscriptSegment.segments_as_string(
            self.transcript_segments, include_timestamps=include_timestamps, people=people
        )

    def get_person_ids(self) -> List[str]:
        if not self.transcript_segments:
            return []
        return list(set(segment.person_id for segment in self.transcript_segments if segment.person_id))


class ExternalIntegrationConversationSource(str, Enum):
    audio = 'audio_transcript'
    message = 'message'
    other = 'other_text'


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
