from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

from models.facts import FactCategory


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


class ExternalIntegrationCreateFact(BaseModel):
    text: str = Field(description="The original text from which the fact was extracted")
    text_source: ExternalIntegrationFactSource = Field(description="The source of the text", default=ExternalIntegrationFactSource.other)
    text_source_spec: Optional[str] = Field(description="Additional specification about the source", default=None)
    app_id: Optional[str] = None


class EmptyResponse(BaseModel):
    pass
