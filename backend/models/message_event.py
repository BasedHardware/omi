from typing import List, Optional, Any

from pydantic import BaseModel

from models.conversation import Conversation, Message, ConversationPhoto


# Freemium action constants
FREEMIUM_ACTION_SETUP_ON_DEVICE_STT = "setup_on_device_stt"
FREEMIUM_ACTION_NONE = "none"


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


class TranslationEvent(MessageEvent):
    event_type: str = "translating"
    segments: List = []

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class PhotoProcessingEvent(MessageEvent):
    event_type: str = "photo_processing"
    temp_id: str
    photo_id: str

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class PhotoDescribedEvent(MessageEvent):
    event_type: str = "photo_described"
    photo_id: str
    description: str
    discarded: bool

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class SpeakerLabelSuggestionEvent(MessageEvent):
    event_type: str = "speaker_label_suggestion"
    speaker_id: int
    person_id: str
    person_name: str
    segment_id: str

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j


class FreemiumThresholdReachedEvent(MessageEvent):
    event_type: str = "freemium_threshold_reached"
    remaining_seconds: int
    action: str

    def to_json(self):
        j = self.model_dump(mode="json")
        j["type"] = self.event_type
        del j["event_type"]
        return j
