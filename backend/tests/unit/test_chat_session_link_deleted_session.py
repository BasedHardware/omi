"""Chat writes must survive a chat session deleted while they were in flight.

Prod signature (2026-08-20T00:49:53Z, image 920fc55): DELETE /v2/messages returned
500 after 31.5s from
database/chat.py:add_message_to_chat_session ->
`google.api_core.exceptions.NotFound: 404 No document to update:
.../users/<uid>/chat_sessions/78489909-...`.

The race is the endpoint's own latency. clear_chat_messages reads the session,
deletes it, then calls initial_message_util, which acquires/creates a session and
spends the whole LLM round trip (10-80s in prod on this route) generating the
greeting before linking the new ai message back onto the session document. A second
clear -- a double tap, or a client retrying a request that already looked hung --
lands inside that window: it deletes the session the first call is still holding, so
the first call's link write hits a tombstone. The user's clear then 500s even though
the clear itself, and the message write it was reporting, both succeeded.

The message/file/OpenAI-id lists are derived state the session document owns; a
session that no longer exists has nothing to record. This mirrors the guard
database/folders.py:update_folder_conversation_count already carries for the same
failure class (see test_folder_move_deleted_folder).

The fake below models the one server behavior that matters: update() on a missing
document raises NotFound. test_fake_update_on_missing_session_raises is the control
that keeps that true, so the other cases prove the guard rather than a lenient fake.
"""

import os

import pytest
from google.api_core.exceptions import NotFound
from unittest.mock import patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)

import database.chat as chat_db

UID = 'u1'
SESSION_ID = '78489909-6ff7-41de-b292-0fedd332e1ba'


class _FakeDocRef:
    def __init__(self, store, doc_id):
        self._store = store
        self.id = doc_id

    def update(self, values):
        if self.id not in self._store:
            raise NotFound(f"404 No document to update: {self.id}")
        self._store[self.id].update(values)

    def delete(self):
        self._store.pop(self.id, None)


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, doc_id):
        return _FakeDocRef(self._store, doc_id)


class _FakeUserRef:
    def __init__(self, store):
        self._store = store

    def collection(self, name):
        assert name == 'chat_sessions'
        return _FakeCollection(self._store)


class _FakeDb:
    def __init__(self, store):
        self._store = store

    def collection(self, name):
        assert name == 'users'
        return self

    def document(self, _uid):
        return _FakeUserRef(self._store)


@pytest.fixture
def live_session():
    """A session store holding one session, patched in as database.chat's Firestore client."""
    store = {SESSION_ID: {'id': SESSION_ID}}
    with patch.object(chat_db, 'db', _FakeDb(store)):
        yield store


def _delete(store):
    """The concurrent clear: the session is gone by the time the in-flight write lands."""
    store.pop(SESSION_ID, None)


def test_fake_update_on_missing_session_raises(live_session):
    # Control: without the guard these writes propagate NotFound, which is the 500.
    _delete(live_session)
    with pytest.raises(NotFound):
        _FakeDb(live_session).collection('users').document(UID).collection('chat_sessions').document(SESSION_ID).update(
            {'message_ids': ['m1']}
        )


def test_add_message_links_message_onto_live_session(live_session):
    chat_db.add_message_to_chat_session(UID, SESSION_ID, 'm1')
    assert 'message_ids' in live_session[SESSION_ID]


def test_add_message_to_deleted_session_does_not_raise(live_session):
    _delete(live_session)
    assert chat_db.add_message_to_chat_session(UID, SESSION_ID, 'm1') is None
    assert SESSION_ID not in live_session


def test_add_files_to_deleted_session_does_not_raise(live_session):
    _delete(live_session)
    assert chat_db.add_files_to_chat_session(UID, SESSION_ID, ['f1']) is None


def test_add_files_still_links_onto_live_session(live_session):
    chat_db.add_files_to_chat_session(UID, SESSION_ID, ['f1'])
    assert 'file_ids' in live_session[SESSION_ID]
