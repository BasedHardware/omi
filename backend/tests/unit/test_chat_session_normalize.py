"""Regression test for GET /v2/chat-sessions ResponseValidationError (issue #9099).

Commit e22938ac7 added a strict ``response_model=list[ChatSessionResponse]`` to
the previously-untyped list endpoint. Firestore holds session docs written by
several code paths (Python v2, Rust desktop backend, legacy), and some rows lack
fields the model marks required (``title``, ``created_at``, ``message_count``,
``starred``) — which made FastAPI raise ResponseValidationError (HTTP 500).

``_normalize_chat_session`` fills safe defaults so those rows validate.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

from database import chat as chat_db
from database.chat import _normalize_chat_session, get_chat_session_by_id
from models.chat_session import ChatSessionResponse


def test_normalize_none_passthrough():
    assert _normalize_chat_session(None) is None


def test_normalize_fills_missing_required_fields_and_validates():
    # A doc as returned by the list query: only id + updated_at + plugin_id are
    # guaranteed present; title/created_at/message_count/starred are missing.
    now = datetime.now(timezone.utc)
    raw = {'id': 'sess-1', 'updated_at': now, 'plugin_id': None}

    normalized = _normalize_chat_session(raw)

    assert normalized['title'] == 'New Chat'
    assert normalized['message_count'] == 0
    assert normalized['starred'] is False
    assert normalized['created_at'] == now  # falls back to updated_at

    # The previously-failing step: strict response_model validation must pass.
    ChatSessionResponse.model_validate(normalized)


def test_normalize_fills_missing_timestamps_with_utc_now():
    raw = {'id': 'sess-legacy', 'plugin_id': None}

    normalized = _normalize_chat_session(raw)

    assert normalized['created_at'] is not None
    assert normalized['updated_at'] is not None
    assert normalized['created_at'] == normalized['updated_at']
    ChatSessionResponse.model_validate(normalized)


def test_get_chat_session_by_id_injects_document_id(monkeypatch):
    session_id = 'doc-key-123'
    now = datetime.now(timezone.utc)
    session_data = {'updated_at': now, 'plugin_id': None}

    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = session_data

    mock_session_ref = MagicMock()
    mock_session_ref.get.return_value = mock_doc

    mock_sessions_col = MagicMock()
    mock_sessions_col.document.return_value = mock_session_ref

    mock_user_ref = MagicMock()
    mock_user_ref.collection.return_value = mock_sessions_col

    mock_users_col = MagicMock()
    mock_users_col.document.return_value = mock_user_ref

    monkeypatch.setattr(chat_db, 'db', MagicMock(collection=MagicMock(return_value=mock_users_col)))

    result = get_chat_session_by_id('uid-1', session_id)

    assert result['id'] == session_id
    ChatSessionResponse.model_validate(result)


def test_normalize_preserves_existing_values():
    now = datetime.now(timezone.utc)
    raw = {
        'id': 'sess-2',
        'title': 'My chat',
        'preview': 'hello',
        'created_at': now,
        'updated_at': now,
        'message_count': 7,
        'starred': True,
    }

    normalized = _normalize_chat_session(raw)

    assert normalized['title'] == 'My chat'
    assert normalized['message_count'] == 7
    assert normalized['starred'] is True
    ChatSessionResponse.model_validate(normalized)
