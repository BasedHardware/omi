import os
import sys
import types
from unittest.mock import MagicMock

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

# Mock heavy deps to avoid needing GCP credentials / firebase_admin (CI-only).
sys.modules["database._client"] = MagicMock()
sys.modules["database.firestore_cache"] = MagicMock()
sys.modules["database.redis_db"] = MagicMock()
sys.modules["stripe"] = MagicMock()
sys.modules["firebase_admin"] = MagicMock()
sys.modules["firebase_admin.auth"] = MagicMock()
# utils.subscription has a deep import chain (firebase_admin/stripe/fastapi) and is
# only used by code paths we don't exercise here; stub the whole module.
sys.modules["utils"] = types.ModuleType("utils")
sys.modules["utils"].__path__ = []
sys.modules["utils.subscription"] = MagicMock()


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
# `transactional` is a pass-through so the decorated helper runs inline in tests
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
    """Records whether reads/writes were routed through a transaction."""

    def __init__(self, data, exists=True):
        self._data = data
        self._exists = exists
        self.get_transactions = []  # the `transaction=` kwarg passed to each get()
        self.direct_updates = []  # any non-transactional person_ref.update(...) calls

    def get(self, transaction=None):
        self.get_transactions.append(transaction)
        return _FakeSnapshot(self._data, exists=self._exists)

    def update(self, update_data):
        # A non-transactional write -> the read-modify-write was NOT atomic.
        self.direct_updates.append(update_data)


class _FakeTransaction:
    def __init__(self):
        self.updated_ref = None
        self.updated_data = None

    def update(self, person_ref, update_data):
        self.updated_ref = person_ref
        self.updated_data = update_data


def test_remove_sample_uses_transaction_for_read_and_write():
    """The remove must read AND write through the SAME transaction (atomic).

    Before the fix the helper did a bare person_ref.get() (no transaction) and a
    bare person_ref.update(...), so the two parallel arrays could drift under
    concurrency. After the fix get(transaction=...) and transaction.update(...)
    are used, mirroring _add_sample_transaction.
    """
    person_data = {
        "speech_samples": ["a.wav", "b.wav", "c.wav"],
        "speech_sample_transcripts": ["ta", "tb", "tc"],
    }
    person_ref = _FakePersonRef(person_data)
    transaction = _FakeTransaction()

    result = users_db._remove_sample_transaction(transaction, person_ref, "b.wav")

    assert result is True
    # Read happened inside the transaction (not a bare get()).
    assert person_ref.get_transactions == [transaction]
    # Write happened via transaction.update, NOT a bare person_ref.update.
    assert person_ref.direct_updates == []
    assert transaction.updated_ref is person_ref
    # Aligned removal of the matching index from both arrays.
    assert transaction.updated_data["speech_samples"] == ["a.wav", "c.wav"]
    assert transaction.updated_data["speech_sample_transcripts"] == ["ta", "tc"]
    assert "updated_at" in transaction.updated_data


def test_remove_person_speech_sample_drives_the_transactional_helper():
    """Public entrypoint must hand a real db.transaction() to the @transactional helper."""
    captured = {}

    def fake_helper(transaction, person_ref, sample_path):
        captured["transaction"] = transaction
        captured["sample_path"] = sample_path
        return True

    sentinel_txn = object()
    users_db.db.transaction.return_value = sentinel_txn

    import unittest.mock as _mock

    with _mock.patch.object(users_db, "_remove_sample_transaction", side_effect=fake_helper):
        result = users_db.remove_person_speech_sample("uid-1", "person-1", "b.wav")

    assert result is True
    # The transaction passed to the helper came from db.transaction(), proving the
    # read-modify-write is wrapped in a Firestore transaction.
    assert captured["transaction"] is sentinel_txn
    assert captured["sample_path"] == "b.wav"


def test_remove_sample_transaction_sample_not_found():
    person_data = {
        "speech_samples": ["a.wav"],
        "speech_sample_transcripts": ["ta"],
    }
    person_ref = _FakePersonRef(person_data)
    transaction = _FakeTransaction()

    result = users_db._remove_sample_transaction(transaction, person_ref, "missing.wav")

    assert result is False
    assert transaction.updated_data is None
    assert person_ref.direct_updates == []


def test_remove_sample_transaction_person_not_found():
    person_ref = _FakePersonRef({}, exists=False)
    transaction = _FakeTransaction()

    result = users_db._remove_sample_transaction(transaction, person_ref, "a.wav")

    assert result is False
    assert transaction.updated_data is None
    assert person_ref.direct_updates == []
