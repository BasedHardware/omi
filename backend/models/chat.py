from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel

from models.memory import Memory


class MessageSender(str, Enum):
    ai = 'ai'
    human = 'human'


class MessageType(str, Enum):
    text = 'text'
    daySummary = 'daySummary'


class Message(BaseModel):
    id: str
    text: str
    created_at: datetime
    sender: MessageSender
    plugin_id: Optional[str]
    from_external_integration: bool = False
    type: MessageType
    memories: List[Memory] = []  # TODO: should be a smaller version of memory, id + title


class SendMessageRequest(BaseModel):
    text: str
