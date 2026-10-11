"""An expired Firestore transaction must not drop a conversation persist.

Firestore retires transaction ids under load. The commit then dies with
``InvalidArgument: 400 The referenced transaction has expired or is no longer
valid``, and ``@firestore.transactional`` does not retry that error. Nothing was
written, so ``run_transactional`` restarts the persist on a fresh transaction.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from google.api_core.exceptions import InvalidArgument

from database import conversations as conversations_db

EXPIRED_MESSAGE = '400 The referenced transaction has expired or is no longer valid.'


class _FakeSnapshot:
    def __init__(self, data: Dict[str, Any] | None):
        self._data = data
        self.exists = data is not None

    def to_dict(self) -> Dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class _FakeDocumentReference:
    def __init__(self, client: '_FakeFirestoreClient'):
        self._client = client

    def get(self, transaction=None) -> _FakeSnapshot:
        return _FakeSnapshot(self._client.document)

    def collection(self, _collection_id: str) -> '_FakeCollectionReference':
        return _FakeCollectionReference(self._client)


class _FakeCollectionReference:
    def __init__(self, client: '_FakeFirestoreClient'):
        self._client = client

    def document(self, _document_id: str) -> Any:
        return self._client.doc_ref

    def collection(self, _collection_id: str) -> '_FakeCollectionReference':
        return self


class _FakeTransaction:
    """Surface ``_Transactional.__call__`` drives on a real transaction."""

    _max_attempts = 5
    _read_only = False

    def __init__(self, client: '_FakeFirestoreClient', index: int):
        self._client = client
        self._id = f'txn-{index}'.encode()
        self.payload: Dict[str, Any] | None = None
        self.rolled_back = False

    def _clean_up(self) -> None:
        pass

    def _begin(self, retry_id=None) -> None:
        pass

    def _rollback(self) -> None:
        self.rolled_back = True

    def set(self, _doc_ref: Any, payload: Dict[str, Any], merge: bool = False) -> None:
        self.payload = payload

    def _commit(self) -> None:
        if self._client.commit_errors:
            raise self._client.commit_errors.pop(0)
        self._client.commits.append(self.payload)


class _FakeFirestoreClient:
    def __init__(self, document: Dict[str, Any] | None, commit_errors: List[BaseException] | None = None):
        self.document = document
        self.commit_errors = list(commit_errors or [])
        self.commits: List[Dict[str, Any] | None] = []
        self.transactions: List[_FakeTransaction] = []
        self.doc_ref = _FakeDocumentReference(self)

    def collection(self, _collection_id: str) -> _FakeCollectionReference:
        return _FakeCollectionReference(self)

    def transaction(self) -> _FakeTransaction:
        transaction = _FakeTransaction(self, len(self.transactions))
        self.transactions.append(transaction)
        return transaction


def test_expired_transaction_retries_and_persist_processing_result_lands(monkeypatch: pytest.MonkeyPatch):
    client = _FakeFirestoreClient(
        {'status': 'processing', 'data_protection_level': 'standard'},
        [InvalidArgument(EXPIRED_MESSAGE)],
    )
    monkeypatch.setattr(conversations_db, 'db', client)
    monkeypatch.setattr(conversations_db, 'invalidate_people_stats_cache', lambda _uid: None)

    persisted = conversations_db.persist_processing_result_with_lifecycle(
        'uid-1',
        {
            'id': 'conversation-1',
            'status': 'completed',
            'data_protection_level': 'standard',
            'structured': {'title': 'Recovered'},
        },
    )

    assert persisted is True
    assert len(client.transactions) == 2, 'the retry must use a fresh transaction, not the retired id'
    assert client.transactions[0].rolled_back is True
    assert len(client.commits) == 1
    written = client.commits[0]
    assert written is not None
    assert written['id'] == 'conversation-1'
    assert written['status'] == 'completed'
    assert written['structured']['title'] == 'Recovered'
