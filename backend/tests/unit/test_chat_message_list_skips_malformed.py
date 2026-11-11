"""The message-list routes must skip a malformed stored row, not 500 the whole page.

`GET /v2/messages` (`routers/chat.py`) and `GET /v2/desktop/messages` (`routers/chat_sessions.py`)
declare `response_model=List[Message]` but returned the raw rows from `chat_db.get_messages`.
FastAPI validates every row during serialization, so one legacy/partial message doc (missing or
out-of-enum `sender`/`type`, missing `text`) raised `ResponseValidationError` and the user's whole
history page 500s until that row ages out of the ordered window.

The list-endpoint fix #8239 was closed unmerged, and the desktop route never had one; both now
route through `Message.deserialize_many_safe` (#8882), the same helper the send path and
`utils/chat.py` use.
"""

import os
from types import SimpleNamespace

os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import routers.chat as chat_router
import routers.chat_sessions as sessions_router

_GOOD = {
    'id': 'good-1',
    'text': "what's the plan?",
    'created_at': '2026-01-01T00:00:00+00:00',
    'sender': 'human',
    'type': 'text',
}
# Missing text / created_at / sender / type -> Message(**record) raises ValidationError.
_MALFORMED = {'id': 'legacy-broken'}


def test_v2_messages_skips_malformed_rows(monkeypatch):
    monkeypatch.setattr(chat_router.chat_db, 'get_messages', lambda *args, **kwargs: [dict(_GOOD), dict(_MALFORMED)])
    monkeypatch.setattr(
        chat_router,
        'resolve_chat_target',
        lambda uid, app_id, session_id: SimpleNamespace(app_id=None, session_id=None),
    )

    messages = chat_router.get_messages(
        plugin_id=None, app_id=None, chat_session_id=None, limit=100, offset=0, uid='u1'
    )

    # Pre-fix this returned raw dicts (AttributeError here) and one bad row 500s the route in production.
    assert [m.id for m in messages] == ['good-1']


def test_v2_desktop_messages_skips_malformed_rows(monkeypatch):
    monkeypatch.setattr(
        sessions_router.chat_db, 'get_messages', lambda *args, **kwargs: [dict(_GOOD), dict(_MALFORMED)]
    )

    messages = sessions_router.get_messages(app_id=None, session_id=None, limit=100, offset=0, uid='u1')

    assert [m.id for m in messages] == ['good-1']
