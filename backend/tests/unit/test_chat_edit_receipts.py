"""Shared receipt wire and owner-scoped undo contract."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import chat_receipts
from utils.other import endpoints as auth

from models.chat import EditReceiptBlock, UndoChatReceiptResponse
from utils.messaging.undo import UndoStore, edit_receipt_block
from utils.messaging import undo


def test_receipt_wire_contract():
    block = edit_receipt_block(
        'a' * 32, 'conversation', 'id', {'structured': {'title': 'old'}}, {'structured': {'title': 'new'}}
    )
    assert block == dict(
        type='editReceipt',
        id='a' * 32,
        receiptId='a' * 32,
        targetKind='conversation',
        action='updated',
        targetId='id',
        summary='new',
        undoable=True,
        undoneAt=None,
    )
    stamp = datetime.now(timezone.utc)
    response = UndoChatReceiptResponse(
        status='already_undone', block=EditReceiptBlock(**dict(block, undoneAt=stamp, undoable=False))
    )
    assert response.model_dump(mode='json')['block']['undoneAt']


def test_owner_lookup_never_searches_other_users():
    seen = []

    class Ref:
        def collection(self, name):
            seen.append(name)
            return self

        def document(self, name):
            seen.append(name)
            return self

        def get(self):
            return SimpleNamespace(to_dict=lambda: None)

    store = SimpleNamespace(user=lambda uid: (seen.append(uid) or Ref()))
    with pytest.raises(LookupError):
        UndoStore(store).undo_for_owner('owner', 'a' * 32)
    assert seen == ['owner', 'chat_receipts', 'a' * 32]


def test_owner_undo_returns_updated_block(monkeypatch):
    block = edit_receipt_block('a' * 32, 'task', 'id', {}, {'description': 'Task'})
    stamp = datetime.now(timezone.utc)

    class Ref:
        def collection(self, name):
            return self

        def document(self, name):
            return self

        def get(self):
            return SimpleNamespace(to_dict=lambda: {'session_id': 'session'})

    store = UndoStore(SimpleNamespace(user=lambda uid: Ref()))
    monkeypatch.setattr(
        store,
        'ref',
        lambda *args: SimpleNamespace(
            get=lambda: SimpleNamespace(
                to_dict=lambda: {'presentation': 'encrypted', 'state': 'done', 'undone_at': stamp}
            )
        ),
    )
    monkeypatch.setattr(undo.encryption, 'decrypt', lambda *args: __import__('json').dumps({'block': block}))
    monkeypatch.setattr(store, 'undo', lambda *args: SimpleNamespace(status='already_undone'))
    response = store.undo_for_owner('owner', 'a' * 32)
    assert response.status == 'already_undone'
    assert response.block.undoneAt == stamp
    assert not response.block.undoable


def test_authenticated_http_undo_endpoint(monkeypatch):

    app = FastAPI()
    app.include_router(chat_receipts.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'owner'
    block = EditReceiptBlock(**edit_receipt_block('a' * 32, 'conversation', 'id', {}, {'structured': {'title': 'new'}}))
    calls = []

    class Manager:
        def undo_for_owner(self, uid, receipt_id):
            calls.append((uid, receipt_id))
            if receipt_id == 'b' * 32:
                raise LookupError('missing')
            return UndoChatReceiptResponse(
                status='already_undone' if len(calls) > 1 else 'undone',
                block=block.model_copy(update={'undoable': False, 'undoneAt': datetime.now(timezone.utc)}),
            )

    monkeypatch.setattr(chat_receipts, 'UndoStore', Manager)
    client = TestClient(app)
    assert client.post('/v1/chat/receipts/' + 'a' * 32 + '/undo').json()['status'] == 'undone'
    assert client.post('/v1/chat/receipts/' + 'a' * 32 + '/undo').json()['status'] == 'already_undone'
    assert client.post('/v1/chat/receipts/' + 'b' * 32 + '/undo').status_code == 404
    assert client.post('/v1/chat/receipts/invalid/undo').status_code == 404
    assert all(uid == 'owner' for uid, _ in calls)
