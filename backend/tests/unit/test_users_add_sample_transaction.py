"""_add_sample_transaction pads/aligns speech_sample_transcripts.

database.users binds ``db`` at import (``from ._client import db``) and pulls the
``google.cloud.firestore_v1`` chain at top level, so the fake ``database._client``
must be active before the module is exec'd. This is the sanctioned Tier-2 "fake
must precede import" case: see backend/docs/test_isolation.md and
testing.import_isolation.load_module_fresh.
"""

import os
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

from testing.import_isolation import load_module_fresh, stub_modules

_BACKEND = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def users_db():
    """Load a fresh database.users against stubbed database._client + firestore chain."""
    client_stub = ModuleType("database._client")
    client_stub.db = MagicMock(name="db")
    client_stub.document_id_from_seed = MagicMock(name="document_id_from_seed")

    firestore_stub = ModuleType("google.cloud.firestore")
    google_pkg = ModuleType("google")
    google_pkg.__path__ = []  # type: ignore[attr-defined]
    google_cloud_pkg = ModuleType("google.cloud")
    google_cloud_pkg.__path__ = []  # type: ignore[attr-defined]

    google_exceptions_stub = ModuleType("google.cloud.exceptions")

    class NotFound(Exception):
        pass

    google_exceptions_stub.NotFound = NotFound

    fv1_stub = ModuleType("google.cloud.firestore_v1")
    fv1_stub.FieldFilter = MagicMock()
    fv1_stub.transactional = lambda func: func

    fakes = {
        "database._client": client_stub,
        "google": google_pkg,
        "google.cloud": google_cloud_pkg,
        "google.cloud.firestore": firestore_stub,
        "google.cloud.exceptions": google_exceptions_stub,
        "google.cloud.firestore_v1": fv1_stub,
        "stripe": MagicMock(),
        "firebase_admin": MagicMock(),
        "firebase_admin.auth": MagicMock(),
    }
    with stub_modules(fakes):
        module = load_module_fresh(
            "database.users",
            os.path.join(str(_BACKEND), "database", "users.py"),
        )
        yield module


class _FakeSnapshot:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class _FakePersonRef:
    def __init__(self, data, exists=True):
        self._data = data
        self._exists = exists

    def get(self, transaction=None):
        return _FakeSnapshot(self._data, exists=self._exists)


class _FakeTransaction:
    def __init__(self):
        self.updated_ref = None
        self.updated_data = None
        self._read_only = False
        self._max_attempts = 1
        self._id = None
        self.committed = False
        self.rolled_back = False

    def update(self, person_ref, update_data):
        self.updated_ref = person_ref
        self.updated_data = update_data

    def _clean_up(self):
        self._id = None

    def _begin(self, retry_id=None):
        self._id = retry_id or "txn-1"

    def _commit(self):
        self.committed = True

    def _rollback(self):
        self.rolled_back = True


def test_add_sample_transaction_pads_transcripts_for_v1_samples(users_db):
    person_data = {
        "speech_samples": ["sample-a.wav", "sample-b.wav"],
        "speech_sample_transcripts": [],
    }
    person_ref = _FakePersonRef(person_data)
    transaction = _FakeTransaction()

    result = users_db._add_sample_transaction(
        transaction,
        person_ref,
        "sample-c.wav",
        transcript="we ride at dawn",
        max_samples=5,
    )

    assert result is True
    assert transaction.updated_data["speech_samples"] == [
        "sample-a.wav",
        "sample-b.wav",
        "sample-c.wav",
    ]
    assert transaction.updated_data["speech_sample_transcripts"] == [
        "",
        "",
        "we ride at dawn",
    ]
    assert transaction.updated_data["speech_samples_version"] == 3
    assert "updated_at" in transaction.updated_data


def test_add_sample_transaction_already_aligned_transcripts(users_db):
    person_data = {
        "speech_samples": ["sample-a.wav", "sample-b.wav"],
        "speech_sample_transcripts": ["first", "second"],
    }
    person_ref = _FakePersonRef(person_data)
    transaction = _FakeTransaction()

    result = users_db._add_sample_transaction(
        transaction,
        person_ref,
        "sample-c.wav",
        transcript="third",
        max_samples=5,
    )

    assert result is True
    assert transaction.updated_data["speech_samples"] == [
        "sample-a.wav",
        "sample-b.wav",
        "sample-c.wav",
    ]
    assert transaction.updated_data["speech_sample_transcripts"] == [
        "first",
        "second",
        "third",
    ]
    assert transaction.updated_data["speech_samples_version"] == 3


def test_add_sample_transaction_max_samples_reached(users_db):
    person_data = {
        "speech_samples": ["a.wav", "b.wav"],
        "speech_sample_transcripts": ["a", "b"],
    }
    person_ref = _FakePersonRef(person_data)
    transaction = _FakeTransaction()

    result = users_db._add_sample_transaction(
        transaction,
        person_ref,
        "c.wav",
        transcript="c",
        max_samples=2,
    )

    assert result is False
    assert transaction.updated_data is None


def test_add_sample_transaction_person_not_found(users_db):
    person_ref = _FakePersonRef({}, exists=False)
    transaction = _FakeTransaction()

    result = users_db._add_sample_transaction(
        transaction,
        person_ref,
        "sample-x.wav",
        transcript="ghost",
        max_samples=5,
    )

    assert result is False
    assert transaction.updated_data is None
