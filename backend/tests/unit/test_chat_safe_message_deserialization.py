"""Tests for Message.deserialize_many_safe integration in utils.chat.

Verifies that malformed stored messages in chat history (missing required fields)
are skipped gracefully instead of raising a ValidationError and 500ing initial-message
or voice-message processing paths.
"""

import ast
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
os.environ.setdefault('PINECONE_API_KEY', 'test-pinecone-key-not-real')

import utils.chat as chat_utils
from models.chat import Message

_GOOD_MESSAGE_DICT = {
    'id': 'msg-good-1',
    'text': 'Hello world',
    'created_at': datetime(2025, 1, 1, tzinfo=timezone.utc),
    'sender': 'human',
    'type': 'text',
}

_MALFORMED_MESSAGE_DICT = {
    'id': 'msg-bad-1',
    # Missing required text, created_at, sender, type
}

_MOCK_SESSION_DICT = {
    'id': 'session-123',
    'created_at': datetime(2025, 1, 1, tzinfo=timezone.utc),
}


def test_initial_message_util_skips_malformed_messages(monkeypatch):
    monkeypatch.setattr(chat_utils.chat_db, 'get_chat_session_by_id', lambda uid, sid: {'id': sid, 'app_id': 'app-1'})
    monkeypatch.setattr(
        chat_utils.chat_db,
        'get_messages',
        lambda uid, limit=5, chat_session_id=None, app_id=None: [_GOOD_MESSAGE_DICT, _MALFORMED_MESSAGE_DICT],
    )
    monkeypatch.setattr(chat_utils, 'get_available_app_by_id', lambda app_id, uid: None)
    monkeypatch.setattr(chat_utils, 'initial_chat_message', lambda uid, app, history: 'Hello from AI')
    monkeypatch.setattr(chat_utils.chat_db, 'add_message', MagicMock())
    monkeypatch.setattr(chat_utils.chat_db, 'add_message_to_chat_session', MagicMock())
    monkeypatch.setattr(chat_utils, 'record_app_usage', MagicMock())

    result = chat_utils.initial_message_util('user-123', 'app-1', chat_session_id='session-456')

    assert result.text == 'Hello from AI'
    assert result.chat_session_id == 'session-456'


def test_process_voice_message_segment_skips_malformed_messages(monkeypatch):
    monkeypatch.setattr(chat_utils, '_validated_wav_is_silent', lambda path, provider=None: False)
    monkeypatch.setattr(chat_utils, '_prepare_voice_message_url', lambda path: 'https://example.com/voice.wav')
    monkeypatch.setattr(
        chat_utils,
        '_transcribe_voice_message_url',
        lambda url, path, language, detect_language=True: ('Hello segment', 'en'),
    )
    monkeypatch.setattr(chat_utils.chat_db, 'add_message', MagicMock())
    monkeypatch.setattr(chat_utils.chat_db, 'add_message_to_chat_session', MagicMock())
    monkeypatch.setattr(chat_utils.chat_db, 'get_chat_session', lambda uid, app_id=None: _MOCK_SESSION_DICT)
    monkeypatch.setattr(
        chat_utils.chat_db,
        'get_messages',
        lambda uid, limit=10: [_GOOD_MESSAGE_DICT, _MALFORMED_MESSAGE_DICT],
    )
    monkeypatch.setattr(chat_utils, 'send_chat_message_notification', MagicMock())

    captured_messages = []

    def mock_execute_graph_chat(uid, messages, app):
        captured_messages.extend(messages)
        return 'AI response to voice', False, []

    monkeypatch.setattr(chat_utils, 'execute_graph_chat', mock_execute_graph_chat)

    result = chat_utils.process_voice_message_segment('/tmp/fake.wav', 'user-123')

    assert len(result) == 2
    assert result[1]['text'] == 'AI response to voice'
    assert len(captured_messages) == 1
    assert captured_messages[0].id == 'msg-good-1'


@pytest.mark.asyncio
async def test_process_voice_message_segment_stream_skips_malformed_messages(monkeypatch):
    monkeypatch.setattr(chat_utils, '_validated_wav_is_silent', lambda path, provider=None: False)
    monkeypatch.setattr(chat_utils, '_prepare_voice_message_url', lambda path: 'https://example.com/voice.wav')
    monkeypatch.setattr(
        chat_utils,
        '_transcribe_voice_message_url',
        lambda url, path, language, detect_language=True: ('Hello stream', 'en'),
    )
    monkeypatch.setattr(
        chat_utils.chat_db,
        'get_messages',
        lambda uid, limit=10: [_GOOD_MESSAGE_DICT, _MALFORMED_MESSAGE_DICT],
    )
    monkeypatch.setattr(chat_utils, 'send_chat_message_notification', MagicMock())
    monkeypatch.setattr(chat_utils.chat_db, 'get_chat_session', lambda uid, app_id=None: _MOCK_SESSION_DICT)

    captured_messages = []

    async def mock_execute_graph_chat_stream(uid, messages, app, *args, **kwargs):
        captured_messages.extend(messages)
        yield 'AI streamed chunk'

    monkeypatch.setattr(chat_utils, 'execute_graph_chat_stream', mock_execute_graph_chat_stream)
    monkeypatch.setattr(chat_utils.chat_db, 'add_message', MagicMock())
    monkeypatch.setattr(chat_utils.chat_db, 'add_message_to_chat_session', MagicMock())
    monkeypatch.setattr(chat_utils, 'acquire_chat_session', lambda uid, app_id=None: {'id': 'session-123'})

    chunks = []
    async for chunk in chat_utils.process_voice_message_segment_stream('/tmp/fake.wav', 'user-123'):
        chunks.append(chunk)

    assert len(chunks) > 0
    assert len(captured_messages) == 1
    assert captured_messages[0].id == 'msg-good-1'


def test_utils_chat_has_no_raw_message_comprehension():
    tree = ast.parse(Path(chat_utils.__file__).read_text())
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ListComp)
        and isinstance(node.elt, ast.Call)
        and getattr(node.elt.func, 'id', None) == 'Message'
    ]

    assert offenders == [], f'raw Message(**record) comprehensions reintroduced at lines {offenders}'
