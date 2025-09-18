from datetime import datetime
from enum import Enum
from typing import List, Optional, Any

from pydantic import BaseModel, model_validator


class MessageSender(str, Enum):
    ai = 'ai'
    human = 'human'


class MessageType(str, Enum):
    text = 'text'
    day_summary = 'day_summary'


class MessageConversationStructured(BaseModel):
    title: str
    emoji: str


class MessageConversation(BaseModel):
    id: str
    structured: MessageConversationStructured
    created_at: datetime


class FileChat(BaseModel):
    id: str
    name: str
    thumbnail: Optional[str] = ""
    mime_type: str
    openai_file_id: str
    created_at: datetime
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
    app_id: Optional[str] = None
    # TODO: remove plugin_id after migration
    plugin_id: Optional[str] = None
    from_external_integration: bool = False
    type: MessageType
    memories_id: List[str] = []  # used in db
    memories: List[MessageConversation] = []  # used front facing
    reported: bool = False
    report_reason: Optional[str] = None
    files_id: List[str] = []
    files: List[FileChat] = []
    chat_session_id: Optional[str] = None
    data_protection_level: Optional[str] = None

    @model_validator(mode='before')
    @classmethod
    def _sync_app_and_plugin_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            app_id_val = data.get('app_id')
            plugin_id_val = data.get('plugin_id')

            if app_id_val is not None:
                data['plugin_id'] = app_id_val
            elif plugin_id_val is not None:
                data['app_id'] = plugin_id_val
        return data

    @staticmethod
    def get_messages_as_string(
        messages: List['Message'], use_user_name_if_available: bool = False, use_plugin_name_if_available: bool = False
    ) -> str:
        sorted_messages = sorted(messages, key=lambda m: m.created_at)

        def get_sender_name(message: Message) -> str:
            if message.sender == 'human':
                return 'User'
            # elif use_plugin_name_if_available and message.app_id is not None:
            #     plugin = next((p for p in plugins if p.id == message.app_id), None)
            #     if plugin:
            #         return plugin.name RESTORE ME
            return message.sender.upper()  # TODO: use app id

        formatted_messages = [
            f"({message.created_at.strftime('%d %b %Y at %H:%M UTC')}) {get_sender_name(message)}: {message.text}"
            for message in sorted_messages
        ]

        return '\n'.join(formatted_messages)

    @staticmethod
    def get_messages_as_xml(
        messages: List['Message'], use_user_name_if_available: bool = False, use_plugin_name_if_available: bool = False
    ) -> str:
        sorted_messages = sorted(messages, key=lambda m: m.created_at)

        def get_sender_name(message: Message) -> str:
            if message.sender == 'human':
                return 'User'
            # elif use_plugin_name_if_available and message.app_id is not None:
            #     plugin = next((p for p in plugins if p.id == message.app_id), None)
            #     if plugin:
            #         return plugin.name RESTORE ME
            return message.sender.upper()  # TODO: use app id

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
                {('<attachments>' + ''.join(f"<file>{file.name}</file>" for file in message.files) + '</attachments>') if message.files and len(message.files) > 0 else ''}
                </message>
            """.replace(
                '    ', ''
            )
            .replace('\n\n\n', '\n\n')
            .strip()
            for message in sorted_messages
        ]

        return '\n'.join(formatted_messages)


class ResponseMessage(Message):
    ask_for_nps: Optional[bool] = False


class SendMessageRequest(BaseModel):
    text: str
    file_ids: Optional[List[str]] = []


class ChatSession(BaseModel):
    id: str
    message_ids: Optional[List[str]] = []
    file_ids: Optional[List[str]] = []
    app_id: Optional[str] = None
    plugin_id: Optional[str] = None
    created_at: datetime

    @model_validator(mode='before')
    @classmethod
    def _sync_chat_session_app_and_plugin_ids(cls, data: Any) -> Any:
        if isinstance(data, dict):
            app_id_val = data.get('app_id')
            plugin_id_val = data.get('plugin_id')

            if app_id_val is not None:
                data['plugin_id'] = app_id_val
            elif plugin_id_val is not None:
                data['app_id'] = plugin_id_val
        return data

    def add_file_ids(self, new_file_ids: List[str]):
        if self.file_ids is None:
            self.file_ids = []
        for file_id in new_file_ids:
            if file_id not in self.file_ids:
                self.file_ids.append(file_id)

    def retrieve_new_file(self, file_ids) -> List:
        existing_files = set(self.file_ids or [])
        return list(set(file_ids) - existing_files)
