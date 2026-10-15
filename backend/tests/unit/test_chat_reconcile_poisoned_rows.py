"""#20271 — a malformed stored message must not 500 the desktop reconcile page.

The fix routes the rows through Message.deserialize_many_safe with a
per-record logger, so a poisoned row is skipped and the client syncs past it
on the next page.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.chat as chat_db
from routers import chat_sessions as chat_sessions_router
from utils.other import endpoints as auth

UID = 'uid-reconcile'
VALID = {
    'id': 'm1',
    'text': 'hello',
    'created_at': '2026-10-14T00:00:00Z',
    'sender': 'human',
    'type': 'text',
}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(chat_sessions_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def test_poisoned_rows_are_dropped_not_500(client, monkeypatch):
    rows = [
        dict(VALID),
        {'id': 'm2'},  # missing required fields
        'not-a-dict',
        {'id': 'm3', 'created_at': 'garbage', 'sender': 'human', 'type': 'text', 'text': 'x' * 3},
    ]
    monkeypatch.setattr(chat_db, 'get_messages_reconcile_page', lambda *a, **k: (rows, 'cursor-2', True))
    response = client.get('/v2/desktop/messages/reconcile')
    assert response.status_code == 200
    body = response.json()
    ids = [m['id'] for m in body['messages']]
    assert ids == ['m1']  # the m3 row's Message() construction raises too (garbage datetime)
    assert body['next_cursor'] == 'cursor-2'
    assert body['has_more'] is True


def test_invalid_cursor_returns_400(client, monkeypatch):
    def raise_cursor(*a, **k):
        raise chat_db.MessageReconcileCursorError('bad')

    monkeypatch.setattr(chat_db, 'get_messages_reconcile_page', raise_cursor)
    assert client.get('/v2/desktop/messages/reconcile?cursor=x').status_code == 400


def test_all_valid_rows_pass_through(client, monkeypatch):
    rows = [dict(VALID, id='m1'), dict(VALID, id='m2')]
    monkeypatch.setattr(chat_db, 'get_messages_reconcile_page', lambda *a, **k: (rows, None, False))
    body = client.get('/v2/desktop/messages/reconcile').json()
    assert [m['id'] for m in body['messages']] == ['m1', 'm2']
    assert body['has_more'] is False
