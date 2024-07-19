from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class Structured(BaseModel):
    title: str
    overview: str
    emoji: str = ''
    category: str = 'other'


class ActionItem(BaseModel):
    description: str


class Event(BaseModel):
    title: str
    startsAt: datetime
    duration: int
    description: Optional[str] = ''
    created: bool = False


class MemoryPhoto(BaseModel):
    base64: str
    description: str


class PluginResponse(BaseModel):
    pluginId: Optional[str] = None
    content: str


class TranscriptSegment(BaseModel):
    text: str
    speaker: str
    speaker_id: int
    is_user: bool
    start: float
    end: float


class Memory(BaseModel):
    createdAt: datetime
    startedAt: Optional[datetime] = None
    finishedAt: Optional[datetime] = None
    transcript: str = ''
    transcriptSegments: List[TranscriptSegment] = []
    photos: Optional[List[MemoryPhoto]] = []
    recordingFilePath: Optional[str] = None
    recordingFileBase64: Optional[str] = None
    structured: Structured
    pluginsResponse: List[PluginResponse] = []
    discarded: bool
