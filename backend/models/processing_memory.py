from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

from models.memory import Geolocation, MemoryPhoto
from models.transcript_segment import TranscriptSegment

class ProcessingMemory(BaseModel):
    id: str
    created_at: datetime
    timer_start: Optional[int]
    language: Optional[str] = None  # applies only to Friend # TODO: once released migrate db to default 'en'
    geolocation: Optional[Geolocation] = None
    transcript_segments: List[TranscriptSegment] = []

    memory_id: Optional[str]
    message_ids: List[str] = []
