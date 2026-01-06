from datetime import datetime
from enum import Enum
from typing import Any, List, Literal, Optional

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
        messages: List['Message'],
        use_user_name_if_available: bool = False,
        use_plugin_name_if_available: bool = False,
        include_file_info: bool = False,
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

        formatted_messages = []
        for message in sorted_messages:
            msg_text = (
                f"({message.created_at.strftime('%d %b %Y at %H:%M UTC')}) {get_sender_name(message)}: {message.text}"
            )

            # Add file info if requested and files exist
            if include_file_info and message.files_id and len(message.files_id) > 0:
                file_info = f" [Files attached: {len(message.files_id)} file(s), IDs: {', '.join(message.files_id)}]"
                msg_text += file_info

            formatted_messages.append(msg_text)

        return '\n'.join(formatted_messages)

    @staticmethod
    def get_messages_as_xml(
        messages: List['Message'],
        use_user_name_if_available: bool = False,
        use_plugin_name_if_available: bool = False,
        include_file_info: bool = False,
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

        formatted_messages = []
        for message in sorted_messages:
            # Build file section if requested
            file_section = ""
            if include_file_info and message.files and len(message.files) > 0:
                file_section = '<attachments>\n'
                for file in message.files:
                    file_section += f'  <file id="{file.id}" name="{file.name}" type="{file.mime_type}"/>\n'
                file_section += '</attachments>'
            elif include_file_info and message.files_id and len(message.files_id) > 0:
                # Fallback if files not loaded but IDs exist
                file_section = '<attachments>\n'
                for file_id in message.files_id:
                    file_section += f'  <file id="{file_id}"/>\n'
                file_section += '</attachments>'
            elif message.files and len(message.files) > 0:
                # Original behavior when include_file_info is False
                file_section = (
                    '<attachments>' + ''.join(f"<file>{file.name}</file>" for file in message.files) + '</attachments>'
                )

            msg = f"""<message>
<created_at>{message.created_at.strftime('%d %b %Y at %H:%M UTC')}</created_at>
<sender>{get_sender_name(message)}</sender>
<content>{message.text}</content>
{file_section}
</message>"""

            formatted_messages.append(msg.replace('    ', '').strip())

        return '\n'.join(formatted_messages)


class ResponseMessage(Message):
    ask_for_nps: Optional[bool] = False


class PageContext(BaseModel):
    """Page context for chat - indicates what the user is currently viewing."""

    type: Literal["conversation", "task", "memory", "recap"]
    id: Optional[str] = None
    title: Optional[str] = None


class SendMessageRequest(BaseModel):
    text: str
    file_ids: Optional[List[str]] = []
    context: Optional[PageContext] = None


class ChatSession(BaseModel):
    id: str
    message_ids: Optional[List[str]] = []
    file_ids: Optional[List[str]] = []
    app_id: Optional[str] = None
    plugin_id: Optional[str] = None
    created_at: datetime
    openai_thread_id: Optional[str] = None
    openai_assistant_id: Optional[str] = None

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
