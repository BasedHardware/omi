"""Tests ensuring Apple Reminders exports clear sync_requested and pending-sync drains settled rows.

Regression coverage for #21214:
- update_action_item clears sync_requested when exported=True
- update_action_item preserves sync_requested for unrelated field updates
- get_pending_apple_reminders_sync drains already-exported rows encountered during
  scan, preventing starvation when 50 settled rows precede genuinely pending exports.
"""

from datetime import datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from database import action_items as action_items_db


class FakeDocSnapshot:
    def __init__(self, doc_id, data, ref):
        self.id = doc_id
        self._data = dict(data)
        self.reference = ref

    def to_dict(self):
        return dict(self._data)


class FakeDocRef:
    def __init__(self, doc_id, storage):
        self.id = doc_id
        self._storage = storage

    def get(self, transaction=None):
        exists = self.id in self._storage
        data = self._storage.get(self.id, {})
        snap = FakeDocSnapshot(self.id, data, self)
        snap.exists = exists
        return snap

    def update(self, fields):
        if self.id not in self._storage:
            raise Exception(f"Document {self.id} not found")
        self._storage[self.id].update(fields)


class FakeQuery:
    def __init__(self, storage, limit_val=50):
        self._storage = storage
        self._limit = limit_val

    def where(self, filter=None):
        return self

    def limit(self, n):
        return FakeQuery(self._storage, n)

    def stream(self):
        matching = []
        for doc_id, data in sorted(self._storage.items()):
            if data.get("sync_requested") is True:
                ref = FakeDocRef(doc_id, self._storage)
                matching.append(FakeDocSnapshot(doc_id, data, ref))
        return matching[: self._limit]


class FakeCollection:
    def __init__(self, storage=None):
        self._storage = storage if storage is not None else {}

    def document(self, doc_id):
        return FakeDocRef(doc_id, self._storage)

    def where(self, filter=None):
        return FakeQuery(self._storage)


class TestAppleRemindersPendingSyncStarvation(unittest.TestCase):
    def test_single_item_export_clears_sync_requested(self):
        storage = {
            "task_1": {
                "id": "task_1",
                "description": "Call dentist",
                "sync_requested": True,
                "exported": False,
            }
        }
        fake_coll = FakeCollection(storage)
        fake_user_doc = MagicMock()
        fake_user_doc.collection.return_value = fake_coll
        fake_db = MagicMock()
        fake_db.collection.return_value.document.return_value = fake_user_doc

        with patch.object(action_items_db, "db", fake_db), patch.object(
            action_items_db, "bump_action_items_list_version"
        ):
            update_data = {
                "exported": True,
                "export_platform": "apple_reminders",
                "apple_reminder_id": "apple-rem-123",
            }
            res = action_items_db.update_action_item("u1", "task_1", update_data)
            self.assertTrue(res)

        self.assertFalse(storage["task_1"]["sync_requested"])
        self.assertTrue(storage["task_1"]["exported"])
        self.assertEqual(storage["task_1"]["apple_reminder_id"], "apple-rem-123")

    def test_unrelated_update_preserves_sync_requested(self):
        storage = {
            "task_2": {
                "id": "task_2",
                "description": "Old description",
                "sync_requested": True,
                "exported": False,
            }
        }
        fake_coll = FakeCollection(storage)
        fake_user_doc = MagicMock()
        fake_user_doc.collection.return_value = fake_coll
        fake_db = MagicMock()
        fake_db.collection.return_value.document.return_value = fake_user_doc

        with patch.object(action_items_db, "db", fake_db), patch.object(
            action_items_db, "bump_action_items_list_version"
        ):
            update_data = {
                "description": "New description",
            }
            res = action_items_db.update_action_item("u1", "task_2", update_data)
            self.assertTrue(res)

        self.assertTrue(storage["task_2"]["sync_requested"])
        self.assertEqual(storage["task_2"]["description"], "New description")

    def test_pending_sync_drains_settled_rows_and_prevents_starvation(self):
        storage = {}
        # 50 settled rows
        for i in range(50):
            doc_id = f"a{i:03d}"
            storage[doc_id] = {
                "id": doc_id,
                "description": f"Settled task {i}",
                "sync_requested": True,
                "exported": True,
                "export_platform": "apple_reminders",
                "apple_reminder_id": f"rem-{i}",
            }
        # 1 genuinely pending task whose silent push was missed
        storage["z-new"] = {
            "id": "z-new",
            "description": "Missed silent push task",
            "sync_requested": True,
            "exported": False,
        }

        fake_coll = FakeCollection(storage)
        fake_user_doc = MagicMock()
        fake_user_doc.collection.return_value = fake_coll
        fake_db = MagicMock()
        fake_db.collection.return_value.document.return_value = fake_user_doc

        with patch.object(action_items_db, "db", fake_db):
            result = action_items_db.get_pending_apple_reminders_sync("u1")

        pending_export = result["pending_export"]
        self.assertEqual(len(pending_export), 1)
        self.assertEqual(pending_export[0]["id"], "z-new")
        self.assertEqual(pending_export[0]["description"], "Missed silent push task")

        # Verify all 50 settled rows were drained and marked sync_requested=False
        for i in range(50):
            self.assertFalse(storage[f"a{i:03d}"]["sync_requested"])


if __name__ == "__main__":
    unittest.main()
