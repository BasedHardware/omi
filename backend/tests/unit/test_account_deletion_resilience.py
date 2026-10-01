import unittest
from typing import Any

from database.account_deletion_marker import (
    ACCOUNT_DELETION_COLLECTION,
    _clean_uid,
    account_deletion_document,
    get_user_deletion_wipe_status,
)
from database.account_deletion_policy import (
    ACCOUNT_DELETION_INVALID_STATUS,
    account_deletion_blocks_access,
)
from database.account_deletion_transitions import (
    adopt_legacy_late_agent_vm_cleanup,
    mark_wipe_completed,
    read_agent_vm_migration_journals,
    record_late_agent_vm_cleanup,
)
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite


def _unwrap(fn: Any) -> Any:
    """Unwrap Firestore @transactional wrapper for hermetic unit testing."""
    return getattr(fn, '__wrapped__', getattr(fn, 'to_wrap', fn))


class _MockDocRef:
    def __init__(self, uid: str, exists: bool = True, data: dict | None = None):
        self.uid = uid
        self._exists = exists
        self._data = data or {}
        self.sets = []
        self.updates = []
        self._subcollections = {}

    def collection(self, name: str):
        if name not in self._subcollections:
            self._subcollections[name] = _MockCollection()
        return self._subcollections[name]

    def get(self, transaction=None):
        outer = self

        class _Snap:
            exists = outer._exists
            id = outer.uid

            def to_dict(self):
                return outer._data

        return _Snap()


class _MockCollection:
    def __init__(self):
        self.docs = {}
        self._stream_items = []

    def document(self, path: str):
        if path not in self.docs:
            self.docs[path] = _MockDocRef(path)
        return self.docs[path]

    def stream(self):
        return self._stream_items


class _MockClient:
    def __init__(self):
        self._collections = {}

    def collection(self, name: str):
        if name not in self._collections:
            self._collections[name] = _MockCollection()
        return self._collections[name]


class _MockTransaction:
    def __init__(self):
        self.sets = []
        self.updates = []
        self.in_progress = True
        self.id = b'mock_tx_1'

    def set(self, ref, data, merge=False):
        self.sets.append((ref, data, merge))

    def update(self, ref, data):
        self.updates.append((ref, data))


class TestAccountDeletionResilience(unittest.TestCase):
    def setUp(self):
        self.client = _MockClient()

    def test_clean_uid_valid(self):
        self.assertEqual(_clean_uid("user_12345"), "user_12345")
        # Preserves whitespace to prevent identity aliasing
        self.assertEqual(_clean_uid(" alice "), " alice ")
        # Allows .. inside string ID
        self.assertEqual(_clean_uid("alice..legacy"), "alice..legacy")

    def test_clean_uid_rejects_invalids(self):
        self.assertIsNone(_clean_uid(None))
        self.assertIsNone(_clean_uid(12345))
        self.assertIsNone(_clean_uid(""))
        self.assertIsNone(_clean_uid("   "))
        self.assertIsNone(_clean_uid("."))
        self.assertIsNone(_clean_uid(".."))
        self.assertIsNone(_clean_uid("user/slash"))
        self.assertIsNone(_clean_uid("user\\backslash"))
        self.assertIsNone(_clean_uid("user\0null"))
        self.assertIsNone(_clean_uid("x" * 129))

    def test_account_deletion_document_enforces_clean_uid(self):
        doc = account_deletion_document("alice", firestore_client=self.client)
        self.assertEqual(doc.uid, "alice")
        with self.assertRaises(ValueError):
            account_deletion_document("user/slash", firestore_client=self.client)
        with self.assertRaises(ValueError):
            account_deletion_document("", firestore_client=self.client)

    def test_get_user_deletion_wipe_status_blocks_on_invalid_uid(self):
        res = get_user_deletion_wipe_status(None, firestore_client=self.client)
        self.assertEqual(res, ACCOUNT_DELETION_INVALID_STATUS)
        self.assertTrue(account_deletion_blocks_access(res))

        res2 = get_user_deletion_wipe_status("", firestore_client=self.client)
        self.assertEqual(res2, ACCOUNT_DELETION_INVALID_STATUS)
        self.assertTrue(account_deletion_blocks_access(res2))

    def test_get_user_deletion_wipe_status_hit_and_miss(self):
        doc = self.client.collection(ACCOUNT_DELETION_COLLECTION).document("bob")
        doc._exists = True
        doc._data = {"wipe_status": "pending"}
        res = get_user_deletion_wipe_status("bob", firestore_client=self.client)
        self.assertEqual(res, "pending")

        doc_miss = self.client.collection(ACCOUNT_DELETION_COLLECTION).document("charlie")
        doc_miss._exists = False
        res_miss = get_user_deletion_wipe_status("charlie", firestore_client=self.client)
        self.assertIsNone(res_miss)

    def test_read_agent_vm_migration_journals_validation(self):
        with self.assertRaises(ValueError):
            read_agent_vm_migration_journals(None, firestore_client=self.client)
        with self.assertRaises(ValueError):
            read_agent_vm_migration_journals("   ", firestore_client=self.client)
        with self.assertRaises(ValueError):
            read_agent_vm_migration_journals("user/bad", firestore_client=self.client)

    def test_read_agent_vm_migration_journals_success(self):
        mig_col = self.client.collection('users').document('user1').collection('agentVmMigrations')

        class _FakeStreamSnap:
            id = "mig_1"

            def to_dict(self):
                return {"migrationId": "mig_1", "status": "ok"}

        mig_col._stream_items = [_FakeStreamSnap()]
        res = read_agent_vm_migration_journals("user1", firestore_client=self.client)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["migrationId"], "mig_1")

    def test_mark_wipe_completed_normal_and_late_vm(self):
        tx = _MockTransaction()
        doc = _MockDocRef("u1", exists=True, data={"wipe_status": "pending"})
        ok = _unwrap(mark_wipe_completed)(tx, doc)
        self.assertTrue(ok)
        self.assertEqual(tx.sets[0][1]["wipe_status"], "completed")

        tx2 = _MockTransaction()
        doc_late = _MockDocRef("u2", exists=True, data={"wipe_status": "pending", "late_agent_vm_cleanup": {"vmName": "vm1", "zone": "us-central1-a"}})
        ok2 = _unwrap(mark_wipe_completed)(tx2, doc_late)
        self.assertFalse(ok2)
        self.assertEqual(tx2.sets[0][1]["wipe_status"], "failed")

    def test_record_late_agent_vm_cleanup_gce_validation(self):
        tx = _MockTransaction()
        doc = _MockDocRef("u1", exists=True, data={"wipe_status": "pending"})
        with self.assertRaises(ValueError):
            _unwrap(record_late_agent_vm_cleanup)(tx, doc, "INVALID_VM!", "us-central1-a")
        with self.assertRaises(ValueError):
            _unwrap(record_late_agent_vm_cleanup)(tx, doc, "vm1", "invalid_zone")
        with self.assertRaises(ValueError):
            _unwrap(record_late_agent_vm_cleanup)(tx, doc, "vm1", "us-central1-a", expected_instance_id="non-numeric")

        ok = _unwrap(record_late_agent_vm_cleanup)(tx, doc, "vm-1", "us-central1-a", expected_instance_id="12345")
        self.assertTrue(ok)

    def test_adopt_legacy_late_agent_vm_cleanup_validation(self):
        tx = _MockTransaction()
        doc = _MockDocRef("u1", exists=True, data={"wipe_status": "pending"})
        with self.assertRaises(ValueError):
            _unwrap(adopt_legacy_late_agent_vm_cleanup)(tx, doc, "BAD_VM", "us-central1-a", "12345")
        with self.assertRaises(ValueError):
            _unwrap(adopt_legacy_late_agent_vm_cleanup)(tx, doc, "vm-1", "us-central1-a", "abc_not_numeric")

    def test_adopt_legacy_late_agent_vm_cleanup_match(self):
        tx = _MockTransaction()
        doc = _MockDocRef(
            "u1",
            exists=True,
            data={
                "wipe_status": "pending",
                "late_agent_vm_cleanup": {"vmName": "vm-1", "zone": "us-central1-a"},
            },
        )
        ok = _unwrap(adopt_legacy_late_agent_vm_cleanup)(tx, doc, "vm-1", "us-central1-a", "98765")
        self.assertTrue(ok)
        self.assertEqual(tx.updates[0][1], {'late_agent_vm_cleanup.expectedInstanceId': '98765'})
