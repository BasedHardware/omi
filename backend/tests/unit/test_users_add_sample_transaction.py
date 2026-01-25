import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Mock the database client to avoid needing GCP credentials
sys.modules["database._client"] = MagicMock()
sys.modules["stripe"] = MagicMock()


class NotFound(Exception):
    pass


_google_module = sys.modules.setdefault("google", types.ModuleType("google"))
_google_cloud_module = sys.modules.setdefault("google.cloud", types.ModuleType("google.cloud"))
_google_exceptions_module = types.ModuleType("google.cloud.exceptions")
_google_exceptions_module.NotFound = NotFound
sys.modules.setdefault("google.cloud.exceptions", _google_exceptions_module)
_google_firestore_module = types.ModuleType("google.cloud.firestore")
sys.modules.setdefault("google.cloud.firestore", _google_firestore_module)
_google_firestore_v1_module = types.ModuleType("google.cloud.firestore_v1")
_google_firestore_v1_module.FieldFilter = MagicMock()
_google_firestore_v1_module.transactional = lambda func: func
sys.modules.setdefault("google.cloud.firestore_v1", _google_firestore_v1_module)
setattr(_google_module, "cloud", _google_cloud_module)
setattr(_google_cloud_module, "exceptions", _google_exceptions_module)
setattr(_google_cloud_module, "firestore", _google_firestore_module)

from database import users as users_db


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


def test_add_sample_transaction_pads_transcripts_for_v1_samples():
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


def test_add_sample_transaction_already_aligned_transcripts():
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


def test_add_sample_transaction_max_samples_reached():
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


def test_add_sample_transaction_person_not_found():
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
