"""Tests for conversations_to_sqlite recipe.

Covers: UTC normalisation, load+query, multi-page merge, idempotence,
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

# Load conversations_to_sqlite example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_sqlite.py"
spec = importlib.util.spec_from_file_location("conversations_to_sqlite", script_path)
c2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2s)

load = c2s.load
utc_stamp = c2s.utc_stamp


SAMPLE_CONVERSATIONS = [
    {
        "id": "conv_1",
        "source": "phone_microphone",
        "started_at": "2026-09-20T09:00:00Z",
        "created_at": "2026-09-20T09:01:00Z",
        "updated_at": "2026-09-20T09:05:00Z",
        "structured": {
            "title": "Team standup",
            "category": "work",
        },
    },
    {
        "id": "conv_2",
        "source": "phone_microphone",
        "started_at": "2026-09-20T14:00:00+02:00",
        "created_at": "2026-09-20T14:01:00+02:00",
        "updated_at": "2026-09-20T14:05:00+02:00",
        "structured": {
            "title": "Doctor appointment",
            "category": "personal",
        },
    },
]


class TestConversationsToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_conversations.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T11:00:00Z"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp("2026-09-20T13:00:00+02:00"), "2026-09-20 11:00:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))

    def test_load_and_query(self):
        json_file = self.dir_path / "conversations.json"
        json_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()

            # Check category filter
            cursor.execute("SELECT COUNT(*) FROM conversations WHERE category = 'work'")
            self.assertEqual(cursor.fetchone()[0], 1)

            # Check title search
            cursor.execute("SELECT id FROM conversations WHERE title LIKE '%standup%'")
            self.assertEqual(cursor.fetchone()[0], "conv_1")

            # Check UTC normalisation: +02:00 offset should become 12:00 UTC
            cursor.execute("SELECT started_at FROM conversations WHERE id = 'conv_2'")
            self.assertEqual(cursor.fetchone()[0], "2026-09-20 12:00:00")

            # Check json_extract on raw_json
            cursor.execute(
                "SELECT json_extract(raw_json, '$.structured.category') FROM conversations WHERE id = 'conv_1'"
            )
            self.assertEqual(cursor.fetchone()[0], "work")
        finally:
            conn.close()

    def test_idempotence(self):
        batch1 = [SAMPLE_CONVERSATIONS[0]]
        batch2 = [
            {**SAMPLE_CONVERSATIONS[0], "structured": {"title": "Updated standup", "category": "work"}},
            SAMPLE_CONVERSATIONS[1],
        ]
        f1 = self.dir_path / "p1.json"
        f2 = self.dir_path / "p2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        _, _, total = load(str(self.db_path), [str(f2)])

        # Should have 2 distinct rows, not 3
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT title FROM conversations WHERE id = 'conv_1'")
            self.assertEqual(cursor.fetchone()[0], "Updated standup")
        finally:
            conn.close()

    def test_missing_id_raises_value_error(self):
        """Records without an id field must raise ValueError before DB is opened."""
        bad_data = [{"source": "phone_microphone", "structured": {"title": "No ID"}}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(bad_data), encoding="utf-8")

        with self.assertRaises(ValueError):
            load(str(self.db_path), [str(bad_file)])

        self.assertFalse(self.db_path.exists())

    def test_wrapped_object_input(self):
        """Input wrapped as {'conversations': [...]} should be unwrapped."""
        wrapped = {"conversations": SAMPLE_CONVERSATIONS}
        json_file = self.dir_path / "wrapped.json"
        json_file.write_text(json.dumps(wrapped), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(total, 2)


    def test_path_traversal_rejected(self):
        """Paths containing '..' must be rejected before any DB is opened."""
        json_file = self.dir_path / "conversations.json"
        json_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")

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

        json_file = self.dir_path / "conversations.json"
        json_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")

        with self.assertRaises(ValueError, msg="Expected ValueError when output is not SQLite"):
            load(str(not_a_db), [str(json_file)])

        self.assertEqual(not_a_db.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
