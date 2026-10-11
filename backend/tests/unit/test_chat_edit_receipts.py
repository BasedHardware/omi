"""Shared receipt wire and owner-scoped undo contract."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

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
