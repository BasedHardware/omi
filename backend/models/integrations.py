from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime, timezone

from models.memories import MemoryCategory, MemoryDB
from models.transcript_segment import TranscriptSegment as BaseTranscriptSegment


class ConversationTimestampRange(BaseModel):
    start: int
    end: int


class ScreenPipeCreateConversation(BaseModel):
    request_id: str
    source: str
    text: str
    timestamp_range: ConversationTimestampRange


class ExternalIntegrationMemorySource(str, Enum):
    email = "email"
    post = "social_post"
    other = "other"


class ExternalIntegrationMemory(BaseModel):
    content: str = Field(description="The content of the memory (fact)")
    tags: Optional[List[str]] = Field(description="Tags associated with the memory (fact)", default=None)


class ExternalIntegrationCreateMemory(BaseModel):
    text: Optional[str] = Field(description="The original text from which the fact was extracted")
    text_source: ExternalIntegrationMemorySource = Field(
        description="The source of the text", default=ExternalIntegrationMemorySource.other
    )
    text_source_spec: Optional[str] = Field(description="Additional specification about the source", default=None)
    app_id: Optional[str] = None
    memories: Optional[List[ExternalIntegrationMemory]] = Field(
        description="List of explicit memories(facts) to be created", default=None
    )


class EmptyResponse(BaseModel):
    pass


class ConversationCreateResponse(BaseModel):
    status: str
    conversation_id: str


class MemoryItem(MemoryDB):
    """
    Memory item model that extends MemoryDB for API responses
    """

    class Config:
        exclude_none = True


class MemoriesResponse(BaseModel):
    memories: List[MemoryItem] = Field(description="List of user memories (facts)")


class ActionItem(BaseModel):
    description: str = Field(description="The action item to be completed")
    completed: bool = False
    exported: bool = False
    export_date: Optional[datetime] = None
    export_platform: Optional[str] = None


class Event(BaseModel):
    title: str = Field(description="The title of the event")
    description: str = Field(description="A brief description of the event", default='')
    start: datetime = Field(description="The start date and time of the event")
    duration: int = Field(description="The duration of the event in minutes", default=30)
    created: bool = False

    def as_dict_cleaned_dates(self):
        event_dict = self.dict()
        start_time = event_dict['start']
        if start_time.tzinfo is None:
            event_dict['start'] = start_time.isoformat() + 'Z'
        else:
            event_dict['start'] = start_time.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        return event_dict


class ConversationItemStructured(BaseModel):
    title: str
    overview: str
    emoji: str = "🧠"
    category: str = "other"
    action_items: List[ActionItem] = Field(default=[])
    events: List[Event] = Field(default=[])


class ConversationItemGeolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    location_type: Optional[str] = None


class ConversationItemTranscriptSegment(BaseModel):
    text: str
    speaker: Optional[str] = None
    is_user: bool = False
    person_id: Optional[str] = None
    start: float = 0.0
    end: float = 0.0


class ConversationItem(BaseModel):
    id: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    source: str
    structured: Optional[ConversationItemStructured] = None
    transcript_segments: Optional[List[ConversationItemTranscriptSegment]] = None
    discarded: Optional[bool] = False
    app_id: Optional[str] = None
    language: Optional[str] = None
    external_data: Optional[Dict] = None
    geolocation: Optional[ConversationItemGeolocation] = None
    status: Optional[str] = None

    class Config:
        json_encoders = {
            datetime: lambda v: (
                v.isoformat() + 'Z'
                if v.tzinfo is None
                else v.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
            )
        }


class ConversationsResponse(BaseModel):
    conversations: List[ConversationItem] = Field(description="List of user conversations")


class SearchConversationsResponse(BaseModel):
    conversations: List[ConversationItem] = Field(description="List of user conversations")
    total_pages: int = Field(description="Total number of pages")
    current_page: int = Field(description="Current page number")
    per_page: int = Field(description="Number of items per page")

class TaskItem(BaseModel):
    """Task (action item) model for API responses"""
    id: str
    description: str
    completed: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: (
                v.isoformat() + 'Z'
                if v.tzinfo is None
                else v.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
            )
        }


class TasksResponse(BaseModel):
    tasks: List[TaskItem] = Field(description="List of user tasks (action items)")
