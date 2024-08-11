from datetime import datetime
from enum import Enum
from typing import List, Optional, Dict

from fastapi import FastAPI
from pydantic import BaseModel, Field

from models.chat import Message
from models.transcript_segment import TranscriptSegment

app = FastAPI()


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


class Event(BaseModel):
    title: str = Field(description="The title of the event")
    description: str = Field(description="A brief description of the event", default='')
    start: datetime = Field(description="The start date and time of the event")
    duration: int = Field(description="The duration of the event in minutes", default=30)
    created: bool = False


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
        result = f"{self.emoji} {self.title} ({self.category})\n\nSummary: {self.overview}\n\n"
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

    @staticmethod
    def memories_to_string(memories: List['Memory']) -> str:
        result = []
        for memory in memories:
            memory_str = f"{memory.created_at.isoformat().split('.')[0]}\nTitle: {memory.structured.title}\nSummary: {memory.structured.overview}\n"
            if memory.structured.action_items:
                memory_str += "Action Items:\n"
                for item in memory.structured.action_items:
                    memory_str += f"  - {item.description}\n"
            memory_str += f"Category: {memory.structured.category}\n"
            result.append(memory_str.strip())
        return "\n\n".join(result)

    def get_transcript(self) -> str:
        return TranscriptSegment.segments_as_string(self.transcript_segments, include_timestamps=True)


class CreateMemory(BaseModel):
    started_at: datetime
    finished_at: datetime
    transcript_segments: List[TranscriptSegment]
    geolocation: Optional[Geolocation] = None

    photos: List[MemoryPhoto] = []

    source: MemorySource = MemorySource.friend
    language: Optional[str] = None

    def get_transcript(self) -> str:
        return TranscriptSegment.segments_as_string(self.transcript_segments, include_timestamps=True)


class CreateMemoryResponse(BaseModel):
    memory: Memory
    messages: List[Message] = []
