"""Chat sessions (v2) — response wire shapes.

Source of truth for the response schema of ``routers.chat_sessions``. The dict
shapes mirror what ``database.chat`` returns:

* Chat sessions (v2) carry ``title``, ``preview``, ``message_count``,
  ``starred`` and ``updated_at``. This is distinct from the legacy v1
  ``models.chat.ChatSession`` (``message_ids`` / ``file_ids`` /
  ``openai_thread_id``), so the v2 shape gets its own model.
* ``save_message`` returns a small ack-shaped dict (``id`` / ``created_at`` as
  an ISO string / ``session_id`` / ``created``), not a full ``Message``.

Collection: users/{uid}/chat_sessions and users/{uid}/messages.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


class ChatSessionResponse(BaseModel):
    """A v2 chat session (multi-session chat with title, preview, starring)."""

    id: str = Field(description='Unique chat session identifier.')
    title: str = Field(description='Display title of the session.')
    preview: Optional[str] = Field(default=None, description='Preview text of the latest message, if any.')
    created_at: datetime = Field(description='Session creation timestamp (UTC).')
    updated_at: datetime = Field(description='Last update timestamp (UTC).')
    app_id: Optional[str] = Field(default=None, description='App/plugin the session belongs to; null for main chat.')
    plugin_id: Optional[str] = Field(default=None, description='Mirrors app_id for cross-platform query compatibility.')
    message_count: int = Field(description='Number of messages in the session.')
    starred: bool = Field(description='Whether the user starred the session.')

    @model_validator(mode='before')
    @classmethod
    def _repair_legacy_session_shape(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        app_id_val = data.get('app_id')
        plugin_id_val = data.get('plugin_id')
        if app_id_val is not None:
            data['plugin_id'] = app_id_val
        elif plugin_id_val is not None:
            data['app_id'] = plugin_id_val

        if not data.get('title'):
            data['title'] = 'New Chat'
        if 'preview' not in data:
            data['preview'] = None
        if data.get('updated_at') is None and data.get('created_at') is not None:
            data['updated_at'] = data['created_at']
        if data.get('message_count') is None:
            data['message_count'] = len(data.get('message_ids') or [])
        if data.get('starred') is None:
            data['starred'] = False

        return data


class SaveMessageResponse(BaseModel):
    """Ack for ``POST /v2/desktop/messages``.

    ``created_at`` is an ISO-8601 string (the persistence layer calls
    ``datetime.isoformat()``), not a ``datetime``. ``created`` is False for
    idempotent retries of an existing ``client_message_id``.
    """

    id: str = Field(description='Message identifier (client_message_id or generated UUID).')
    created_at: str = Field(description='ISO-8601 creation timestamp of the message.')
    session_id: Optional[str] = Field(default=None, description='Chat session the message belongs to.')
    created: bool = Field(description='True if a new message was created; False for an idempotent retry.')


class DeleteMessagesResponse(BaseModel):
    """Ack for ``DELETE /v2/desktop/messages`` — carries the deleted count."""

    status: str = Field(description='Human-readable status message, e.g. "ok".')
    deleted_count: int = Field(description='Number of messages deleted.')


class InitialMessageResponse(BaseModel):
    """Response for ``POST /v2/chat/initial-message``."""

    message: str = Field(description='Generated greeting message text.')
    message_id: str = Field(description='Identifier of the generated message.')


class GenerateTitleResponse(BaseModel):
    """Response for ``POST /v2/chat/generate-title``."""

    title: str = Field(description='Generated session title.')
