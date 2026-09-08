"""A chat request must be able to name the session it targets.

`/v2/messages` (send, read, clear) resolved the session server-side with
`chat_db.get_chat_session(uid, app_id)` and exposed no way to say which session
the caller meant. A client with more than one session per app therefore could
not read an older thread or continue it — every write landed in whichever
session the resolver happened to return.

That resolver made it worse: its Firestore query was `.limit(1)` with no
`order_by`, so "the current session" was whichever document the index yielded.
Creating a second session via `/v2/chat-sessions` could silently move the
conversation.

Seam: `utils.chat_session_target.resolve_chat_session` and `database.chat.get_chat_session`
are exercised directly with patched collaborators — no Firestore client and no
FastAPI app construction.
"""

from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

import routers.chat as chat_router
import utils.chat_session_target as chat_target


class _FakeQuery:
    """Records the query chain so the test can assert what the query did."""

    def __init__(self, recorder, docs):
        self._recorder = recorder
        self._docs = docs

    def where(self, filter=None):  # noqa: A002 - mirrors the Firestore signature
        self._recorder['where'] = filter
        return self

    def order_by(self, field, direction=None):
        self._recorder['order_by'] = (field, direction)
        return self

    def limit(self, n):
        self._recorder['limit'] = n
        return self

    def stream(self):
        return iter(self._docs)


def test_explicit_session_id_is_used_instead_of_the_current_session(monkeypatch):
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_chat_session_by_id',
        lambda uid, sid: {'id': sid, 'plugin_id': None},
    )
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_chat_session',
        lambda uid, app_id=None: {'id': 'current-session'},
    )

    resolved = chat_target.resolve_chat_session('uid-1', None, 'older-session')

    assert resolved['id'] == 'older-session'


def test_unknown_session_id_fails_instead_of_falling_back(monkeypatch):
    """A silent fallback would write the message into a different conversation."""
    monkeypatch.setattr(chat_router.chat_db, 'get_chat_session_by_id', lambda uid, sid: None)
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_chat_session',
        lambda uid, app_id=None: {'id': 'current-session'},
    )

    with pytest.raises(HTTPException) as excinfo:
        chat_target.resolve_chat_session('uid-1', None, 'does-not-exist')

    assert excinfo.value.status_code == 404


def test_a_foreign_session_id_cannot_be_targeted(monkeypatch):
    """`get_chat_session_by_id` is uid-scoped, so another user's id resolves to None."""
    store = {('uid-1', 'sess-a'): {'id': 'sess-a'}}
    monkeypatch.setattr(
        chat_router.chat_db,
        'get_chat_session_by_id',
        lambda uid, sid: store.get((uid, sid)),
    )
    monkeypatch.setattr(chat_router.chat_db, 'get_chat_session', lambda uid, app_id=None: None)

    with pytest.raises(HTTPException) as excinfo:
        chat_target.resolve_chat_session('uid-2', None, 'sess-a')

    assert excinfo.value.status_code == 404


def test_without_an_id_the_current_session_is_used(monkeypatch):
    """Released clients send no session id; their behaviour must not change."""
    seen = {}

    def _current(uid, app_id=None):
        seen['app_id'] = app_id
        return {'id': 'current-session'}

    monkeypatch.setattr(chat_router.chat_db, 'get_chat_session', _current)

    resolved = chat_target.resolve_chat_session('uid-1', 'app-9', None)

    assert resolved['id'] == 'current-session'
    assert seen['app_id'] == 'app-9'


def test_blank_session_id_is_treated_as_absent(monkeypatch):
    monkeypatch.setattr(chat_router.chat_db, 'get_chat_session', lambda uid, app_id=None: {'id': 'current-session'})

    assert chat_target.resolve_chat_session('uid-1', None, '')['id'] == 'current-session'


def test_current_session_resolves_to_the_newest(monkeypatch):
    """The newest timestamped session is selected by the ordered query.

    The fallback query still handles legacy sessions without `created_at`.
    """
    import database.chat as chat_db

    recorder = {}

    class _Doc:
        def __init__(self, session_id, created_at):
            self.id = session_id
            self._data = {'id': session_id, 'created_at': created_at}

        def to_dict(self):
            return self._data

    docs = [
        _Doc('sess-older', datetime(2026, 8, 5, tzinfo=timezone.utc)),
        _Doc('sess-newest', datetime(2026, 8, 7, tzinfo=timezone.utc)),
        _Doc('sess-middle', datetime(2026, 8, 6, tzinfo=timezone.utc)),
    ]

    class _Collection:
        def where(self, filter=None):  # noqa: A002
            return _FakeQuery(recorder, docs).where(filter=filter)

    class _Document:
        def collection(self, name):
            return _Collection()

    class _Db:
        def collection(self, name):
            return _Root()

    class _Root:
        def document(self, uid):
            return _Document()

    # Replace the client outright: touching the real one reaches the metadata
    # server, which the hermetic-network guard blocks.
    monkeypatch.setattr(chat_db, 'db', _Db())
    monkeypatch.setattr(chat_db, '_typed_doc', lambda doc: doc.to_dict())

    result = chat_db.get_chat_session('uid-1', app_id=None)

    assert result['id'] == 'sess-newest'
    assert recorder['order_by'][0] == '__name__'
    assert recorder['limit'] == 1
