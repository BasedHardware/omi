"""Tests for memories_to_sqlite recipe.

Covers: UTC normalisation, tags parsing, load+query, multi-page merge, idempotence,
wrapped objects, path traversal rejection, non-SQLite overwrite rejection,
and ValueError on records missing a required id field.
Uses importlib.util.spec_from_file_location matching project conventions.
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
parse_tags = m2s.parse_tags


SAMPLE_MEMORIES = [
    {
        "id": "mem_01_work",
        "category": "work",
        "visibility": "private",
        "content": "Prefers asynchronous communication for architecture proposals.",
        "tags": ["workflow", "management"],
        "created_at": "2026-09-15T10:30:00Z",
        "updated_at": "2026-09-15T10:35:00Z",
    },
    {
        "id": "mem_02_skills",
        "category": "skills",
        "visibility": "public",
        "content": "Proficient in Python standard library and KiCad S-expressions.",
        "tags": ["python", "kicad"],
        "created_at": "2026-09-16T14:15:00+02:00",
        "updated_at": "2026-09-16T14:20:00+02:00",
    },
    {
        "id": "mem_03_learnings",
        "category": "learnings",
        "visibility": "private",
        "content": "KiCad library table nicknames require escaping double quotes.",
        "tags": ["eda", "electronics"],
        "created_at": "2026-09-17T09:00:00Z",
        "updated_at": "2026-09-17T09:05:00Z",
    },
]


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_memories.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-15T10:30:00Z"), "2026-09-15 10:30:00")
        self.assertEqual(utc_stamp("2026-09-16T14:15:00+02:00"), "2026-09-16 12:15:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))

    def test_parse_tags(self):
        self.assertEqual(parse_tags(["python", "sqlite"]), "python,sqlite")
        self.assertEqual(parse_tags("single_tag"), "single_tag")
        self.assertIsNone(parse_tags(None))
        self.assertIsNone(parse_tags([]))

    def test_load_and_query(self):
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 3)
        self.assertEqual(added, 3)
        self.assertEqual(total, 3)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()

            # Check category filter
            cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'work'")
            self.assertEqual(cursor.fetchone()[0], 1)

            # Check content search
            cursor.execute("SELECT id FROM memories WHERE content LIKE '%KiCad%'")
            rows = [r[0] for r in cursor.fetchall()]
            self.assertIn("mem_02_skills", rows)
            self.assertIn("mem_03_learnings", rows)

            # Check UTC normalisation: +02:00 offset should become 12:15:00 UTC
            cursor.execute("SELECT created_at FROM memories WHERE id = 'mem_02_skills'")
            self.assertEqual(cursor.fetchone()[0], "2026-09-16 12:15:00")

            # Check json_extract on raw_json
            cursor.execute(
                "SELECT json_extract(raw_json, '$.visibility') FROM memories WHERE id = 'mem_01_work'"
            )
            self.assertEqual(cursor.fetchone()[0], "private")

            # Check tags field
            cursor.execute("SELECT tags FROM memories WHERE id = 'mem_01_work'")
            self.assertEqual(cursor.fetchone()[0], "workflow,management")
        finally:
            conn.close()

    def test_idempotence(self):
        batch1 = [SAMPLE_MEMORIES[0]]
        batch2 = [
            {**SAMPLE_MEMORIES[0], "content": "Updated async communication note"},
            SAMPLE_MEMORIES[1],
        ]
        f1 = self.dir_path / "m1.json"
        f2 = self.dir_path / "m2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        _, _, total = load(str(self.db_path), [str(f2)])

        # Should have 2 distinct rows, not 3
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM memories WHERE id = 'mem_01_work'")
            self.assertEqual(cursor.fetchone()[0], "Updated async communication note")
        finally:
            conn.close()

    def test_missing_id_raises_value_error(self):
        """Records without an id field must raise ValueError before DB is opened."""
        bad_data = [{"content": "Memory without an id", "category": "work"}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])

        self.assertFalse(self.db_path.exists())

    def test_wrapped_object_input(self):
        """Input wrapped as {'memories': [...]} should be unwrapped."""
        wrapped = {"memories": SAMPLE_MEMORIES}
        json_file = self.dir_path / "wrapped.json"
        json_file.write_text(json.dumps(wrapped), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 3)
        self.assertEqual(total, 3)

    def test_path_traversal_rejected(self):
        """Paths containing '..' must be rejected before any DB is opened."""
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")

        escape = self.dir_path.parent / "escape.db"
        existed = escape.exists()
        try:
            with self.assertRaises(ValueError, msg="Expected ValueError for '..' in path"):
                load(str(self.dir_path / ".." / "escape.db"), [str(json_file)])
            if not existed:
                self.assertFalse(escape.exists())
        finally:
            if not existed and escape.exists():
                escape.unlink()

    def test_non_sqlite_file_rejected(self):
        """Overwriting an existing file that is not a SQLite database must raise ValueError."""
        not_a_db = self.dir_path / "output.db"
        original = b"This is not a SQLite file at all"
        not_a_db.write_bytes(original)

        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")

        with self.assertRaises(ValueError, msg="Expected ValueError when output is not SQLite"):
            load(str(not_a_db), [str(json_file)])

        self.assertEqual(not_a_db.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
