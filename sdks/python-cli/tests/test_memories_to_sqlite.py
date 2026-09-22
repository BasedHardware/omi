"""Tests for memories_to_sqlite recipe (PR #15142).

Covers: UTC normalisation, tag formatting, load+query, idempotence,
and ValueError on records missing a required id field.
Uses importlib.util.spec_from_file_location to match the project
convention established in test_memories_to_markdown.py.
"""

from __future__ import annotations

import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

# Load memories_to_sqlite example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_sqlite.py"
spec = importlib.util.spec_from_file_location("memories_to_sqlite", script_path)
m2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2s)

load = m2s.load
utc_stamp = m2s.utc_stamp
format_tags = m2s.format_tags


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

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'work'")
        self.assertEqual(cursor.fetchone()[0], 1)

        cursor.execute("SELECT content FROM memories WHERE tags LIKE '%roadmap%'")
        self.assertEqual(cursor.fetchone()[0], "Discussed roadmap with team in morning sync.")

        cursor.execute("SELECT COUNT(*) FROM memories WHERE manually_added = 1")
        self.assertEqual(cursor.fetchone()[0], 1)

        conn.close()

    def test_idempotence(self):
        batch1 = [
            {"id": "mem_1", "content": "Initial memory", "category": "notes", "created_at": "2026-09-20T08:00:00Z"}
        ]
        batch2 = [
            {"id": "mem_1", "content": "Updated memory", "category": "notes", "created_at": "2026-09-20T08:00:00Z"},
            {"id": "mem_2", "content": "Another memory", "category": "notes", "created_at": "2026-09-20T10:00:00Z"},
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

    def test_missing_id_raises_value_error(self):
        """Records without an id field must raise ValueError before touching the DB."""
        bad_data = [{"content": "No id field here", "category": "notes"}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])

        # DB must not have been created / written to
        self.assertFalse(self.db_path.exists())


if __name__ == "__main__":
    unittest.main()
