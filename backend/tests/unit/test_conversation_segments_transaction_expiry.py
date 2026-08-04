"""Regression test: an expired Firestore transaction must not kill a live listen session.

`update_conversation_segments` is the live transcript write, run every ~0.6s by the
`stream_transcript` loop. Firestore retires a transaction id mid-flight and rejects the
commit with `400 The referenced transaction has expired or is no longer valid`; the SDK's
`@firestore.transactional` only retries `Aborted`, so the `InvalidArgument` escaped into
the WebSocket task, which the supervisor classifies as a crash and tears the session down.
Prod saw ~26 of these a day across 18 users — each one ending someone's recording.

Nothing is written when the commit is rejected, so the recovery is a brand-new transaction.
"""

from __future__ import annotations

import json
import zlib
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
    def __init__(self, client: "_FakeFirestoreClient"):
        self._client = client

    def get(self, transaction=None) -> _FakeSnapshot:
        self._client.reads += 1
        return _FakeSnapshot(self._client.document)

    def collection(self, _collection_id: str) -> "_FakeCollectionReference":
        return _FakeCollectionReference(self._client)


class _FakeCollectionReference:
    def __init__(self, client: "_FakeFirestoreClient"):
        self._client = client

    def document(self, _document_id: str) -> Any:
        return self._client.doc_ref

    def collection(self, _collection_id: str) -> "_FakeCollectionReference":
        return self


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
    def __init__(self, document: Dict[str, Any] | None, commit_errors: List[BaseException] | None = None):
        self.document = document
        self.commit_errors = list(commit_errors or [])
        self.commits: List[Dict[str, Any] | None] = []
        self.transactions: List[_FakeTransaction] = []
        self.reads = 0
        self.doc_ref = _FakeDocumentReference(self)

    def collection(self, _collection_id: str) -> _FakeCollectionReference:
        return _FakeCollectionReference(self)

    def transaction(self) -> _FakeTransaction:
        transaction = _FakeTransaction(self, len(self.transactions))
        self.transactions.append(transaction)
        return transaction


def _stored_segments(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    assert payload['transcript_segments_compressed'] is True
    return json.loads(zlib.decompress(payload['transcript_segments']).decode('utf-8'))


SEGMENTS = [{'id': 'seg-1', 'text': 'hello', 'start': 0.0, 'end': 1.0}]


def _write(client: _FakeFirestoreClient) -> bool:
    return conversations_db.update_conversation_segments(
        'uid-1',
        'conversation-1',
        SEGMENTS,
        data_protection_level='standard',
        firestore_client=client,
    )


def test_expired_transaction_is_restarted_and_the_segments_land():
    client = _FakeFirestoreClient({'has_content': False}, [InvalidArgument(EXPIRED_MESSAGE)])

    assert _write(client) is True

    assert len(client.transactions) == 2, 'the retry must use a fresh transaction, not the retired id'
    assert client.transactions[0].rolled_back is True
    assert len(client.commits) == 1
    assert _stored_segments(client.commits[0]) == SEGMENTS
    assert client.commits[0]['has_content'] is True


def test_expired_transaction_gives_up_after_the_attempt_budget():
    client = _FakeFirestoreClient({'has_content': False}, [InvalidArgument(EXPIRED_MESSAGE) for _ in range(3)])

    with pytest.raises(InvalidArgument):
        _write(client)

    assert len(client.transactions) == 3
    assert client.commits == []


def test_other_invalid_argument_failures_are_not_retried():
    too_large = InvalidArgument('400 The value of property transcript_segments is longer than 1048487 bytes.')
    client = _FakeFirestoreClient({'has_content': False}, [too_large])

    with pytest.raises(InvalidArgument):
        _write(client)

    assert len(client.transactions) == 1, 'only an expired transaction is recoverable by restarting'


def test_missing_conversation_still_reports_no_write():
    client = _FakeFirestoreClient(None)

    assert _write(client) is False
    assert client.commits == [None]
