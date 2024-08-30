from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from models.chat import Message
from models.memory import Geolocation, MemoryPhoto
from models.transcript_segment import TranscriptSegment

class ProcessingMemory(BaseModel):
    id: str
    created_at: datetime
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    language: Optional[str] = None  # applies only to Friend # TODO: once released migrate db to default 'en'
    geolocation: Optional[Geolocation] = None
    photos: List[MemoryPhoto] = []
    trigger_integrations = Optional[bool] = False

    memory_id: Optional[str]
    message_ids: List[str] = []
