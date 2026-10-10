import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

# Add parent directories to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import load, SCHEMA, boolean_to_int, utc_stamp, validate_db_path, text


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
        self.assertIsNone(utc_stamp(""))
        self.assertIsNone(utc_stamp("invalid-date"))

    def test_boolean_to_int(self):
        self.assertEqual(boolean_to_int(True), 1)
        self.assertEqual(boolean_to_int(False), 0)
        self.assertEqual(boolean_to_int("true"), 1)
        self.assertEqual(boolean_to_int("1"), 1)
        self.assertEqual(boolean_to_int("yes"), 1)
        self.assertEqual(boolean_to_int("t"), 1)
        self.assertEqual(boolean_to_int("false"), 0)
        self.assertEqual(boolean_to_int("no"), 0)
        self.assertEqual(boolean_to_int("0"), 0)
        self.assertEqual(boolean_to_int(None), 0)

    def test_text_and_surrogates(self):
        self.assertIsNone(text(None))
        self.assertEqual(text("Hello world"), "Hello world")
        self.assertEqual(text({"key": "val"}), '{"key": "val"}')
        # Test surrogate dropping
        surrogate_str = "Invalid \ud800 text"
        sanitized = text(surrogate_str)
        self.assertEqual(sanitized, "Invalid  text")

    def test_path_traversal_rejected(self):
        sample_memories = [{"id": "m1", "content": "Memory 1", "category": "work"}]
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(sample_memories), encoding="utf-8")

        escape = self.dir_path.parent / "escape.sqlite"
        existed = escape.exists()
        try:
            with self.assertRaises(ValueError, msg="Expected ValueError for '..' in path"):
                load(str(self.dir_path / ".." / "escape.sqlite"), [str(json_file)])
            if not existed:
                self.assertFalse(escape.exists())
        finally:
            if not existed and escape.exists():
                escape.unlink()

    def test_non_sqlite_file_rejected(self):
        not_a_db = self.dir_path / "output.sqlite"
        original = b"This is not a SQLite database header"
        not_a_db.write_bytes(original)

        sample_memories = [{"id": "m1", "content": "Memory 1"}]
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(sample_memories), encoding="utf-8")

        with self.assertRaises(ValueError, msg="Expected ValueError when output is not SQLite"):
            load(str(not_a_db), [str(json_file)])

        self.assertEqual(not_a_db.read_bytes(), original)

    def test_load_and_query(self):
        sample_memories = [
            {
                "id": "mem_1",
                "content": "User prefers TypeScript over JavaScript",
                "category": "preferences",
                "created_at": "2026-09-20T10:30:00Z",
                "updated_at": "2026-09-20T11:00:00Z",
                "manually_added": True,
                "source": "chat",
                "conversation_id": "conv_123",
            },
            {
                "id": "mem_2",
                "content": "Project deadline is October 15",
                "category": "work",
                "created_at": "2026-09-21T08:15:00Z",
                "manually_added": False,
                "source": "audio",
            },
        ]
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(sample_memories), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(self.db_path)
        try:
            row1 = conn.execute(
                "SELECT content, category, created_at, manually_added, conversation_id FROM memories WHERE id = 'mem_1'"
            ).fetchone()
            self.assertEqual(row1[0], "User prefers TypeScript over JavaScript")
            self.assertEqual(row1[1], "preferences")
            self.assertEqual(row1[2], "2026-09-20 10:30:00")
            self.assertEqual(row1[3], 1)
            self.assertEqual(row1[4], "conv_123")

            row2 = conn.execute(
                "SELECT content, category, manually_added, conversation_id FROM memories WHERE id = 'mem_2'"
            ).fetchone()
            self.assertEqual(row2[0], "Project deadline is October 15")
            self.assertEqual(row2[1], "work")
            self.assertEqual(row2[2], 0)
            self.assertIsNone(row2[3])
        finally:
            conn.close()

    def test_idempotency_and_update(self):
        initial = [{"id": "mem_1", "content": "Initial note", "category": "notes"}]
        json_file1 = self.dir_path / "batch1.json"
        json_file1.write_text(json.dumps(initial), encoding="utf-8")

        load(str(self.db_path), [str(json_file1)])

        updated = [
            {"id": "mem_1", "content": "Updated note", "category": "work"},
            {"id": "mem_2", "content": "New note", "category": "personal"},
        ]
        json_file2 = self.dir_path / "batch2.json"
        json_file2.write_text(json.dumps(updated), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file2)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 1)  # only 1 new
        self.assertEqual(total, 2)

        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute("SELECT content, category FROM memories WHERE id = 'mem_1'").fetchone()
            self.assertEqual(row[0], "Updated note")
            self.assertEqual(row[1], "work")
        finally:
            conn.close()

    def test_wrapper_keys_handling(self):
        wrapped = {
            "memories": [
                {"id": "wm_1", "content": "Wrapped item 1"},
                {"id": "wm_2", "content": "Wrapped item 2"},
            ]
        }
        json_file = self.dir_path / "wrapped.json"
        json_file.write_text(json.dumps(wrapped), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(total, 2)

    def test_missing_id_raises_value_error(self):
        invalid = [{"content": "No ID here"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(json_file)])


if __name__ == "__main__":
    unittest.main()
