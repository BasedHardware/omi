"""Regression: an expired Firestore transaction must be restarted, not kill the caller.

`update_conversation_segments` (the live transcript write, run every ~0.6s) commits inside a
transaction. Firestore retires a transaction id mid-flight and rejects the commit with
`400 The referenced transaction has expired or is no longer valid`; the SDK's `@transactional`
only retries `Aborted`, so the `InvalidArgument` used to escape and tear the session down.

With WP2 the transaction runs through the storage port, so the expired-restart now lives in
`FirestoreDocumentStore.run_transaction` (which wraps `run_transactional`). This test drives that
adapter method directly with a fake Firestore client, preserving the exact regression at the layer
that now owns it. Nothing is written when the commit is rejected, so recovery is a fresh transaction.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest
from google.api_core.exceptions import InvalidArgument

from database.store.adapters.firestore import FirestoreDocumentStore

EXPIRED_MESSAGE = '400 The referenced transaction has expired or is no longer valid.'
CONV = 'users/uid-1/conversations/conversation-1'


class _FakeSnapshot:
    def __init__(self, data: Dict[str, Any] | None):
        self._data = data
        self.exists = data is not None
        self.id = 'conversation-1'

    def to_dict(self) -> Dict[str, Any] | None:
        return dict(self._data) if self._data is not None else None


class _FakeDocumentReference:
    def __init__(self, client: "_FakeFirestoreClient"):
        self._client = client

    def get(self, transaction=None) -> _FakeSnapshot:
        self._client.reads += 1
        return _FakeSnapshot(self._client.doc_data)


class _FakeTransaction:
    """Implements the surface `_Transactional.__call__` drives on a real transaction."""

    _max_attempts = 5
    _read_only = False

    def __init__(self, client: "_FakeFirestoreClient", index: int):
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

    def update(self, _doc_ref: Any, payload: Dict[str, Any]) -> None:
        self.payload = payload

    def _commit(self) -> None:
        if self._client.commit_errors:
            raise self._client.commit_errors.pop(0)
        self._client.commits.append(self.payload)


class _FakeFirestoreClient:
    def __init__(self, doc_data: Dict[str, Any] | None, commit_errors: List[BaseException] | None = None):
        self.doc_data = doc_data
        self.commit_errors = list(commit_errors or [])
        self.commits: List[Dict[str, Any] | None] = []
        self.transactions: List[_FakeTransaction] = []
        self.reads = 0
        self.doc_ref = _FakeDocumentReference(self)

    def document(self, _path: str) -> _FakeDocumentReference:
        return self.doc_ref

    def transaction(self) -> _FakeTransaction:
        transaction = _FakeTransaction(self, len(self.transactions))
        self.transactions.append(transaction)
        return transaction


def _run(client: _FakeFirestoreClient) -> bool:
    store = FirestoreDocumentStore(client=client)

    def _fn(tx) -> bool:
        snapshot = tx.get(CONV)
        if not snapshot.exists:
            return False
        tx.update(CONV, {'has_content': True})
        return True

    return store.run_transaction(_fn)


def test_expired_transaction_is_restarted_and_the_write_lands():
    client = _FakeFirestoreClient({'has_content': False}, [InvalidArgument(EXPIRED_MESSAGE)])

    assert _run(client) is True

    assert len(client.transactions) == 2, 'the retry must use a fresh transaction, not the retired id'
    assert client.transactions[0].rolled_back is True
    assert client.commits == [{'has_content': True}]


def test_expired_transaction_gives_up_after_the_attempt_budget():
    client = _FakeFirestoreClient({'has_content': False}, [InvalidArgument(EXPIRED_MESSAGE) for _ in range(3)])

    with pytest.raises(InvalidArgument):
        _run(client)

    assert len(client.transactions) == 3
    assert client.commits == []


def test_other_invalid_argument_failures_are_not_retried():
    too_large = InvalidArgument('400 The value of property transcript_segments is longer than 1048487 bytes.')
    client = _FakeFirestoreClient({'has_content': False}, [too_large])

    with pytest.raises(InvalidArgument):
        _run(client)

    assert len(client.transactions) == 1, 'only an expired transaction is recoverable by restarting'


def test_missing_document_still_reports_no_write():
    client = _FakeFirestoreClient(None)

    assert _run(client) is False
    assert client.commits == [None]
