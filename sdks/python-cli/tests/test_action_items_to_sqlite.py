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

    def test_empty_wrappers(self):
        cases = [
            ("bare", []),
            ("action_items", {"action_items": []}),
            ("items", {"items": []}),
            ("data", {"data": []}),
        ]
        for name, payload in cases:
            source = self.dir_path / f"empty_{name}.json"
            source.write_text(json.dumps(payload), encoding="utf-8")
            db = self.dir_path / f"empty_{name}.sqlite"
            loaded, added, total = load(str(db), [str(source)])
            self.assertEqual((loaded, added, total), (0, 0, 0), f"Failed for {name}")

            conn = sqlite3.connect(str(db))
            count = conn.execute("SELECT COUNT(*) FROM action_items").fetchone()[0]
            conn.close()
            self.assertEqual(count, 0, f"Table should be empty for {name}")

    def test_mixed_file_batch(self):
        valid_tasks = [
            {"id": "t1", "description": "Task 1", "completed": False},
            {"id": "t2", "description": "Task 2", "completed": True},
        ]
        f_valid = self.dir_path / "valid.json"
        f_valid.write_text(json.dumps(valid_tasks), encoding="utf-8")

        f_empty_wrapper1 = self.dir_path / "empty_w1.json"
        f_empty_wrapper1.write_text(json.dumps({"action_items": []}), encoding="utf-8")

        f_empty_wrapper2 = self.dir_path / "empty_w2.json"
        f_empty_wrapper2.write_text(json.dumps({"items": []}), encoding="utf-8")

        f_empty_wrapper3 = self.dir_path / "empty_w3.json"
        f_empty_wrapper3.write_text(json.dumps({"data": []}), encoding="utf-8")

        f_empty_bare = self.dir_path / "empty_bare.json"
        f_empty_bare.write_text(json.dumps([]), encoding="utf-8")

        sources = [
            str(f_empty_wrapper1),
            str(f_valid),
            str(f_empty_wrapper2),
            str(f_empty_bare),
            str(f_empty_wrapper3),
        ]
        loaded, added, total = load(str(self.db_path), sources)
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        rows = conn.execute("SELECT id, description, completed FROM action_items ORDER BY id").fetchall()
        conn.close()
        self.assertEqual(rows, [("t1", "Task 1", 0), ("t2", "Task 2", 1)])

    def test_single_object_input(self):
        single_item = {"id": "single_1", "description": "Solo task", "completed": True}
        f_single = self.dir_path / "single.json"
        f_single.write_text(json.dumps(single_item), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(f_single)])
        self.assertEqual((loaded, added, total), (1, 1, 1))

        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute("SELECT id, description, completed FROM action_items WHERE id = 'single_1'").fetchone()
        conn.close()
        self.assertEqual(row, ("single_1", "Solo task", 1))

    def test_malformed_wrappers_raise(self):
        cases = [
            ("action_items_str", {"action_items": "not-a-list"}),
            ("items_num", {"items": 12345}),
            ("data_none", {"data": None}),
        ]
        for name, payload in cases:
            f = self.dir_path / f"malformed_{name}.json"
            f.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError, msg=f"Should raise for {name}"):
                load(str(self.db_path), [str(f)])

    def test_malformed_input_leaves_existing_rows_unchanged(self):
        initial_tasks = [{"id": "init_1", "description": "Initial task", "completed": False}]
        f_init = self.dir_path / "init.json"
        f_init.write_text(json.dumps(initial_tasks), encoding="utf-8")
        load(str(self.db_path), [str(f_init)])

        conn = sqlite3.connect(str(self.db_path))
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM action_items").fetchone()[0], 1)
        conn.close()

        # Batch with valid and invalid files
        f_next_valid = self.dir_path / "next_valid.json"
        f_next_valid.write_text(json.dumps([{"id": "next_1", "description": "Next"}]), encoding="utf-8")
        f_bad = self.dir_path / "bad_in_batch.json"
        f_bad.write_text(json.dumps([{"description": "Missing ID"}]), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(f_next_valid), str(f_bad)])

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        count = cursor.execute("SELECT COUNT(*) FROM action_items").fetchone()[0]
        rows = cursor.execute("SELECT id FROM action_items").fetchall()
        conn.close()

        self.assertEqual(count, 1)
        self.assertEqual(rows, [("init_1",)])


if __name__ == "__main__":
    unittest.main()
