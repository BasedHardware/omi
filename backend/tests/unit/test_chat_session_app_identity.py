"""A named chat session owns the app identity of the request that targets it.

Clients address a thread by id and are not required to restate which app it
belongs to. When the router derived the app id from the query string instead of
from the resolved session, three app-scoped operations ran against the wrong
app:

- `DELETE /v2/messages` filtered the message delete by `plugin_id == None`, so
  an app session's record was deleted while its messages survived;
- `GET /v2/messages` on an empty session created the greeting in the *current*
  app session rather than the selected one;
- `POST /v2/messages` ran the turn with no app, giving the wrong persona and
  storing the reply as main chat.

Seam: the router handlers are called directly with `chat_db`,
`initial_message_util` and the quota enforcer patched — no Firestore client and
no FastAPI app construction.
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import routers.chat as chat_router
import utils.chat_session_target as chat_target

APP_SESSION = {
    'id': 'sess-app',
    'app_id': 'app-9',
    'plugin_id': 'app-9',
    'created_at': datetime(2026, 8, 7, tzinfo=timezone.utc),
}


def _v2_clear_chat_messages():
    """The v1 handler reuses the module-level name, so reach the v2 one by route."""
    for route in chat_router.router.routes:
        if getattr(route, 'path', None) == '/v2/messages' and 'DELETE' in getattr(route, 'methods', set()):
            return route.endpoint
    raise AssertionError('DELETE /v2/messages route not registered')


@pytest.fixture
def sessions(monkeypatch):
    """Only the app session is addressable; the app's "current" session differs."""
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_chat_session_by_id',
        lambda uid, sid: dict(APP_SESSION) if sid == APP_SESSION['id'] else None,
    )
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_chat_session',
        lambda uid, app_id=None: {'id': 'sess-current', 'app_id': app_id, 'created_at': APP_SESSION['created_at']},
    )


def test_target_takes_its_app_identity_from_the_named_session(sessions):
    target = chat_target.resolve_chat_target('uid-1', None, 'sess-app')

    assert target.session_id == 'sess-app'
    assert target.app_id == 'app-9'


def test_target_without_a_named_session_keeps_the_requested_app(sessions):
    target = chat_target.resolve_chat_target('uid-1', 'app-9', None)

    assert target.session_id == 'sess-current'
    assert target.app_id == 'app-9'


def test_clearing_a_named_app_session_deletes_its_messages(monkeypatch, sessions):
    """The delete must be scoped by the session's app, not the query string's."""
    recorded = {}

    def _clear_chat(uid, app_id=None, chat_session_id=None):
        recorded['app_id'] = app_id
        recorded['chat_session_id'] = chat_session_id
        return None

    monkeypatch.setattr(chat_router.chat_db, 'clear_chat', _clear_chat)
    deleted = []
    monkeypatch.setattr(chat_router.chat_db, 'delete_chat_session', lambda uid, sid: deleted.append((uid, sid)))
    monkeypatch.setattr(chat_router, 'FileChatTool', lambda uid, sid: type('T', (), {'cleanup': lambda self: None})())
    monkeypatch.setattr(
        chat_router,
        'initial_message_util',
        lambda uid, app_id=None, chat_session_id=None: recorded.update(greeting_session_id=chat_session_id),
    )

    _v2_clear_chat_messages()(app_id=None, plugin_id=None, chat_session_id='sess-app', uid='uid-1')

    assert recorded['chat_session_id'] == 'sess-app'
    # `plugin_id == None` would match no message in an app session.
    assert recorded['app_id'] == 'app-9'
    assert recorded['greeting_session_id'] == 'sess-app'
    assert deleted == []


def test_reading_an_empty_named_session_greets_that_session(monkeypatch, sessions):
    recorded = {}

    monkeypatch.setattr(
        chat_router.chat_db,
        'get_messages',
        lambda uid, limit=100, offset=0, include_conversations=False, app_id=None, chat_session_id=None: [],
    )

    def _initial(uid, app_id=None, chat_session_id=None):
        recorded['app_id'] = app_id
        recorded['chat_session_id'] = chat_session_id
        return {'id': 'greeting'}

    monkeypatch.setattr(chat_router, 'initial_message_util', _initial)

    chat_router.get_messages(plugin_id=None, app_id=None, chat_session_id='sess-app', limit=100, offset=0, uid='uid-1')

    # Without the session id the greeting is written into the *current* session.
    assert recorded['chat_session_id'] == 'sess-app'
    assert recorded['app_id'] == 'app-9'


def test_reading_a_named_session_scopes_history_to_its_app(monkeypatch, sessions):
    recorded = {}

    def _get_messages(uid, limit=100, offset=0, include_conversations=False, app_id=None, chat_session_id=None):
        recorded['app_id'] = app_id
        recorded['chat_session_id'] = chat_session_id
        recorded['limit'] = limit
        recorded['offset'] = offset
        return [{'id': 'm1'}]

    monkeypatch.setattr(chat_router.chat_db, 'get_messages', _get_messages)

    chat_router.get_messages(plugin_id=None, app_id=None, chat_session_id='sess-app', limit=100, offset=0, uid='uid-1')

    assert recorded == {
        'app_id': 'app-9',
        'chat_session_id': 'sess-app',
        'limit': 100,
        'offset': 0,
    }


def test_over_quota_turn_in_a_named_session_carries_session_and_app(monkeypatch, sessions):
    """The canned turn joins the named session and is stored under its app."""
    added = []
    joined = []

    def _enforce(uid, platform=None):
        raise HTTPException(
            status_code=402,
            detail={'error': 'quota_exceeded', 'plan': 'Free', 'unit': 'questions', 'limit': 30},
        )

    monkeypatch.setattr(chat_router, 'enforce_chat_quota', _enforce)
    monkeypatch.setattr(chat_router.chat_db, 'add_message', lambda uid, msg: added.append(msg))
    monkeypatch.setattr(
        chat_router.chat_db,
        'add_message_to_chat_session',
        lambda uid, sid, mid: joined.append((sid, mid)),
    )

    from models.chat import SendMessageRequest

    chat_router.send_message(
        SendMessageRequest(text='hi'),
        plugin_id=None,
        app_id=None,
        chat_session_id='sess-app',
        uid='uid-1',
    )

    assert [m['app_id'] for m in added] == ['app-9', 'app-9']
    assert {sid for sid, _ in joined} == {'sess-app'}
    assert {mid for _, mid in joined} == {m['id'] for m in added}
