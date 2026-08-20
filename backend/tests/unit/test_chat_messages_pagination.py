"""GET /v2/messages pagination (limit/offset).

The DB layer already accepted limit/offset; the HTTP route hard-coded limit=100
and omitted offset. This pins the query params through to chat_db and ensures
empty later pages do not synthesize a greeting.
"""

from datetime import datetime, timezone

import routers.chat as chat_router


def test_get_messages_forwards_limit_and_offset(monkeypatch):
    recorded = {}

    monkeypatch.setattr(
        chat_router,
        'resolve_chat_target',
        lambda uid, app_id, chat_session_id: type(
            'Target',
            (),
            {'app_id': app_id, 'session_id': chat_session_id},
        )(),
    )

    def _get_messages(uid, limit=20, offset=0, include_conversations=False, app_id=None, chat_session_id=None):
        recorded.update(
            {
                'uid': uid,
                'limit': limit,
                'offset': offset,
                'include_conversations': include_conversations,
                'app_id': app_id,
                'chat_session_id': chat_session_id,
            }
        )
        return [{'id': 'm1', 'created_at': datetime(2026, 8, 20, tzinfo=timezone.utc)}]

    monkeypatch.setattr(chat_router.chat_db, 'get_messages', _get_messages)

    result = chat_router.get_messages(
        plugin_id=None,
        app_id='app-1',
        chat_session_id=None,
        limit=25,
        offset=50,
        uid='uid-1',
    )

    assert result == [{'id': 'm1', 'created_at': datetime(2026, 8, 20, tzinfo=timezone.utc)}]
    assert recorded == {
        'uid': 'uid-1',
        'limit': 25,
        'offset': 50,
        'include_conversations': True,
        'app_id': 'app-1',
        'chat_session_id': None,
    }


def test_get_messages_empty_later_page_does_not_create_greeting(monkeypatch):
    greeted = []

    monkeypatch.setattr(
        chat_router,
        'resolve_chat_target',
        lambda uid, app_id, chat_session_id: type(
            'Target',
            (),
            {'app_id': app_id, 'session_id': chat_session_id},
        )(),
    )
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_messages',
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        chat_router,
        'initial_message_util',
        lambda *args, **kwargs: greeted.append(True) or {'id': 'greeting'},
    )

    assert (
        chat_router.get_messages(
            plugin_id=None,
            app_id=None,
            chat_session_id=None,
            limit=100,
            offset=100,
            uid='uid-1',
        )
        == []
    )
    assert greeted == []


def test_get_messages_empty_first_page_still_creates_greeting(monkeypatch):
    monkeypatch.setattr(
        chat_router,
        'resolve_chat_target',
        lambda uid, app_id, chat_session_id: type(
            'Target',
            (),
            {'app_id': app_id, 'session_id': chat_session_id},
        )(),
    )
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_messages',
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(
        chat_router,
        'initial_message_util',
        lambda uid, app_id=None, chat_session_id=None: {'id': 'greeting', 'app_id': app_id},
    )

    assert chat_router.get_messages(
        plugin_id=None,
        app_id='app-1',
        chat_session_id=None,
        limit=100,
        offset=0,
        uid='uid-1',
    ) == [{'id': 'greeting', 'app_id': 'app-1'}]
