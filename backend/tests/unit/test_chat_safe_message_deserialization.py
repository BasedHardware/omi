"""One malformed stored chat message must not 500 the initial-message or voice paths.

`utils/chat.py` built chat history with `[Message(**msg) for msg in ...]` at four call sites:
`initial_message_util` (persona and standard branches), `process_voice_message_segment`, and
`process_voice_message_segment_stream`. One legacy or corrupt row selected by the last-N query
raised `ValidationError` and took the whole endpoint down until the row aged out of the window.

`Message.deserialize_many_safe` (#8882) is the shared safe-deserialize helper the repo already
routes the list (#8239), send (`routers/chat.py`) and proactive-notification
(`utils/app_integrations.py`, #9799) paths through; `utils/chat.py` was the last holder of the raw
comprehension. These tests pin the behavior (the bad row is skipped, the rest of the history is
used) and the source (the comprehension cannot come back).
"""

import ast
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)
os.environ.setdefault('OPENAI_API_KEY', 'test-openai-key-not-real')
os.environ.setdefault('PINECONE_API_KEY', 'test-pinecone-key-not-real')

import utils.chat as chat_util
from models.chat import Message

_GOOD = {
    'id': 'good-1',
    'text': "what's the plan?",
    'created_at': datetime(2026, 1, 1, tzinfo=timezone.utc),
    'sender': 'human',
    'type': 'text',
}
# Missing text / created_at / sender / type -> Message(**record) raises ValidationError.
_MALFORMED = {'id': 'legacy-broken'}


def test_malformed_stored_message_does_not_break_initial_message(monkeypatch, caplog):
    monkeypatch.setattr(chat_util.chat_db, 'get_chat_session_by_id', lambda uid, sid: {'id': 'sess-1'})
    monkeypatch.setattr(chat_util.chat_db, 'get_messages', lambda *args, **kwargs: [dict(_GOOD), dict(_MALFORMED)])
    monkeypatch.setattr(chat_util.chat_db, 'add_message', MagicMock())
    monkeypatch.setattr(chat_util.chat_db, 'add_message_to_chat_session', MagicMock())
    monkeypatch.setattr(chat_util, 'get_available_app_by_id', lambda app_id, uid: None)
    captured = {}

    def fake_initial_message(uid, app, history):
        captured['history'] = history
        return 'reply'

    monkeypatch.setattr(chat_util, 'initial_chat_message', fake_initial_message)

    with caplog.at_level(logging.WARNING):
        message = chat_util.initial_message_util('uid-1', chat_session_id='sess-1')

    assert isinstance(message, Message)
    assert message.text == 'reply'
    # The valid row reached the prompt; the malformed one was skipped, with a warning.
    assert isinstance(captured['history'], str) and "what's the plan?" in captured['history']
    assert 'legacy-broken' in caplog.text


def test_utils_chat_has_no_raw_message_comprehension():
    tree = ast.parse(Path(chat_util.__file__).read_text())
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.ListComp)
        and isinstance(node.elt, ast.Call)
        and getattr(node.elt.func, 'id', None) == 'Message'
    ]

    assert offenders == [], f'raw Message(**record) comprehensions reintroduced at lines {offenders}'
