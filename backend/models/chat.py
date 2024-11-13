from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class MessageSender(str, Enum):
    ai = 'ai'
    human = 'human'


class MessageType(str, Enum):
    text = 'text'
    day_summary = 'day_summary'


class MessageMemoryStructured(BaseModel):
    title: str
    emoji: str


class MessageMemory(BaseModel):
    id: str
    structured: MessageMemoryStructured
    created_at: datetime


class Message(BaseModel):
    id: str
    text: str
    created_at: datetime
    sender: MessageSender
    plugin_id: Optional[str] = None
    from_external_integration: bool = False
    type: MessageType
    memories_id: List[str] = []  # used in db
    memories: List[MessageMemory] = []  # used front facing

    @staticmethod
    def get_messages_as_string(
            messages: List['Message'],
            use_user_name_if_available: bool = False,
            use_plugin_name_if_available: bool = False
    ) -> str:
        sorted_messages = sorted(messages, key=lambda m: m.created_at)

        def get_sender_name(message: Message) -> str:
            if message.sender == 'human':
                return 'User'
            # elif use_plugin_name_if_available and message.plugin_id is not None:
            #     plugin = next((p for p in plugins if p.id == message.plugin_id), None)
            #     if plugin:
            #         return plugin.name RESTORE ME
            return message.sender.upper()

        formatted_messages = [
            f"({message.created_at.strftime('%d %b, at %H:%M')}) {get_sender_name(message)}: {message.text}"
            for message in sorted_messages
        ]

        return '\n'.join(formatted_messages)


class ResponseMessage(Message):
    ask_for_nps: Optional[bool] = False


class SendMessageRequest(BaseModel):
    text: str
