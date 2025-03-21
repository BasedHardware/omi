from typing import List, Optional

from pydantic import BaseModel

from models.conversation import Conversation, Message


class MessageEvent(BaseModel):
    event_type: str

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class ConversationEvent(MessageEvent):
    memory: Conversation
    messages: Optional[List[Message]] = []

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class NewConversationCreated(MessageEvent):
    processing_memory_id: Optional[str] = None
    memory_id: Optional[str] = None
    message_ids: Optional[List[str]] = []
    memory: Conversation
    messages: Optional[List[Message]] = []

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class NewProcessingConversationCreated(MessageEvent):
    processing_memory_id: Optional[str] = None
    memory_id: Optional[str] = None

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class ProcessingConversationStatusChanged(MessageEvent):
    processing_memory_id: Optional[str] = None
    processing_memory_status: Optional[str] = None
    memory_id: Optional[str] = None

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class MemoryBackwardSycnedEvent(MessageEvent):
    name: Optional[str] = None

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class MessageServiceStatusEvent(MessageEvent):
    event_type: str = "service_status"
    status: str
    status_text: Optional[str] = None

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class PingEvent(MessageEvent):
    event_type: str = "ping"

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class LastConversationEvent(MessageEvent):
    event_type: str = "last_memory"
    memory_id: str

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j
