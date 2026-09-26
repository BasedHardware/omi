import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys

# Support running directly or within test suite
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import load, SCHEMA, utc_stamp, format_tags, validate_db_path


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

    def test_format_tags(self):
        self.assertEqual(format_tags(["work", "meeting"]), '["work", "meeting"]')
        self.assertEqual(format_tags("work, focus"), '["work", "focus"]')
        self.assertEqual(format_tags('["python", "cli"]'), '["python", "cli"]')
        self.assertIsNone(format_tags(None))
        self.assertIsNone(format_tags([]))

    def test_load_and_query(self):
        sample_memories = [
            {
                "id": "mem_1",
                "content": "Prefers dark mode in all IDEs and terminals",
                "category": "lifestyle",
                "visibility": "private",
                "tags": ["preferences", "ui"],
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:00:00Z",
                "conversation_id": "conv_42"
            },
            {
                "id": "mem_2",
                "content": "KiCad table parsers require escaping quotes in nicknames",
                "category": "learnings",
                "visibility": "public",
                "tags": ["electronics", "eda"],
                "created_at": "2026-09-21T09:00:00Z",
                "updated_at": "2026-09-21T09:30:00Z",
                "conversation_id": None
            }
        ]
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(sample_memories), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(added, 2)
        self.assertEqual(total, 2)

        # Verify database contents
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Query by category
        cursor.execute("SELECT content FROM memories WHERE category = 'learnings'")
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertIn("KiCad table parsers", row[0])

        # Query by visibility
        cursor.execute("SELECT COUNT(*) FROM memories WHERE visibility = 'private'")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Check raw_json and JSON extraction
        cursor.execute("SELECT json_extract(raw_json, '$.category') FROM memories WHERE id = 'mem_1'")
        self.assertEqual(cursor.fetchone()[0], "lifestyle")

        # Check tags stored as JSON array
        cursor.execute("SELECT tags FROM memories WHERE id = 'mem_1'")
        tags = json.loads(cursor.fetchone()[0])
        self.assertEqual(tags, ["preferences", "ui"])

        conn.close()

    def test_wrapped_json_shapes(self):
        wrapped = {
            "memories": [
                {
                    "id": "mem_wrap_1",
                    "content": "Working on Omi SQLite documentation",
                    "category": "work",
                    "created_at": "2026-09-22T10:00:00Z"
                }
            ]
        }
        json_file = self.dir_path / "wrapped.json"
        json_file.write_text(json.dumps(wrapped), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(total, 1)

    def test_idempotence_and_replacement(self):
        batch1 = [
            {"id": "mem_1", "content": "Initial thought", "category": "notes", "created_at": "2026-09-20T08:00:00Z"}
        ]
        batch2 = [
            {"id": "mem_1", "content": "Updated finalized thought", "category": "learnings", "created_at": "2026-09-20T08:00:00Z"},
            {"id": "mem_2", "content": "Second thought", "category": "skills", "created_at": "2026-09-20T10:00:00Z"}
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

        # Check updated content
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT content, category FROM memories WHERE id = 'mem_1'")
        c, cat = cursor.fetchone()
        self.assertEqual(c, "Updated finalized thought")
        self.assertEqual(cat, "learnings")
        conn.close()

    def test_missing_id_raises(self):
        invalid_data = [{"content": "Memory without id"}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(invalid_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])

    def test_traversal_path_rejected(self):
        with self.assertRaises(ValueError):
            validate_db_path("../unsafe.db")

    def test_non_sqlite_file_rejected(self):
        fake_db = self.dir_path / "fake.sqlite"
        fake_db.write_text("THIS IS NOT A SQLITE DATABASE", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_db_path(str(fake_db))


if __name__ == "__main__":
    unittest.main()
