import json
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator

# App display names are resolved by an injected callable, never by importing the database
# layer here: models/ must stay import-pure so a Pydantic module cannot drag the Firestore
# client into every import graph that touches a chat message.
AppNameResolver = Callable[[str], Optional[str]]


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

    def model_dump(self, **kwargs):
        exclude_fields = {'thumb_name'}
        return super().model_dump(exclude=exclude_fields, **kwargs)


class ChartDataPoint(BaseModel):
    label: str
    value: float


class ChartDataset(BaseModel):
    label: str
    data_points: List[ChartDataPoint]
    color: Optional[str] = None  # hex color, e.g. "#4CAF50"


class ChartData(BaseModel):
    chart_type: Literal['line', 'bar']
    title: str
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    datasets: List[ChartDataset]


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
    session_id: Optional[str] = None
    data_protection_level: Optional[str] = None
    langsmith_run_id: Optional[str] = None  # LangSmith run ID for feedback tracking
    prompt_name: Optional[str] = None  # LangSmith prompt name for versioning
    prompt_commit: Optional[str] = None  # LangSmith prompt commit/version for traceability
    rating: Optional[int] = None  # User feedback: 1 = thumbs up, -1 = thumbs down, None = no rating
    # Desktop journal compatibility fields. These are optional so the existing
    # message response remains readable by older clients while a new client can
    # reconcile the canonical turn identity and structured payload exactly.
    metadata: Optional[str] = None
    content_blocks: List[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            'Structured chat content blocks. New rows store these directly; '
            'legacy rows are projected from metadata.content_blocks.'
        ),
    )
    client_message_id: Optional[str] = None
    message_source: Optional[str] = None
    journal_revision: Optional[int] = None
    chart_data: Optional[Union[ChartData, dict]] = None  # Inline chart visualization data

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

            if 'content_blocks' not in data:
                metadata = data.get('metadata')
                if isinstance(metadata, str):
                    try:
                        legacy_blocks = json.loads(metadata).get('content_blocks')
                    except (AttributeError, TypeError, ValueError):
                        legacy_blocks = None
                    if isinstance(legacy_blocks, list):
                        data['content_blocks'] = legacy_blocks
        return data

    @classmethod
    def deserialize_many_safe(cls, records, on_error=None) -> List['Message']:
        """Build Message objects from raw stored records, skipping any that fail
        validation so one malformed or legacy chat message cannot 500 a whole history
        load. on_error(record, exception), when provided, is called for each skip."""
        parsed: List['Message'] = []
        for record in records:
            try:
                parsed.append(cls(**record))
            except Exception as exc:  # noqa: BLE001 - one bad record must not break the history
                if on_error is not None:
                    on_error(record, exc)
        return parsed

    @staticmethod
    def _resolve_sender_name(
        message: 'Message',
        *,
        use_plugin_name_if_available: bool,
        app_name_by_id: Dict[str, Optional[str]],
        app_name_resolver: Optional[AppNameResolver],
    ) -> str:
        if message.sender == 'human':
            return 'User'
        if use_plugin_name_if_available and app_name_resolver and message.app_id and message.app_id.strip():
            app_id = message.app_id.strip()
            if app_id not in app_name_by_id:
                name = app_name_resolver(app_id)
                app_name_by_id[app_id] = name.strip() if isinstance(name, str) and name.strip() else None
            resolved_name = app_name_by_id[app_id]
            if resolved_name:
                return resolved_name
        return message.sender.upper()

    @staticmethod
    def get_messages_as_string(
        messages: List['Message'],
        use_user_name_if_available: bool = False,
        use_plugin_name_if_available: bool = False,
        include_file_info: bool = False,
        app_name_resolver: Optional[AppNameResolver] = None,
    ) -> str:
        sorted_messages = sorted(messages, key=lambda m: m.created_at)
        app_name_by_id: Dict[str, Optional[str]] = {}

        formatted_messages = []
        for message in sorted_messages:
            sender_name = Message._resolve_sender_name(
                message,
                use_plugin_name_if_available=use_plugin_name_if_available,
                app_name_by_id=app_name_by_id,
                app_name_resolver=app_name_resolver,
            )
            msg_text = f"({message.created_at.strftime('%d %b %Y at %H:%M UTC')}) {sender_name}: {message.text}"

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
        app_name_resolver: Optional[AppNameResolver] = None,
    ) -> str:
        sorted_messages = sorted(messages, key=lambda m: m.created_at)
        app_name_by_id: Dict[str, Optional[str]] = {}

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
<sender>{Message._resolve_sender_name(message, use_plugin_name_if_available=use_plugin_name_if_available, app_name_by_id=app_name_by_id, app_name_resolver=app_name_resolver)}</sender>
<content>{message.text}</content>
{file_section}
</message>"""

            # Only strip the block's surrounding whitespace. The template above is flush-left, so a
            # .replace('    ', '') here would instead delete 4-space runs from message.text (code,
            # tables, aligned or pasted text), corrupting the history shown to the LLM.
            formatted_messages.append(msg.strip())

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


class GenerateReplyTurn(BaseModel):
    """A prior turn supplied by the caller purely as generation context."""

    text: str = Field(..., min_length=1, max_length=100000)
    sender: MessageSender


class GenerateReplyRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=100000)
    history: List[GenerateReplyTurn] = Field(default_factory=list, max_length=50)
    app_id: Optional[str] = Field(None, max_length=200)


class GenerateReplyResponse(BaseModel):
    text: str
    app_id: Optional[str] = None


class RateMessageRequest(BaseModel):
    rating: Optional[int] = None


class ShareChatMessagesRequest(BaseModel):
    message_ids: list[str] = []


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
