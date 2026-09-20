import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Add parent directories to import path if needed
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import load, SCHEMA, boolean_to_int, format_tags, utc_stamp


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_memories.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T11:00:00Z"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp("2026-09-20T13:00:00+02:00"), "2026-09-20 11:00:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))

    def test_format_tags(self):
        self.assertEqual(format_tags(["work", "urgent", "project-x"]), "work; urgent; project-x")
        self.assertEqual(format_tags(None), "")
        self.assertEqual(format_tags("single-tag"), "single-tag")

    def test_load_and_query(self):
        sample_memories = [
            {
                "id": "mem_1",
                "category": "work",
                "visibility": "private",
                "content": "Discussed roadmap with team in morning sync.",
                "tags": ["meeting", "roadmap"],
                "manually_added": False,
                "reviewed": True,
                "created_at": "2026-09-20T09:00:00Z",
                "updated_at": "2026-09-20T09:00:00Z",
            },
            {
                "id": "mem_2",
                "category": "personal",
                "visibility": "private",
                "content": "Doctor appointment scheduled for next Tuesday.",
                "tags": ["health"],
                "manually_added": True,
                "reviewed": True,
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-20T10:00:00Z",
            },
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

        # Check count by category
        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'work'")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Check tag search
        cursor.execute("SELECT content FROM memories WHERE tags LIKE '%roadmap%'")
        self.assertEqual(cursor.fetchone()[0], "Discussed roadmap with team in morning sync.")

        # Check manually_added query
        cursor.execute("SELECT COUNT(*) FROM memories WHERE manually_added = 1")
        self.assertEqual(cursor.fetchone()[0], 1)

        conn.close()

    def test_idempotence(self):
        batch1 = [
            {"id": "mem_1", "content": "Initial memory", "category": "notes", "created_at": "2026-09-20T08:00:00Z"}
        ]
        batch2 = [
            {"id": "mem_1", "content": "Updated memory", "category": "notes", "created_at": "2026-09-20T08:00:00Z"},
            {"id": "mem_2", "content": "Another memory", "category": "notes", "created_at": "2026-09-20T10:00:00Z"}
        ]
        f1 = self.dir_path / "m1.json"
        f2 = self.dir_path / "m2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 2)
        self.assertEqual(added, 1)  # Only mem_2 is new
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM memories WHERE id = 'mem_1'")
        self.assertEqual(cursor.fetchone()[0], "Updated memory")
        conn.close()


if __name__ == "__main__":
    unittest.main()
