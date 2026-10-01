import unittest
from typing import Any

from database.account_deletion_marker import (
    ACCOUNT_DELETION_COLLECTION,
    _clean_uid,
    account_deletion_document,
    get_user_deletion_wipe_status,
)
from database.account_deletion_transitions import (
    adopt_legacy_late_agent_vm_cleanup,
    mark_wipe_completed,
    read_agent_vm_migration_journals,
    record_late_agent_vm_cleanup,
)
from database.firestore_read_metrics import FirestoreReadOutcome, FirestoreReadSite


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

    def set(self, ref, data, merge=False):
        self.sets.append((ref, data, merge))

    def update(self, ref, data):
        self.updates.append((ref, data))


class TestAccountDeletionResilience(unittest.TestCase):
    def setUp(self):
        self.client = _MockClient()

    def test_clean_uid_valid(self):
        self.assertEqual(_clean_uid("user_12345"), "user_12345")
        self.assertEqual(_clean_uid("  user_abc  "), "user_abc")

    def test_clean_uid_rejects_invalids(self):
        self.assertIsNone(_clean_uid(None))
        self.assertIsNone(_clean_uid(12345))
        self.assertIsNone(_clean_uid(""))
        self.assertIsNone(_clean_uid("   "))
        self.assertIsNone(_clean_uid("user/slash"))
        self.assertIsNone(_clean_uid("user\\backslash"))
        self.assertIsNone(_clean_uid("user\0null"))
        self.assertIsNone(_clean_uid("../traversal"))
        self.assertIsNone(_clean_uid("x" * 129))

    def test_account_deletion_document_enforces_clean_uid(self):
        doc = account_deletion_document("alice", firestore_client=self.client)
        self.assertEqual(doc.uid, "alice")
        with self.assertRaises(ValueError):
            account_deletion_document("../traversal", firestore_client=self.client)
        with self.assertRaises(ValueError):
            account_deletion_document("", firestore_client=self.client)

    def test_get_user_deletion_wipe_status_graceful_on_invalid_uid(self):
        self.assertIsNone(get_user_deletion_wipe_status(None, firestore_client=self.client))
        self.assertIsNone(get_user_deletion_wipe_status("../bad", firestore_client=self.client))
        self.assertIsNone(get_user_deletion_wipe_status("", firestore_client=self.client))

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
            read_agent_vm_migration_journals("../bad", firestore_client=self.client)

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
        ok = mark_wipe_completed(tx, doc)
        self.assertTrue(ok)
        self.assertEqual(tx.sets[0][1]["wipe_status"], "completed")

        tx2 = _MockTransaction()
        doc_late = _MockDocRef("u2", exists=True, data={"wipe_status": "pending", "late_agent_vm_cleanup": {"vm": "x"}})
        ok2 = mark_wipe_completed(tx2, doc_late)
        self.assertFalse(ok2)
        self.assertEqual(tx2.sets[0][1]["wipe_status"], "failed")

    def test_record_late_agent_vm_cleanup_input_validation(self):
        tx = _MockTransaction()
        doc = _MockDocRef("u1", exists=True, data={"wipe_status": "pending"})
        with self.assertRaises(ValueError):
            record_late_agent_vm_cleanup(tx, doc, "", "us-central1-a")
        with self.assertRaises(ValueError):
            record_late_agent_vm_cleanup(tx, doc, "vm1", "   ")
        with self.assertRaises(ValueError):
            record_late_agent_vm_cleanup(tx, doc, "vm1", "us-central1-a", expected_instance_id="non-numeric")

    def test_adopt_legacy_late_agent_vm_cleanup_validation(self):
        tx = _MockTransaction()
        doc = _MockDocRef("u1", exists=True, data={"wipe_status": "pending"})
        with self.assertRaises(ValueError):
            adopt_legacy_late_agent_vm_cleanup(tx, doc, "", "zone", "12345")
        with self.assertRaises(ValueError):
            adopt_legacy_late_agent_vm_cleanup(tx, doc, "vm", "zone", "abc_not_numeric")

    def test_adopt_legacy_late_agent_vm_cleanup_match(self):
        tx = _MockTransaction()
        doc = _MockDocRef(
            "u1",
            exists=True,
            data={
                "wipe_status": "pending",
                "late_agent_vm_cleanup": {"vmName": "vm1", "zone": "zone1"},
            },
        )
        ok = adopt_legacy_late_agent_vm_cleanup(tx, doc, "vm1", "zone1", "98765")
        self.assertTrue(ok)
        self.assertEqual(tx.updates[0][1], {'late_agent_vm_cleanup.expectedInstanceId': '98765'})
