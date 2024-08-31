from pydantic import BaseModel, Field
from typing import List, Optional

from models.memory import Memory, Message

class MessageEvent(BaseModel):
    event_type: str

class NewMemoryCreated(MessageEvent):
    processing_memory_id: Optional[str] = None
    memory_id: Optional[str] = None
    message_ids: Optional[List[str]] = []
    memory: Memory
    messages: Optional[List[Message]] = []
