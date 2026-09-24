import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add parent directories to import path if needed
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import load, SCHEMA, boolean_to_int, utc_stamp, text


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_memories.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T10:30:00Z"), "2026-09-20 10:30:00")
        self.assertEqual(utc_stamp("2026-09-20T12:30:00+02:00"), "2026-09-20 10:30:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp("invalid-date"))
        self.assertIsNone(utc_stamp(""))

    def test_boolean_to_int(self):
        self.assertEqual(boolean_to_int(True), 1)
        self.assertEqual(boolean_to_int(False), 0)
        self.assertEqual(boolean_to_int("true"), 1)
        self.assertEqual(boolean_to_int("1"), 1)
        self.assertEqual(boolean_to_int("yes"), 1)
        self.assertEqual(boolean_to_int("false"), 0)
        self.assertEqual(boolean_to_int(None), 0)

    def test_text_coercion(self):
        self.assertIsNone(text(None))
        self.assertEqual(text("hello"), "hello")
        self.assertEqual(text(123), "123")
        self.assertEqual(text({"a": 1}), '{"a": 1}')

    def test_load_and_query(self):
        sample_memories = [
            {
                "id": "mem_1",
                "content": "Prefers async architectural reviews over long meetings",
                "category": "work",
                "manually_added": False,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
                "tags": ["workflow"]
            },
            {
                "id": "mem_2",
                "content": "Remembers to water plants on Tuesday",
                "category": "lifestyle",
                "manually_added": True,
                "created_at": "2026-09-21T09:30:00Z",
                "updated_at": "2026-09-21T09:30:00Z",
                "tags": ["home"]
            }
        ]
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(sample_memories), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        # Verify in SQLite
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Check category query
        cursor.execute("SELECT content FROM memories WHERE category = 'work'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "Prefers async architectural reviews over long meetings")

        # Check manually_added count
        cursor.execute("SELECT COUNT(*) FROM memories WHERE manually_added = 1")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Check raw json extraction
        cursor.execute("SELECT json_extract(raw_json, '$.category') FROM memories WHERE id = 'mem_2'")
        self.assertEqual(cursor.fetchone()[0], "lifestyle")

        conn.close()

    def test_idempotence_and_replacement(self):
        batch1 = [
            {"id": "mem_1", "content": "Initial thought", "category": "work", "manually_added": False, "created_at": "2026-09-20T08:00:00Z"}
        ]
        batch2 = [
            {"id": "mem_1", "content": "Updated refined thought", "category": "work", "manually_added": True, "created_at": "2026-09-20T08:00:00Z"},
            {"id": "mem_2", "content": "Second thought", "category": "learnings", "manually_added": False, "created_at": "2026-09-20T10:00:00Z"}
        ]
        f1 = self.dir_path / "b1.json"
        f2 = self.dir_path / "b2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 2)
        self.assertEqual(added, 1)  # Only mem_2 is new
        self.assertEqual(total, 2)

        # Verify update took effect
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT content, manually_added FROM memories WHERE id = 'mem_1'")
        res = cursor.fetchone()
        self.assertEqual(res[0], "Updated refined thought")
        self.assertEqual(res[1], 1)
        conn.close()

    def test_wrapped_dict_payload(self):
        wrapped = {
            "memories": [
                {"id": "mem_wrapped_1", "content": "Wrapped item", "category": "core"}
            ]
        }
        wf = self.dir_path / "wrapped.json"
        wf.write_text(json.dumps(wrapped), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(wf)])
        self.assertEqual(loaded, 1)
        self.assertEqual(total, 1)

    def test_missing_id_raises(self):
        invalid_data = [{"content": "No ID memory", "category": "core"}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(invalid_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])


if __name__ == "__main__":
    unittest.main()
