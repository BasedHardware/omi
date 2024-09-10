from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from models.memory import Geolocation, MemoryPhoto
from models.transcript_segment import TranscriptSegment

class ProcessingMemory(BaseModel):
    id: str
    session_id: Optional[str] = None
    created_at: datetime
    timer_start: float
    language: Optional[str] = None  # applies only to Friend # TODO: once released migrate db to default 'en'
    transcript_segments: List[TranscriptSegment] = []
    geolocation: Optional[Geolocation] = None
    emotional_feedback: Optional[bool] = False

    memory_id: Optional[str] = None
    message_ids: List[str] = []

class UpdateProcessingMemory(BaseModel):
    id: Optional[str] = None
    geolocation: Optional[Geolocation] = None
    emotional_feedback: Optional[bool] = False

class UpdateProcessingMemoryResponse(BaseModel):
    result: ProcessingMemory
