import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add parent directories to import path if needed
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_sqlite import load, SCHEMA, boolean_to_int, utc_stamp


class TestActionItemsToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_tasks.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T10:30:00Z"), "2026-09-20 10:30:00")
        self.assertEqual(utc_stamp("2026-09-20T12:30:00+02:00"), "2026-09-20 10:30:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp("invalid-date"))

    def test_boolean_to_int(self):
        self.assertEqual(boolean_to_int(True), 1)
        self.assertEqual(boolean_to_int(False), 0)
        self.assertEqual(boolean_to_int("true"), 1)
        self.assertEqual(boolean_to_int("1"), 1)
        self.assertEqual(boolean_to_int("false"), 0)
        self.assertEqual(boolean_to_int(None), 0)

    def test_load_and_query(self):
        sample_tasks = [
            {
                "id": "task_1",
                "description": "Send invoice to client",
                "completed": False,
                "due_at": "2026-09-21T18:00:00Z",
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
                "conversation_id": "conv_100",
            },
            {
                "id": "task_2",
                "description": "Review PR #15129",
                "completed": True,
                "due_at": None,
                "created_at": "2026-09-20T09:00:00Z",
                "updated_at": "2026-09-20T09:30:00Z",
                "conversation_id": "conv_101",
            },
        ]
        json_file = self.dir_path / "tasks.json"
        json_file.write_text(json.dumps(sample_tasks), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        # Verify in SQLite
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Check count of open tasks
        cursor.execute("SELECT COUNT(*) FROM action_items WHERE completed = 0")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Check raw json extraction
        cursor.execute("SELECT json_extract(raw_json, '$.description') FROM action_items WHERE id = 'task_1'")
        self.assertEqual(cursor.fetchone()[0], "Send invoice to client")

        conn.close()

    def test_idempotence_and_replacement(self):
        batch1 = [
            {"id": "task_1", "description": "Draft proposal", "completed": False, "created_at": "2026-09-20T08:00:00Z"}
        ]
        batch2 = [
            {"id": "task_1", "description": "Draft proposal", "completed": True, "created_at": "2026-09-20T08:00:00Z"},
            {"id": "task_2", "description": "Submit proposal", "completed": False, "created_at": "2026-09-20T10:00:00Z"}
        ]
        f1 = self.dir_path / "b1.json"
        f2 = self.dir_path / "b2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 2)
        self.assertEqual(added, 1)  # Only task_2 is new
        self.assertEqual(total, 2)

        # Check that task_1 is now completed = 1
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT completed FROM action_items WHERE id = 'task_1'")
        self.assertEqual(cursor.fetchone()[0], 1)
        conn.close()

    def test_missing_id_raises(self):
        invalid_data = [{"description": "No ID task", "completed": False}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(invalid_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])


if __name__ == "__main__":
    unittest.main()
