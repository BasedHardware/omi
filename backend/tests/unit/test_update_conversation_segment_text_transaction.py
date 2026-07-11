"""update_conversation_segment_text is a Firestore transaction (lost-update guard).

Regression for #9392: the old implementation did a bare ``doc_ref.get()`` then
``doc_ref.update()`` (rewriting the whole ``transcript_segments`` array). Two
concurrent edits to *different* segments both read the pre-edit array and the
later write clobbered the earlier one. The read-modify-write must run inside a
Firestore transaction so the read is bound to the transaction and it retries on
contention.

database.conversations binds ``db`` at import (``from ._client import db``) and
pulls the ``google.cloud.firestore`` chain at top level, so the fake modules must
be active before the module is exec'd — the sanctioned Tier-2 "fake must precede
import" case (see backend/docs/test_isolation.md).
"""

import json
import os
import zlib
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def conversations_db():
    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")
    client_stub.document_id_from_seed = MagicMock(name="document_id_from_seed")

    firestore_stub = ModuleType("google.cloud.firestore")
    firestore_stub.transactional = lambda func: func

    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]

    api_core_pkg = ModuleType("google.api_core")
    api_core_pkg.__path__ = []  # type: ignore[attr-defined]
    api_core_exceptions = ModuleType("google.api_core.exceptions")
    for _name in ("AlreadyExists", "Conflict", "NotFound"):
        setattr(api_core_exceptions, _name, type(_name, (Exception,), {}))

    fv1_stub = ModuleType("google.cloud.firestore_v1")
    fv1_stub.FieldFilter = MagicMock()
    fv1_stub.transactional = lambda func: func

    fakes = {
        "database._client": client_stub,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore": firestore_stub,
        "google.api_core": api_core_pkg,
        "google.api_core.exceptions": api_core_exceptions,
        "google.cloud.firestore_v1": fv1_stub,
        "firebase_admin": MagicMock(),
        "firebase_admin.auth": MagicMock(),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.conversations",
            os.path.join(str(_BACKEND), "database", "conversations.py"),
        )
        yield module


class _FakeSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakeDocRef:
    def __init__(self, data, exists=True):
        self._data = data
        self._exists = exists
        self.get_transaction = "unset"

    def get(self, transaction=None, **kwargs):
        # Record how the read was issued — a lost-update fix must read inside the txn.
        self.get_transaction = transaction
        return _FakeSnapshot(self._data, exists=self._exists)


class _FakeTransaction:
    def __init__(self):
        self.updated_ref = None
        self.updated_data = None

    def update(self, doc_ref, update_data):
        self.updated_ref = doc_ref
        self.updated_data = update_data


def _standard_conversation(segments):
    return {
        "id": "conv-1",
        "data_protection_level": "standard",
        "transcript_segments": segments,
    }


def _decode_written_segments(payload):
    raw = payload["transcript_segments"]
    return json.loads(zlib.decompress(raw).decode("utf-8"))


def test_reads_inside_transaction_and_edits_target_segment(conversations_db):
    data = _standard_conversation([{"id": "s1", "text": "hello"}, {"id": "s2", "text": "world"}])
    doc_ref = _FakeDocRef(data)
    transaction = _FakeTransaction()

    result = conversations_db._update_segment_text_transaction(transaction, doc_ref, "uid-1", "s2", "WORLD")

    assert result == "ok"
    # The read must be bound to the transaction (the actual lost-update fix).
    assert doc_ref.get_transaction is transaction
    # The write goes through the transaction, not a bare doc_ref.update().
    assert transaction.updated_ref is doc_ref
    written = _decode_written_segments(transaction.updated_data)
    assert written == [{"id": "s1", "text": "hello"}, {"id": "s2", "text": "WORLD"}]


def test_missing_conversation_returns_not_found(conversations_db):
    doc_ref = _FakeDocRef({}, exists=False)
    transaction = _FakeTransaction()

    result = conversations_db._update_segment_text_transaction(transaction, doc_ref, "uid-1", "s1", "x")

    assert result == "not_found"
    assert transaction.updated_data is None


def test_locked_conversation_is_not_written(conversations_db):
    data = _standard_conversation([{"id": "s1", "text": "hi"}])
    data["is_locked"] = True
    doc_ref = _FakeDocRef(data)
    transaction = _FakeTransaction()

    result = conversations_db._update_segment_text_transaction(transaction, doc_ref, "uid-1", "s1", "x")

    assert result == "locked"
    assert transaction.updated_data is None


def test_unknown_segment_returns_segment_not_found(conversations_db):
    data = _standard_conversation([{"id": "s1", "text": "hi"}])
    doc_ref = _FakeDocRef(data)
    transaction = _FakeTransaction()

    result = conversations_db._update_segment_text_transaction(transaction, doc_ref, "uid-1", "does-not-exist", "x")

    assert result == "segment_not_found"
    assert transaction.updated_data is None
