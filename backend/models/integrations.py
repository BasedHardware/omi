from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional
from models.memory import Geolocation


class MemoryTimestampRange(BaseModel):
    start: int
    end: int


class ScreenPipeCreateMemory(BaseModel):
    request_id: str
    source: str
    text: str
    timestamp_range: MemoryTimestampRange


class WorkflowMemorySource(str, Enum):
    audio = 'audio_transcript'
    other = 'other_text'


class WorkflowCreateMemory(BaseModel):
    source: WorkflowMemorySource = WorkflowMemorySource.audio
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    text: str
    language: Optional[str] = None
    geolocation: Optional[Geolocation] = None
