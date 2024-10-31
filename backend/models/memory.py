from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict

from pydantic import BaseModel, Field

from models.chat import Message
from models.transcript_segment import TranscriptSegment


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
    other = 'other'


class UpdateMemory(BaseModel):
    title: Optional[str] = None
    overview: Optional[str] = None


class MemoryPhoto(BaseModel):
    base64: str
    description: str


class PluginResult(BaseModel):
    plugin_id: Optional[str]
    content: str


class ActionItem(BaseModel):
    description: str = Field(description="The action item to be completed")
    completed: bool = False  # IGNORE ME from the model parser
    deleted: bool = False


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


class Structured(BaseModel):
    title: str = Field(description="A title/name for this conversation", default='')
    overview: str = Field(
        description="A brief overview of the conversation, highlighting the key details from it",
        default='',
    )
    emoji: str = Field(description="An emoji to represent the memory", default='🧠')
    category: CategoryEnum = Field(description="A category for this memory", default=CategoryEnum.other)
    action_items: List[ActionItem] = Field(description="A list of action items from the conversation", default=[])
    events: List[Event] = Field(
        description="A list of events extracted from the conversation, that the user must have on his calendar.",
        default=[],
    )

    def __str__(self):
        result = (f"{str(self.title).capitalize()} ({str(self.category.value).capitalize()})\n"
                  f"{str(self.overview).capitalize()}\n")

        if self.action_items:
            result += "Action Items:\n"
            for item in self.action_items:
                result += f"- {item.description}\n"

        if self.events:
            result += "Events:\n"
            for event in self.events:
                result += f"- {event.title} ({event.start} - {event.duration} minutes)\n"
        return result.strip()


class Geolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    location_type: Optional[str] = None


class MemorySource(str, Enum):
    friend = 'friend'
    openglass = 'openglass'
    screenpipe = 'screenpipe'
    workflow = 'workflow'
    sdcard = 'sdcard'


class MemoryVisibility(str, Enum):
    private = 'private'
    shared = 'shared'
    public = 'public'


class PostProcessingStatus(str, Enum):
    not_started = 'not_started'
    in_progress = 'in_progress'
    completed = 'completed'
    canceled = 'canceled'
    failed = 'failed'


class MemoryStatus(str, Enum):
    in_progress = 'in_progress'
    processing = 'processing'
    completed = 'completed'
    failed = 'failed'


class PostProcessingModel(str, Enum):
    fal_whisperx = 'fal_whisperx'


class MemoryPostProcessing(BaseModel):
    status: PostProcessingStatus
    model: PostProcessingModel
    fail_reason: Optional[str] = None


class Memory(BaseModel):
    id: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]

    source: Optional[MemorySource] = MemorySource.friend  # TODO: once released migrate db to include this field
    language: Optional[str] = None  # applies only to Friend # TODO: once released migrate db to default 'en'

    structured: Structured
    transcript_segments: List[TranscriptSegment] = []
    geolocation: Optional[Geolocation] = None
    photos: List[MemoryPhoto] = []

    plugins_results: List[PluginResult] = []

    external_data: Optional[Dict] = None

    discarded: bool = False
    deleted: bool = False
    visibility: MemoryVisibility = MemoryVisibility.private

    processing_memory_id: Optional[str] = None
    status: Optional[MemoryStatus] = MemoryStatus.completed

    @staticmethod
    def memories_to_string(memories: List['Memory'], use_transcript: bool = False) -> str:
        result = []
        for i, memory in enumerate(memories):
            if isinstance(memory, dict):
                memory = Memory(**memory)
            formatted_date = memory.created_at.strftime("%d %b, at %H:%M")
            if use_transcript:
                memory_str = (f"Memory #{i + 1}\n"
                              f"{formatted_date} ({str(memory.structured.category.value).capitalize()})\n"
                              f"\nTranscript:\n{memory.get_transcript(include_timestamps=False)}\n")
                result.append(memory_str.strip())
                continue

            memory_str = (f"Memory #{i + 1}\n"
                          f"{formatted_date} ({str(memory.structured.category.value).capitalize()})\n"
                          f"{str(memory.structured.title).capitalize()}\n"
                          f"{str(memory.structured.overview).capitalize()}\n")

            if memory.structured.action_items:
                memory_str += "Action Items:\n"
                for item in memory.structured.action_items:
                    memory_str += f"- {item.description}\n"
            result.append(memory_str.strip())

        return "\n\n---------------------\n\n".join(result).strip()

    def get_transcript(self, include_timestamps: bool) -> str:
        # Warn: missing transcript for workflow source
        return TranscriptSegment.segments_as_string(self.transcript_segments, include_timestamps=include_timestamps)

    def as_dict_cleaned_dates(self):
        memory_dict = self.dict()
        memory_dict['structured']['events'] = [
            {**event, 'start': event['start'].isoformat()} for event in memory_dict['structured']['events']
        ]
        memory_dict['created_at'] = memory_dict['created_at'].isoformat()
        memory_dict['started_at'] = memory_dict['started_at'].isoformat() if memory_dict['started_at'] else None
        memory_dict['finished_at'] = memory_dict['finished_at'].isoformat() if memory_dict['finished_at'] else None
        return memory_dict


class CreateMemory(BaseModel):
    started_at: datetime
    finished_at: datetime
    transcript_segments: List[TranscriptSegment]
    geolocation: Optional[Geolocation] = None

    photos: List[MemoryPhoto] = []

    source: MemorySource = MemorySource.friend
    language: Optional[str] = None

    processing_memory_id: Optional[str] = None

    def get_transcript(self, include_timestamps: bool) -> str:
        return TranscriptSegment.segments_as_string(self.transcript_segments, include_timestamps=include_timestamps)


class WorkflowMemorySource(str, Enum):
    audio = 'audio_transcript'
    other = 'other_text'


class WorkflowCreateMemory(BaseModel):
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    text: str
    text_source: WorkflowMemorySource = WorkflowMemorySource.audio
    geolocation: Optional[Geolocation] = None

    source: MemorySource = MemorySource.workflow
    language: Optional[str] = None

    def get_transcript(self, include_timestamps: bool) -> str:
        return self.text


class CreateMemoryResponse(BaseModel):
    memory: Memory
    messages: List[Message] = []


class SetMemoryEventsStateRequest(BaseModel):
    events_idx: List[int]
    values: List[bool]


class SetMemoryActionItemsStateRequest(BaseModel):
    items_idx: List[int]
    values: List[bool]


class DeleteActionItemRequest(BaseModel):
    description: str
    completed: bool
