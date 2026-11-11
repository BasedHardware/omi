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
text = c2s.text
utc_stamp = c2s.utc_stamp
strip_surrogates = c2s.strip_surrogates


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

    def test_single_conversation_object_import(self):
        """A single exported conversation object must be loaded cleanly into SQLite."""
        single_conv = {
            "id": "conv_single",
            "source": "phone_microphone",
            "started_at": "2026-09-20T10:00:00Z",
            "created_at": "2026-09-20T10:01:00Z",
            "updated_at": "2026-09-20T10:05:00Z",
            "structured": {
                "title": "One-on-one sync",
                "category": "work",
            },
        }
        json_file = self.dir_path / "single_conversation.json"
        json_file.write_text(json.dumps(single_conv), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(added, 1)
        self.assertEqual(total, 1)

        conn = sqlite3.connect(str(self.db_path))
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT title, category FROM conversations WHERE id = 'conv_single'")
            row = cursor.fetchone()
            self.assertEqual(row, ("One-on-one sync", "work"))
        finally:
            conn.close()

    def test_empty_wrapper_import(self):
        """Empty wrapper envelopes (conversations/items/data) must load 0 rows without raising ValueError."""
        for key in ("conversations", "items", "data"):
            db_path = self.dir_path / f"empty_{key}.sqlite"
            json_file = self.dir_path / f"empty_{key}.json"
            json_file.write_text(json.dumps({key: []}), encoding="utf-8")

            loaded, added, total = load(str(db_path), [str(json_file)])
            self.assertEqual(loaded, 0)
            self.assertEqual(added, 0)
            self.assertEqual(total, 0)

    def test_non_dict_structured_does_not_abort_import(self):
        """A 'structured' summary that is not an object must not raise AttributeError.

        The summary is produced upstream and is not schema-validated, so it can arrive
        as a list, string or number. One such record must import with NULL title and
        category rather than aborting the whole page.
        """
        for value, label in (([1, 2, 3], "list"), ("not an object", "string"), (7, "number"), (None, "null")):
            with self.subTest(structured=label):
                db_path = self.dir_path / f"structured_{label}.sqlite"
                json_file = self.dir_path / f"structured_{label}.json"
                json_file.write_text(
                    json.dumps([{"id": f"conv_{label}", "structured": value}]),
                    encoding="utf-8",
                )

                loaded, added, total = load(str(db_path), [str(json_file)])
                self.assertEqual(loaded, 1)
                self.assertEqual(total, 1)

                conn = sqlite3.connect(str(db_path))
                try:
                    row = conn.execute("SELECT title, category FROM conversations").fetchone()
                finally:
                    conn.close()
                self.assertEqual(row, (None, None))

    def test_bad_structured_does_not_block_good_records(self):
        """A malformed 'structured' value must not drop the valid records beside it."""
        records = [
            {"id": "good_before", "structured": {"title": "Valid", "category": "work"}},
            {"id": "bad", "structured": ["not", "an", "object"]},
            {"id": "good_after", "structured": {"title": "Also valid", "category": "personal"}},
        ]
        json_file = self.dir_path / "mixed.json"
        json_file.write_text(json.dumps(records), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 3)
        self.assertEqual(total, 3)

        conn = sqlite3.connect(str(self.db_path))
        try:
            titles = dict(conn.execute("SELECT id, title FROM conversations").fetchall())
        finally:
            conn.close()
        self.assertEqual(titles["good_before"], "Valid")
        self.assertEqual(titles["good_after"], "Also valid")
        self.assertIsNone(titles["bad"])

    def test_non_string_fields_are_coerced_to_text(self):
        """dict/list/str fields are coerced to text so sqlite3 can bind them.

        sqlite3 raises "type 'dict' is not supported" for non-text parameters, which
        would abort the import over a single loosely typed field.
        """
        record = {
            "id": "conv_loose",
            "structured": {"title": {"nested": "dict"}, "category": ["work", "urgent"]},
            "source": {"kind": "phone"},
            "transcript": {"segments": [{"text": "hi"}]},
        }
        json_file = self.dir_path / "loose.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(total, 1)

        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT title, category, source, transcript FROM conversations").fetchone()
        finally:
            conn.close()
        for value in row:
            self.assertIsInstance(value, str)
        self.assertIn("nested", row[0])
        self.assertIn("urgent", row[1])

    def test_lone_surrogate_does_not_abort_import(self):
        """Lone surrogates from a malformed export must not raise UnicodeEncodeError.

        json.loads accepts "\\ud800", but neither sqlite3 nor a UTF-8 write can encode it.
        """
        record = {"id": "conv_surrogate", "structured": {"title": "bad \ud800 title", "category": "work"}}
        json_file = self.dir_path / "surrogate.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(total, 1)

        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT title, raw_json FROM conversations").fetchone()
        finally:
            conn.close()
        # The surrogate is dropped, the surrounding text survives.
        self.assertIn("bad", row[0])
        self.assertIn("title", row[1])
        # The stored raw_json must be valid UTF-8 encodable.
        row[1].encode("utf-8")

    def test_strip_surrogates_drops_rather_than_replaces(self):
        """A lone surrogate is removed, not substituted with a '?' placeholder.

        errors="replace" would insert '?' and silently alter the imported text
        even though the function is documented to drop the code point.
        """
        self.assertEqual(strip_surrogates("bad \ud800 title"), "bad  title")
        self.assertNotIn("?", strip_surrogates("bad \ud800 title"))
        self.assertEqual(strip_surrogates("clean text"), "clean text")

    def test_lone_surrogate_in_id_does_not_abort_import(self):
        """The id is sanitized too: an unencodable id must not raise UnicodeEncodeError."""
        record = {"id": "conv_\ud800id", "structured": {"title": "t"}}
        json_file = self.dir_path / "surrogate_id.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual((loaded, total), (1, 1))

        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT id FROM conversations").fetchone()
        finally:
            conn.close()
        self.assertEqual(row[0], "conv_id")
        row[0].encode("utf-8")

    def test_utc_stamp_keeps_falsy_non_string_values(self):
        """Only None/'' map to NULL; 0, False, [] and {} stay queryable as text."""
        self.assertEqual(utc_stamp(0), "0")
        self.assertEqual(utc_stamp(False), "False")
        self.assertEqual(utc_stamp([]), "[]")
        self.assertEqual(utc_stamp({}), "{}")
        # None and the empty string still become NULL for date functions.
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))

    def test_non_string_timestamps_are_coerced(self):
        """A non-string timestamp is stored as text instead of raising."""
        record = {"id": "conv_ts", "started_at": 12345, "created_at": ["2026"], "structured": {"title": "t"}}
        json_file = self.dir_path / "timestamps.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        loaded, _, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 1)
        self.assertEqual(total, 1)

        conn = sqlite3.connect(str(self.db_path))
        try:
            row = conn.execute("SELECT started_at, created_at FROM conversations").fetchone()
        finally:
            conn.close()
        # A list is rendered with str(), matching the scalar coercion path.
        self.assertEqual(row, ("12345", "['2026']"))

    def test_text_helper_coercion(self):
        """text() coerces loosely typed values and passes None through as NULL."""
        self.assertIsNone(text(None))
        self.assertEqual(text("plain"), "plain")
        self.assertEqual(text({"a": 1}), '{"a": 1}')
        self.assertEqual(text([1, 2]), "[1, 2]")
        self.assertEqual(text(12345), "12345")
        self.assertEqual(text(True), "True")

    def test_half_hour_offset_is_normalised_to_utc(self):
        """A +05:30 offset is accepted and normalised to UTC rather than dropped."""
        record = {"id": "conv_tz", "started_at": "2026-01-01T00:00:00+05:30", "structured": {"title": "t"}}
        json_file = self.dir_path / "tz.json"
        json_file.write_text(json.dumps([record]), encoding="utf-8")

        load(str(self.db_path), [str(json_file)])
        conn = sqlite3.connect(str(self.db_path))
        try:
            # 00:00 at +05:30 is 18:30 UTC on the previous day.
            self.assertEqual(
                conn.execute("SELECT started_at FROM conversations").fetchone()[0],
                "2025-12-31 18:30:00",
            )
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
