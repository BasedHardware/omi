from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

from models.facts import FactCategory, FactDB


class ConversationTimestampRange(BaseModel):
    start: int
    end: int


class ScreenPipeCreateConversation(BaseModel):
    request_id: str
    source: str
    text: str
    timestamp_range: ConversationTimestampRange


class ExternalIntegrationFactSource(str, Enum):
    email = "email"
    post = "social_post"
    other = "other"


class ExternalIntegrationFact(BaseModel):
    content: str = Field(description="The content of the fact")
    tags: Optional[List[str]] = Field(description="Tags associated with the fact", default=None)


class ExternalIntegrationCreateFact(BaseModel):
    text: str = Field(description="The original text from which the fact was extracted")
    text_source: ExternalIntegrationFactSource = Field(description="The source of the text", default=ExternalIntegrationFactSource.other)
    text_source_spec: Optional[str] = Field(description="Additional specification about the source", default=None)
    app_id: Optional[str] = None
    memories: Optional[List[ExternalIntegrationFact]] = Field(description="List of explicit memories(facts) to be created", default=None)


class EmptyResponse(BaseModel):
    pass


class MemoryItem(FactDB):
    """
    Memory item model that extends FactDB for API responses
    """

    class Config:
        exclude_none = True

class MemoriesResponse(BaseModel):
    memories: List[MemoryItem] = Field(description="List of user memories (facts)")


class ConversationItem(BaseModel):
    """
    Conversation item model for API responses
    """
    id: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    source: str
    structured: Optional[Dict[str, Any]] = None
    transcript_segments: Optional[List[Dict[str, Any]]] = None
    visibility: Optional[str] = None
    discarded: Optional[bool] = False
    deleted: Optional[bool] = False
    app_id: Optional[str] = None
    geolocation: Optional[Dict[str, Any]] = None
    language: Optional[str] = None
    processing_memory_id: Optional[str] = None
    external_data: Optional[Dict] = None

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
        exclude_none = True


class ConversationsResponse(BaseModel):
    conversations: List[ConversationItem] = Field(description="List of user conversations")
