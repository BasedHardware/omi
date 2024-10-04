from typing import List, Optional

from pydantic import BaseModel

from models.memory import Memory, Message


class MessageEvent(BaseModel):
    event_type: str

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        return j


class MemoryEvent(MessageEvent):
    memory: Memory
    messages: Optional[List[Message]] = []

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        return j