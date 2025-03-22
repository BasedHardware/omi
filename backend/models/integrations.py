from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

from models.facts import FactCategory


class MemoryTimestampRange(BaseModel):
    start: int
    end: int


class ScreenPipeCreateMemory(BaseModel):
    request_id: str
    source: str
    text: str
    timestamp_range: MemoryTimestampRange


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
