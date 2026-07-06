from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime, timezone

from models.memories import MemoryCategory, MemoryDB

# Bounds for PersonaChatRequest.context / PersonaChatRequest.previous_messages.
# These mirror the server-side caps enforced in
# `routers/integration.persona_chat_via_integration` (20 turns, 8192 chars
# per turn, ~500 chars per recognized context key). Putting them at the
# Pydantic layer (P2 from cubic AI review) rejects oversized payloads at
# parse time instead of after a full JSON body has already been read into
# memory — defense against accidental 100MB bodies from a buggy client.
_PERSONA_CONTEXT_MAX_KEYS = 5
_PERSONA_CONTEXT_VALUE_MAX_CHARS = 200
_PERSONA_PREVIOUS_MESSAGES_MAX_ITEMS = 20
_PERSONA_PREVIOUS_MESSAGE_TEXT_MAX_CHARS = 8192


class ConversationTimestampRange(BaseModel):
    start: int
    end: int


class ScreenPipeCreateConversation(BaseModel):
    request_id: str
    source: str
    text: str
    timestamp_range: ConversationTimestampRange


class ExternalIntegrationMemorySource(str, Enum):
    email = "email"
    post = "social_post"
    other = "other"


class ExternalIntegrationMemory(BaseModel):
    content: str = Field(description="The content of the memory (fact)")
    tags: Optional[List[str]] = Field(description="Tags associated with the memory (fact)", default=None)
    source_id: Optional[str] = Field(description="External source object id for provenance", default=None)
    source_url: Optional[str] = Field(description="External source URL for provenance", default=None)
    artifact_ref: Optional[Dict[str, Any]] = Field(description="Source-specific provenance pointer", default=None)


class ExternalIntegrationCreateMemory(BaseModel):
    text: Optional[str] = Field(description="The original text from which the fact was extracted")
    text_source: ExternalIntegrationMemorySource = Field(
        description="The source of the text", default=ExternalIntegrationMemorySource.other
    )
    text_source_spec: Optional[str] = Field(description="Additional specification about the source", default=None)
    source_id: Optional[str] = Field(description="External source object id for the provided text", default=None)
    source_url: Optional[str] = Field(description="External source URL for the provided text", default=None)
    artifact_ref: Optional[Dict[str, Any]] = Field(
        description="Source-specific provenance pointer for the text", default=None
    )
    app_id: Optional[str] = None
    memories: Optional[List[ExternalIntegrationMemory]] = Field(
        description="List of explicit memories(facts) to be created", default=None
    )


class IntegrationNotificationResponse(BaseModel):
    status: str


class PersonaChatRequest(BaseModel):
    """Single-turn persona chat request from a 3rd-party integration (e.g. AI clone plugins).

    The optional `context` and `previous_messages` fields (added in T-020)
    let the plugin tell the persona who they're talking to and what was
    said in the recent turns. Without them, the LLM treats every inbound
    webhook as a fresh conversation and can't answer "who am I?" /
    "remind me about X" / "what did I just say?" in a way that's
    grounded in the actual chat history. Both fields are optional — the
    desktop persona chat (which has its own session continuity) still
    works without them, and the regular `text`-only path is unchanged.
    """

    # Telegram caps messages at 4096 chars; WhatsApp at ~65536; iMessage at
    # ~20000. We pick a conservative 8192 so the cap covers the largest
    # platform and the LLM has plenty of room to think.
    text: str = Field(
        description="The inbound message from the chat platform (1:1 DM, text only)", min_length=1, max_length=8192
    )

    context: Optional[dict] = Field(
        default=None,
        description=(
            "Free-form platform context (sender name, sender username, chat type, "
            "platform). Forwarded to the persona prompt as a SystemMessage so the "
            "persona knows who they're talking to. Recognized keys: sender_name "
            "(str), sender_username (str), chat_type ('private'|'group'), "
            "platform ('telegram'|'whatsapp'|'imessage'). Unknown keys are "
            "preserved verbatim — the renderer ignores them."
        ),
        max_length=_PERSONA_CONTEXT_MAX_KEYS,
    )

    previous_messages: Optional[List[dict]] = Field(
        default=None,
        description=(
            "Recent prior turns from the same chat, oldest first. Each entry is "
            "{'role': 'human'|'ai', 'text': '<message>'}. Inserted into the "
            "persona prompt as HumanMessage / AIMessage before the current "
            "'text' HumanMessage. Capped at 20 entries server-side; per-text "
            "length capped at 8192 to mirror the inbound text limit."
        ),
        max_length=_PERSONA_PREVIOUS_MESSAGES_MAX_ITEMS,
    )

    @field_validator('context')
    @classmethod
    def _cap_context_values(cls, v: Optional[dict]) -> Optional[dict]:
        # Pydantic's `max_length` checks the number of keys (Dict allows
        # arbitrary types). We additionally cap each value's serialized
        # length to keep an oversized sender_name etc. from filling
        # memory before the server re-truncates.
        if v is None:
            return v
        capped: dict = {}
        for k, val in v.items():
            if isinstance(val, str) and len(val) > _PERSONA_CONTEXT_VALUE_MAX_CHARS:
                capped[k] = val[:_PERSONA_CONTEXT_VALUE_MAX_CHARS]
            else:
                capped[k] = val
        return capped

    @field_validator('previous_messages')
    @classmethod
    def _cap_previous_message_text(cls, v: Optional[List[dict]]) -> Optional[List[dict]]:
        if v is None:
            return v
        # Mirror the server-side cap (text per turn) so a chatty buffer
        # doesn't blow the request body budget.
        capped: List[dict] = []
        for turn in v:
            if not isinstance(turn, dict):
                continue
            text = turn.get('text')
            if isinstance(text, str) and len(text) > _PERSONA_PREVIOUS_MESSAGE_TEXT_MAX_CHARS:
                turn = {**turn, 'text': text[:_PERSONA_PREVIOUS_MESSAGE_TEXT_MAX_CHARS]}
            capped.append(turn)
        return capped


class ConversationCreateResponse(BaseModel):
    status: str
    conversation_id: str


class MemoryItem(MemoryDB):
    """
    Memory item model that extends MemoryDB for API responses
    """

    model_config = ConfigDict(exclude_none=True)


class MemoriesResponse(BaseModel):
    memories: List[MemoryItem] = Field(description="List of user memories (facts)")


class ActionItem(BaseModel):
    description: str = Field(description="The action item to be completed")
    completed: bool = False
    exported: bool = False
    export_date: Optional[datetime] = None
    export_platform: Optional[str] = None


class Event(BaseModel):
    title: str = Field(description="The title of the event")
    description: str = Field(description="A brief description of the event", default='')
    start: datetime = Field(description="The start date and time of the event")
    duration: int = Field(description="The duration of the event in minutes", default=30)
    created: bool = False

    def as_dict_cleaned_dates(self):
        event_dict = self.model_dump()
        start_time = event_dict['start']
        if start_time.tzinfo is None:
            event_dict['start'] = start_time.isoformat() + 'Z'
        else:
            event_dict['start'] = start_time.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        return event_dict


class ConversationItemStructured(BaseModel):
    title: str
    overview: str
    emoji: str = "🧠"
    category: str = "other"
    action_items: List[ActionItem] = Field(default=[])
    events: List[Event] = Field(default=[])


class ConversationItemGeolocation(BaseModel):
    google_place_id: Optional[str] = None
    latitude: float
    longitude: float
    address: Optional[str] = None
    location_type: Optional[str] = None


class ConversationItemTranscriptSegment(BaseModel):
    text: str
    speaker: Optional[str] = None
    is_user: bool = False
    person_id: Optional[str] = None
    start: float = 0.0
    end: float = 0.0


class ConversationItem(BaseModel):
    id: str
    created_at: datetime
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    source: str
    structured: Optional[ConversationItemStructured] = None
    transcript_segments: Optional[List[ConversationItemTranscriptSegment]] = None
    discarded: Optional[bool] = False
    app_id: Optional[str] = None
    language: Optional[str] = None
    external_data: Optional[Dict] = None
    geolocation: Optional[ConversationItemGeolocation] = None
    status: Optional[str] = None

    @field_serializer('created_at', 'started_at', 'finished_at')
    def _serialize_dt(self, v: Optional[datetime]):
        if v is None:
            return None
        return (
            v.isoformat() + 'Z' if v.tzinfo is None else v.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        )


class ConversationsResponse(BaseModel):
    conversations: List[ConversationItem] = Field(description="List of user conversations")


class SearchConversationsResponse(BaseModel):
    conversations: List[ConversationItem] = Field(description="List of user conversations")
    total_pages: int = Field(description="Total number of pages")
    current_page: int = Field(description="Current page number")
    per_page: int = Field(description="Number of items per page")


class TaskItem(BaseModel):
    """Task (action item) model for API responses"""

    id: str
    description: str
    completed: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    conversation_id: Optional[str] = None

    @field_serializer('created_at', 'updated_at', 'due_at', 'completed_at')
    def _serialize_dt(self, v: Optional[datetime]):
        if v is None:
            return None
        return (
            v.isoformat() + 'Z' if v.tzinfo is None else v.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
        )


class TasksResponse(BaseModel):
    tasks: List[TaskItem] = Field(description="List of user tasks (action items)")
