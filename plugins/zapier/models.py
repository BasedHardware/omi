from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from models import ExternalIntegrationConversationSource, Geolocation


class ZapierSubcribeModel(BaseModel):
    target_url: str = Field(description="Target url is the url for web hook calling", default='')


class ZapierCreateConversation(BaseModel):
    icon: dict
    title: str
    speakers: int
    category: str
    duration: int
    overview: str
    transcript: str


class ZapierActionCreateConversation(BaseModel):
    text: str
    source: ExternalIntegrationConversationSource  # text_source
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    language: Optional[str] = None
    geolocation: Optional[Geolocation] = None
