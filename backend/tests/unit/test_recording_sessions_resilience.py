"""Hermetic unit tests for recording_sessions input validation and resilience guards.

Verifies:
- Input sanitization and path traversal rejection across all identifiers (uid, recording_session_id, conversation_id)
- Outer retry resiliency under Firestore transaction contention (Aborted errors)
- Clamping and safe fallbacks for corrupted/negative sequence numbers and schema versions
- Deterministic handling of malformed documents and rejected lifecycle transitions
"""

import copy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _pkg(name: str):
    mod = sys.modules.get(name)
    if mod is None or not hasattr(mod, "__path__"):
        mod = types.ModuleType(name)
        mod.__path__ = []
        sys.modules[name] = mod
    return mod


def _mod(name: str):
    mod = sys.modules.get(name)
    if mod is None:
        mod = types.ModuleType(name)
        sys.modules[name] = mod
    return mod


# Preflight stubs for bare environments
for p in ["google", "google.api_core", "google.cloud", "models"]:
    _pkg(p)

_exc = _mod("google.api_core.exceptions")
for exc_name in ["Aborted", "NotFound", "InvalidArgument", "AlreadyExists", "Conflict"]:
    if not hasattr(_exc, exc_name):
        setattr(_exc, exc_name, type(exc_name, (Exception,), {}))
setattr(sys.modules["google.api_core"], "exceptions", _exc)


_fs = _mod("google.cloud.firestore")
if not hasattr(_fs, "Query"):
    _fs.Query = MagicMock()
if not hasattr(_fs, "FieldFilter"):
    _fs.FieldFilter = MagicMock()
if not hasattr(_fs, "transactional"):
    _fs.transactional = lambda fn: fn
setattr(sys.modules["google.cloud"], "firestore", _fs)

_fs_v1 = _mod("google.cloud.firestore_v1")
if not hasattr(_fs_v1, "FieldFilter"):
    _fs_v1.FieldFilter = MagicMock()
setattr(sys.modules["google.cloud"], "firestore_v1", _fs_v1)

db_pkg = _mod("database")
db_pkg.__path__ = [str(BACKEND_DIR / "database")]
_conv_db = _mod("database.conversations")
if not hasattr(_conv_db, "raw_conversation_has_content"):
    _conv_db.raw_conversation_has_content = lambda uid, conv: bool(conv.get("has_content"))
setattr(db_pkg, "conversations", _conv_db)


from database import recording_sessions
from database.firestore_transaction_retry import run_with_transaction_contention_retry


class _FakeSnapshot:
    def __init__(self, data: dict | None, exists: bool = True):
        self._data = copy.deepcopy(data)
        self.exists = exists if data is not None else False

    def to_dict(self):
        return copy.deepcopy(self._data)


class _FakeDocRef:
    def __init__(self, store: dict, path: tuple):
        self.store = store
        self.path = path

    def get(self, transaction=None):
        del transaction
        data = self.store.get(self.path)
        return _FakeSnapshot(data, exists=data is not None)

    def collection(self, name: str):
        return _FakeCollectionRef(self.store, self.path + (name,))


class _FakeCollectionRef:
    def __init__(self, store: dict, path: tuple):
        self.store = store
        self.path = path

    def document(self, doc_id: str):
        return _FakeDocRef(self.store, self.path + (doc_id,))


class _FakeTransaction:
    def __init__(self, store: dict):
        self.store = store

    def create(self, doc_ref, data):
        if doc_ref.path in self.store:
            raise RuntimeError("Document already exists")
        self.store[doc_ref.path] = copy.deepcopy(data)

    def update(self, doc_ref, updates):
        if doc_ref.path not in self.store:
            raise RuntimeError("Document does not exist")
        self.store[doc_ref.path].update(copy.deepcopy(updates))

    def delete(self, doc_ref):
        self.store.pop(doc_ref.path, None)


class _FakeFirestoreClient:
    def __init__(self):
        self.documents = {}

    def collection(self, name: str):
        return _FakeCollectionRef(self.documents, (name,))

    def transaction(self):
        return _FakeTransaction(self.documents)


class TestRecordingSessionsResilience(unittest.TestCase):
    def setUp(self):
        self.client = _FakeFirestoreClient()

    def test_validate_id_success(self):
        self.assertEqual(recording_sessions._validate_id("clean_id", "test"), "clean_id")
        self.assertEqual(recording_sessions._validate_id("  with_spaces  ", "test"), "with_spaces")
        self.assertEqual(recording_sessions._validate_id("uuid-123-abc", "test"), "uuid-123-abc")

    def test_validate_id_rejects_empty_and_whitespace(self):
        with self.assertRaises(ValueError) as ctx:
            recording_sessions._validate_id("", "uid")
        self.assertIn("cannot be empty", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            recording_sessions._validate_id("   \t\n  ", "uid")
        self.assertIn("cannot be empty", str(ctx.exception))

    def test_validate_id_rejects_non_string(self):
        for bad_val in [None, 12345, ["id"], {"id": 1}]:
            with self.assertRaises(ValueError) as ctx:
                recording_sessions._validate_id(bad_val, "session_id")
            self.assertIn("must be a string", str(ctx.exception))

    def test_validate_id_rejects_path_traversal(self):
        traversals = ["../etc/passwd", "users/admin", "..", "folder\\file"]
        for bad_id in traversals:
            with self.assertRaises(ValueError) as ctx:
                recording_sessions._validate_id(bad_id, "doc_id")
            self.assertIn("contains invalid path traversal characters", str(ctx.exception))

    def test_create_or_get_recording_session_validates_inputs(self):
        # Empty or traversal uid
        with self.assertRaises(ValueError):
            recording_sessions.create_or_get_recording_session("", "sid", "cid", firestore_client=self.client)
        with self.assertRaises(ValueError):
            recording_sessions.create_or_get_recording_session(
                "../traversal", "sid", "cid", firestore_client=self.client
            )

        # Empty or traversal recording_session_id
        with self.assertRaises(ValueError):
            recording_sessions.create_or_get_recording_session("u1", "   ", "cid", firestore_client=self.client)
        with self.assertRaises(ValueError):
            recording_sessions.create_or_get_recording_session("u1", "sid/extra", "cid", firestore_client=self.client)

        # Empty or traversal proposed_conversation_id
        with self.assertRaises(ValueError):
            recording_sessions.create_or_get_recording_session("u1", "sid", "", firestore_client=self.client)
        with self.assertRaises(ValueError):
            recording_sessions.create_or_get_recording_session("u1", "sid", "..", firestore_client=self.client)

    def test_renew_recording_session_lease_safely_rejects_invalid_inputs(self):
        self.assertFalse(
            recording_sessions.renew_recording_session_lease("", "sid", "cid", firestore_client=self.client)
        )
        self.assertFalse(
            recording_sessions.renew_recording_session_lease("u1", "../sid", "cid", firestore_client=self.client)
        )
        self.assertFalse(
            recording_sessions.renew_recording_session_lease("u1", "sid", None, firestore_client=self.client)
        )

    def test_get_recording_session_validates_inputs(self):
        with self.assertRaises(ValueError):
            recording_sessions.get_recording_session("", "sid", firestore_client=self.client)
        with self.assertRaises(ValueError):
            recording_sessions.get_recording_session("u1", "../bad_sid", firestore_client=self.client)

    def test_tombstone_and_delete_empty_conversation_validates_inputs(self):
        with self.assertRaises(ValueError):
            recording_sessions.tombstone_and_delete_empty_conversation("", "c1", "s1", firestore_client=self.client)
        with self.assertRaises(ValueError):
            recording_sessions.tombstone_and_delete_empty_conversation(
                "u1", "c1/bad", "s1", firestore_client=self.client
            )
        with self.assertRaises(ValueError):
            recording_sessions.tombstone_and_delete_empty_conversation(
                "u1", "c1", "../s1", firestore_client=self.client
            )

    def test_record_lifecycle_event_safely_rejects_invalid_identifiers(self):
        res1 = recording_sessions.record_lifecycle_event("", "s1", "c1", "processing", firestore_client=self.client)
        self.assertFalse(res1["accepted"])
        self.assertEqual(res1["discard_reason"], "invalid_identifier")

        res2 = recording_sessions.record_lifecycle_event(
            "u1", "../s1", "c1", "processing", firestore_client=self.client
        )
        self.assertFalse(res2["accepted"])
        self.assertEqual(res2["discard_reason"], "invalid_identifier")

        res3 = recording_sessions.record_lifecycle_event(
            "u1", "s1", "c1/hack", "processing", firestore_client=self.client
        )
        self.assertFalse(res3["accepted"])
        self.assertEqual(res3["discard_reason"], "invalid_identifier")

    def test_transaction_contention_retries_and_succeeds(self):
        attempts = 0

        def flaky_operation(transaction):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise _exc.Aborted("Contention collision")
            return "success"

        result = run_with_transaction_contention_retry(
            self.client.transaction,
            flaky_operation,
            operation_name="test_flaky_txn",
            max_attempts=3,
            sleep=lambda _: None,
        )
        self.assertEqual(result, "success")
        self.assertEqual(attempts, 2)

    def test_sequence_and_version_sanitization_on_corrupt_data(self):
        corrupt_data = {
            "conversation_id": "c1",
            "lifecycle_sequence": -10,
            "lifecycle_version": 0,
            "lifecycle_phase": "in_progress",
        }
        binding = recording_sessions._binding(corrupt_data, "s1", mapping_conflict=False)
        self.assertEqual(binding["lifecycle_sequence"], 0)
        self.assertEqual(binding["lifecycle_version"], 1)

        string_seq_data = {
            "conversation_id": "c1",
            "lifecycle_sequence": "42",
            "lifecycle_version": "2",
        }
        binding2 = recording_sessions._binding(string_seq_data, "s1", mapping_conflict=False)
        self.assertEqual(binding2["lifecycle_sequence"], 42)
        self.assertEqual(binding2["lifecycle_version"], 2)

    def test_create_or_get_recording_session_contention_retry_recovers(self):
        real_txn = self.client.transaction
        attempts = 0

        def flaky_txn():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise _exc.Aborted("Contention on session open")
            return real_txn()

        with patch.object(self.client, "transaction", side_effect=flaky_txn):
            result = recording_sessions.create_or_get_recording_session(
                "u1", "sid1", "cid1", firestore_client=self.client
            )
        self.assertEqual(result["recording_session_id"], "sid1")
        self.assertEqual(result["conversation_id"], "cid1")
        self.assertEqual(attempts, 2)

    def test_record_lifecycle_event_contention_retry_recovers(self):
        recording_sessions.create_or_get_recording_session("u1", "sid2", "cid2", firestore_client=self.client)
        real_txn = self.client.transaction
        attempts = 0

        def flaky_txn():
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise _exc.Aborted("Contention on lifecycle event")
            return real_txn()

        with patch.object(self.client, "transaction", side_effect=flaky_txn):
            event = recording_sessions.record_lifecycle_event(
                "u1", "sid2", "cid2", "processing", firestore_client=self.client
            )
        self.assertTrue(event["accepted"])
        self.assertEqual(event["lifecycle_phase"], "processing")
        self.assertEqual(attempts, 2)


if __name__ == "__main__":
    unittest.main()
