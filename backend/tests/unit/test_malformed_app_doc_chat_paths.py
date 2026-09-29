"""A malformed stored app doc must not 500 the chat send / initial-message / generate-reply paths.

Merged #19584 guarded the single app/persona fetches in `routers/apps.py` with a safe build (and
#19652 is doing the oauth caller), but the chat-facing callers still built `App(**record)` from the
raw Firestore document. One legacy/partial app record (missing `name`/`category`/`image`/…)
raised `ValidationError`:

- `POST /v2/messages` persisted the human turn and then 500'd before replying,
- `POST /v2/chat/generate-reply` 500'd for that app id,
- `POST /v2/initial-message` (and clear-chat) for that app 500'd.

`App.deserialize_safe` (`models/app.py`) returns `None` for an unbuildable record; these sites now
treat that as app-unavailable.
"""

import os
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

# Missing name/category/author/description/image/capabilities -> App(**record) raises ValidationError.
_MALFORMED_APP = {'id': 'corrupt_app'}


def test_initial_message_survives_a_malformed_app_doc(monkeypatch):
    monkeypatch.setattr(chat_util.chat_db, 'get_chat_session_by_id', lambda uid, sid: {'id': 'sess-1'})
    monkeypatch.setattr(chat_util.chat_db, 'get_messages', lambda *args, **kwargs: [])
    monkeypatch.setattr(chat_util.chat_db, 'add_message', MagicMock())
    monkeypatch.setattr(chat_util.chat_db, 'add_message_to_chat_session', MagicMock())
    monkeypatch.setattr(chat_util, 'get_available_app_by_id', lambda app_id, uid: dict(_MALFORMED_APP))
    monkeypatch.setattr(chat_util, 'initial_chat_message', lambda uid, app, history: 'reply')

    message = chat_util.initial_message_util('uid-1', chat_session_id='sess-1')

    assert isinstance(message, Message)
    assert message.text == 'reply'


def test_no_raw_app_splat_build_in_the_chat_paths():
    backend = Path(chat_util.__file__).resolve().parents[1]
    for relative in ('routers/chat.py', 'routers/chat_generation.py', 'utils/chat.py'):
        source = (backend / relative).read_text()

        assert 'App(**' not in source, f'raw App(**record) build reintroduced in {relative}'
