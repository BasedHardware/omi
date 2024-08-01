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
    plugin_id: Optional[str] = None
    from_external_integration: bool = False
    type: MessageType
    memories: List[Memory] = []  # TODO: should be a smaller version of memory, id + title

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
            f"({message.created_at.isoformat().split('.')[0]}) {get_sender_name(message)}: {message.text}"
            for message in sorted_messages
        ]

        return '\n'.join(formatted_messages)


class SendMessageRequest(BaseModel):
    text: str
