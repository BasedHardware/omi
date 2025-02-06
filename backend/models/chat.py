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

class FileChat(BaseModel):
    id: str
    name: str
    thumbnail: Optional[str] = ""
    mime_type: str
    openai_file_id: str
    created_at: datetime
    deleted: bool = False
    thumb_name: Optional[str] = ""


    def is_image(self):
        return self.mime_type.startswith("image")

    def dict(self, **kwargs):
        exclude_fields = {'thumb_name'}
        return super().dict(exclude=exclude_fields, **kwargs)


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
    deleted: bool = False
    reported: bool = False
    report_reason: Optional[str] = None
    files_id: List[str] = [] # file attached with message
    reference_files_id: List[str] = [] # related files with message
    files: List[FileChat] = []

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
            return message.sender.upper()  # TODO: use plugin id

        formatted_messages = [
            f"({message.created_at.strftime('%d %b %Y at %H:%M UTC')}) {get_sender_name(message)}: {message.text}"
            for message in sorted_messages
        ]

        return '\n'.join(formatted_messages)

    @staticmethod
    def get_messages_as_xml(
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
            return message.sender.upper()  # TODO: use plugin id

        formatted_messages = [
            f"""
                <message>
                <created_at>
                    {message.created_at.strftime('%d %b %Y at %H:%M UTC')}
                </created_at>
                <sender>
                    {get_sender_name(message)}
                </sender>
                <content>
                    {message.text}
                </content>
                </message>
            """.replace('    ', '').replace('\n\n\n', '\n\n').strip()
            for message in sorted_messages
        ]

        return '\n'.join(formatted_messages)

    def is_message_with_file(self):
        return len(self.reference_files_id) > 0


class ResponseMessage(Message):
    ask_for_nps: Optional[bool] = False


class SendMessageRequest(BaseModel):
    text: str
    file_ids: Optional[List[str]] = []


