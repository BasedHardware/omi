"""Tests for memories_to_sqlite recipe.

Covers: UTC normalisation, load+query, multi-page merge, idempotence,
ValueError on records missing a required id field, and path-safety guards.
Uses importlib.util.spec_from_file_location to match the project convention
established in test_memories_to_markdown.py.
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
text = m2s.text
utc_stamp = m2s.utc_stamp
strip_surrogates = m2s.strip_surrogates


SAMPLE_MEMORIES = [
    {
        "id": "mem_01_work",
        "category": "work",
        "visibility": "private",
        "content": "Prefers asynchronous communication for architecture proposals.",
        "tags": ["workflow", "management"],
        "created_at": "2026-09-15T10:30:00Z",
    },
    {
        "id": "mem_02_skills",
        "category": "skills",
        "visibility": "public",
        "content": "Proficient in Python standard library.",
        "tags": ["python"],
        "created_at": "2026-09-16T14:15:00+02:00",
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
        self.assertEqual(utc_stamp("2026-09-20T11:00:00Z"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp("2026-09-20T13:00:00+02:00"), "2026-09-20 11:00:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))

    def test_load_and_query(self):
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 2)
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'work'")
            self.assertEqual(cursor.fetchone()[0], 1)

            cursor.execute("SELECT id FROM memories WHERE content LIKE '%architecture%'")
            self.assertEqual(cursor.fetchone()[0], "mem_01_work")

            # +02:00 offset should normalise to 12:15 UTC
            cursor.execute("SELECT created_at FROM memories WHERE id = 'mem_02_skills'")
            self.assertEqual(cursor.fetchone()[0], "2026-09-16 12:15:00")

            # tags are semicolon-joined and searchable
            cursor.execute("SELECT tags FROM memories WHERE id = 'mem_01_work'")
            self.assertEqual(cursor.fetchone()[0], "workflow;management")

            cursor.execute(
                "SELECT json_extract(raw_json, '$.visibility') FROM memories WHERE id = 'mem_01_work'"
            )
            self.assertEqual(cursor.fetchone()[0], "private")
        finally:
            conn.close()

    def test_idempotence(self):
        batch1 = [SAMPLE_MEMORIES[0]]
        batch2 = [
            {**SAMPLE_MEMORIES[0], "content": "Prefers asynchronous communication, updated."},
            SAMPLE_MEMORIES[1],
        ]
        f1 = self.dir_path / "p1.json"
        f2 = self.dir_path / "p2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        _, _, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT content FROM memories WHERE id = 'mem_01_work'")
            self.assertEqual(cursor.fetchone()[0], "Prefers asynchronous communication, updated.")
        finally:
            conn.close()

    def test_missing_id_raises_value_error(self):
        """Records without an id field must raise ValueError before DB is opened."""
        bad_data = [{"category": "work", "content": "No ID"}]
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
        self.assertEqual(loaded, 2)
        self.assertEqual(total, 2)

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

    def test_single_memory_object_import(self):
        """A single exported memory object must be loaded cleanly into SQLite."""
        single = {
            "id": "mem_single",
            "category": "learnings",
            "visibility": "private",
            "content": "A lone memory.",
            "tags": ["solo"],
            "created_at": "2026-09-20T10:00:00Z",
        }
        json_file = self.dir_path / "single.json"
        json_file.write_text(json.dumps(single), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(added, 1)
        self.assertEqual(total, 1)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT category, content FROM memories WHERE id = 'mem_single'")
            row = cursor.fetchone()
            self.assertEqual(row, ("learnings", "A lone memory."))
        finally:
            conn.close()

    def test_empty_wrapper_import(self):
        """Empty wrapper envelopes (memories/items/data) must load 0 rows without raising ValueError."""
        for key in ("memories", "items", "data"):
            db_path = self.dir_path / f"empty_{key}.sqlite"
            json_file = self.dir_path / f"empty_{key}.json"
            json_file.write_text(json.dumps({key: []}), encoding="utf-8")

            loaded, added, total = load(str(db_path), [str(json_file)])
            self.assertEqual(loaded, 0)
            self.assertEqual(added, 0)
            self.assertEqual(total, 0)

    def test_non_string_fields_are_coerced_to_text(self):
        """dict/list fields are coerced to text so sqlite3 can bind them."""
        record = {
            "id": "mem_loose",
            "content": {"text": "nested"},
            "category": ["work", "urgent"],
            "visibility": {"level": "private"},
            "tags": "not-a-list",
        }
        json_file = self.dir_path / "loose.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(total, 1)

        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT content, category, visibility, tags FROM memories").fetchone()
        finally:
            conn.close()
        for value in row:
            self.assertIsInstance(value, str)
        self.assertIn("nested", row[0])
        self.assertIn("urgent", row[1])

    def test_lone_surrogate_does_not_abort_import(self):
        """Lone surrogates from a malformed export must not raise UnicodeEncodeError."""
        record = {"id": "mem_surrogate", "content": "bad \ud800 content", "category": "work"}
        json_file = self.dir_path / "surrogate.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(total, 1)

        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT content, raw_json FROM memories").fetchone()
        finally:
            conn.close()
        self.assertIn("bad", row[0])
        self.assertIn("content", row[1])
        row[1].encode("utf-8")

    def test_lone_surrogate_in_id_does_not_abort_import(self):
        """The id is sanitized too: an unencodable id must not raise UnicodeEncodeError."""
        record = {"id": "mem_\ud800id", "content": "t"}
        json_file = self.dir_path / "surrogate_id.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual((loaded, total), (1, 1))

        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT id FROM memories").fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], "mem_id")
        row[0].encode("utf-8")

    def test_text_helper_coercion(self):
        """text() coerces loosely typed values and passes None through as NULL."""
        self.assertIsNone(text(None))
        self.assertEqual(text("plain"), "plain")
        self.assertEqual(text({"a": 1}), '{"a": 1}')
        self.assertEqual(text([1, 2]), "[1, 2]")
        self.assertEqual(text(12345), "12345")
        self.assertEqual(text(True), "True")

    def test_strip_surrogates_drops_rather_than_replaces(self):
        """A lone surrogate is removed, not substituted with a '?' placeholder."""
        self.assertEqual(strip_surrogates("bad \ud800 content"), "bad  content")
        self.assertNotIn("?", strip_surrogates("bad \ud800 content"))
        self.assertEqual(strip_surrogates("clean text"), "clean text")

    def test_tags_list_becomes_semicolon_joined(self):
        """A list tags field renders as a semicolon-joined string; non-list passes through."""
        record = {
            "id": "mem_tags",
            "content": "t",
            "tags": ["a", "b", "c"],
        }
        json_file = self.dir_path / "tags.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        load(str(self.db_path), [str(json_file)])
        conn = sqlite3.connect(str(self.db_path))
        try:
            self.assertEqual(conn.execute("SELECT tags FROM memories").fetchone()[0], "a;b;c")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
