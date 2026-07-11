from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CategoryEnum(str, Enum):
    personal = "personal"
    education = "education"
    health = "health"
    finance = "finance"
    legal = "legal"
    philosophy = "philosophy"
    spiritual = "spiritual"
    science = "science"
    entrepreneurship = "entrepreneurship"
    parenting = "parenting"
    romance = "romantic"
    travel = "travel"
    inspiration = "inspiration"
    technology = "technology"
    business = "business"
    social = "social"
    work = "work"
    sports = "sports"
    politics = "politics"
    literature = "literature"
    history = "history"
    architecture = "architecture"
    music = "music"
    weather = "weather"
    news = "news"
    entertainment = "entertainment"
    psychology = "psychology"
    real = "real"
    design = "design"
    family = "family"
    economics = "economics"
    environment = "environment"
    other = "other"


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
    capture_kind: Optional[Literal['explicit_command', 'clear_commitment', 'direct_request', 'inferred_next_step']] = (
        None
    )
    capture_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    ownership_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    capture_owner: Optional[Literal['user', 'other', 'unknown']] = None
    concrete_deliverable: Optional[bool] = Field(
        default=None,
        description='True only when the commitment names a concrete deliverable or outcome',
    )
    candidate_action: Optional[Literal['create', 'update', 'complete']] = None
    target_task_id: Optional[str] = None

    @staticmethod
    def actions_to_string(action_items: List["ActionItem"]) -> str:
        if not action_items:
            return "None"

        result = []
        for item in action_items:
            status = "completed" if item.completed else "pending"
            line = f"- {item.description} ({status})"

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

        return "\n".join(result)


class Event(BaseModel):
    title: str = Field(description="The title of the event")
    description: str = Field(description="A brief description of the event", default="")
    start: datetime = Field(description="The start date and time of the event")
    duration: int = Field(description="The duration of the event in minutes", default=30)
    created: bool = False

    def as_dict_cleaned_dates(self):
        event_dict = self.dict()
        event_dict["start"] = event_dict["start"].isoformat()
        return event_dict

    @staticmethod
    def events_to_string(events: List["Event"]) -> str:
        if not events:
            return "None"
        return "\n".join(
            [
                f"- {event.title} (Starts: {event.start.strftime('%Y-%m-%d %H:%M:%S %Z')}, Duration: {event.duration} mins)"
                for event in events
            ]
        )


class ActionItemsExtraction(BaseModel):
    action_items: List[ActionItem] = Field(
        description="A list of action items from the conversation", default_factory=list
    )


class Structured(BaseModel):
    title: str = Field(description="A title/name for this conversation", default="")
    overview: str = Field(
        description="A brief overview of the conversation, highlighting the key details from it",
        default="",
    )
    emoji: str = Field(description="An emoji to represent the conversation", default="🧠")
    category: CategoryEnum = Field(description="A category for this conversation", default=CategoryEnum.other)
    action_items: List[ActionItem] = Field(
        description="A list of action items from the conversation", default_factory=list
    )
    events: List[Event] = Field(
        description="A list of events extracted from the conversation, that the user must have on his calendar.",
        default_factory=list,
    )

    @field_validator("category", mode="before")
    @classmethod
    def set_category_default_on_error(cls, value):
        if isinstance(value, CategoryEnum):
            return value
        try:
            return CategoryEnum(value)
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


class ConversationPhoto(BaseModel):
    id: Optional[str] = None
    base64: str
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    discarded: bool = False
    data_protection_level: Optional[str] = None

    @staticmethod
    def photos_as_string(photos: List["ConversationPhoto"], include_timestamps: bool = False) -> str:
        if not photos:
            return "None"
        descriptions = []
        for photo in photos:
            if photo.description and photo.description.strip():
                timestamp_str = ""
                if include_timestamps:
                    timestamp_str = f"[{photo.created_at.strftime('%H:%M:%S')}] "
                descriptions.append(f'- {timestamp_str}"{photo.description}"')

        if not descriptions:
            return "None"
        return "\n".join(descriptions)


class PluginResult(BaseModel):
    plugin_id: Optional[str] = None
    content: str


class AppResult(BaseModel):
    app_id: Optional[str] = None
    content: str


class TranscriptSegment(BaseModel):
    id: Optional[str] = None
    text: str
    speaker: Optional[str] = "SPEAKER_00"
    speaker_id: Optional[int] = None
    is_user: bool
    person_id: Optional[str] = None
    start: float
    end: float

    def __init__(self, **data):
        super().__init__(**data)
        if self.speaker:
            try:
                self.speaker_id = int(self.speaker.split("_", 1)[1])
            except (ValueError, IndexError):
                self.speaker_id = 0
        else:
            self.speaker_id = 0

    def get_timestamp_string(self):
        start_duration = timedelta(seconds=int(self.start))
        end_duration = timedelta(seconds=int(self.end))
        return f'{str(start_duration).split(".")[0]} - {str(end_duration).split(".")[0]}'

    @staticmethod
    def segments_as_string(segments, include_timestamps=False, user_name: str = None):
        if not user_name:
            user_name = "User"
        transcript = ""
        include_timestamps = include_timestamps and TranscriptSegment.can_display_seconds(segments)
        for segment in segments:
            segment_text = segment.text.strip()
            timestamp_str = f"[{segment.get_timestamp_string()}] " if include_timestamps else ""
            transcript += (
                f'{timestamp_str}{user_name if segment.is_user else f"Speaker {segment.speaker_id}"}: '
                f"{segment_text}\n\n"
            )
        return transcript.strip()

    @staticmethod
    def combine_segments(segments: [], new_segments: [], delta_seconds: int = 0):
        if not new_segments or len(new_segments) == 0:
            return segments

        joined_similar_segments = []
        for new_segment in new_segments:
            if delta_seconds > 0:
                new_segment.start += delta_seconds
                new_segment.end += delta_seconds

            if joined_similar_segments and (
                joined_similar_segments[-1].speaker == new_segment.speaker
                or (joined_similar_segments[-1].is_user and new_segment.is_user)
            ):
                joined_similar_segments[-1].text += f" {new_segment.text}"
                joined_similar_segments[-1].end = new_segment.end
            else:
                joined_similar_segments.append(new_segment)

        if (
            segments
            and (
                segments[-1].speaker == joined_similar_segments[0].speaker
                or (segments[-1].is_user and joined_similar_segments[0].is_user)
            )
            and (joined_similar_segments[0].start - segments[-1].end < 30)
        ):
            segments[-1].text += f" {joined_similar_segments[0].text}"
            segments[-1].end = joined_similar_segments[0].end
            joined_similar_segments.pop(0)

        segments.extend(joined_similar_segments)

        for i, segment in enumerate(segments):
            segments[i].text = (
                segments[i].text.strip().replace("  ", "").replace(" ,", ",").replace(" .", ".").replace(" ?", "?")
            )
        return segments

    @staticmethod
    def can_display_seconds(segments):
        for i in range(len(segments)):
            for j in range(i + 1, len(segments)):
                if segments[i].start > segments[j].end or segments[i].end > segments[j].start:
                    return False
        return True


class Conversation(BaseModel):
    id: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    transcript_segments: List[TranscriptSegment] = Field(default_factory=list)
    photos: Optional[List[ConversationPhoto]] = Field(default_factory=list)
    structured: Structured
    apps_results: List[AppResult] = Field(default_factory=list)
    plugins_results: List[PluginResult] = Field(default_factory=list)
    discarded: bool = False

    @model_validator(mode="after")
    def sync_plugin_results(self):
        if self.apps_results and not self.plugins_results:
            self.plugins_results = [
                PluginResult(plugin_id=app.app_id, content=app.content) for app in self.apps_results
            ]
        return self

    def get_transcript(self, include_timestamps: bool = False, user_name: str = None) -> str:
        return TranscriptSegment.segments_as_string(
            self.transcript_segments,
            include_timestamps=include_timestamps,
            user_name=user_name,
        )

    def get_duration(self) -> Optional[str]:
        if not self.transcript_segments:
            return None

        start = min(segment.start for segment in self.transcript_segments)
        end = max(segment.end for segment in self.transcript_segments)
        duration = timedelta(seconds=int(end - start))
        return str(duration).split(".")[0]


class Geolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    location_type: Optional[str] = None


class ExternalIntegrationConversationSource(str, Enum):
    audio = "audio_transcript"
    other = "other_text"


class ExternalIntegrationCreateConversation(BaseModel):
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    text: str
    text_source: ExternalIntegrationConversationSource = ExternalIntegrationConversationSource.audio
    language: Optional[str] = None
    geolocation: Optional[Geolocation] = None


class EndpointResponse(BaseModel):
    message: str = Field(description="A short message to be sent as notification to the user, if needed.", default="")
