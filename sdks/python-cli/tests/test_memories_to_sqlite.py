"""Tests for memories to SQLite exporter.

Pins schema integrity, timestamp normalization, idempotence,
category indexing, json_extract compatibility, and error handling.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Add examples and tests directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_sqlite import SCHEMA, boolean_to_int, load, rows_from, utc_stamp


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.db_path = self.dir_path / "test_memories.sqlite"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-24T10:30:00Z"), "2026-09-24 10:30:00")
        self.assertEqual(utc_stamp("2026-09-24T12:30:00+02:00"), "2026-09-24 10:30:00")
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))
        self.assertIsNone(utc_stamp("invalid-date"))

    def test_boolean_to_int(self):
        self.assertEqual(boolean_to_int(True), 1)
        self.assertEqual(boolean_to_int(False), 0)
        self.assertEqual(boolean_to_int("true"), 1)
        self.assertEqual(boolean_to_int("1"), 1)
        self.assertEqual(boolean_to_int("yes"), 1)
        self.assertEqual(boolean_to_int("false"), 0)
        self.assertEqual(boolean_to_int(None), 0)

    def test_load_and_query(self):
        sample_memories = [
            {
                "id": "mem_01",
                "content": "Prefers oat milk cortado",
                "category": "lifestyle",
                "created_at": "2026-09-24T08:00:00Z",
                "updated_at": "2026-09-24T08:00:00Z",
                "manually_added": False,
            },
            {
                "id": "mem_02",
                "content": "Working on Soroban smart contract verification",
                "category": "work",
                "created_at": "2026-09-24T09:00:00Z",
                "updated_at": "2026-09-24T09:30:00Z",
                "manually_added": True,
            },
            {
                "id": "mem_03",
                "content": "Favorite editor theme is Dracula 🧛",
                "category": "preferences",
                "created_at": "2026-09-24T10:00:00Z",
                "updated_at": "2026-09-24T10:00:00Z",
                "manually_added": False,
            },
        ]
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(sample_memories), encoding="utf-8")

        loaded, added, total = load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 3)
        self.assertEqual(added, 3)
        self.assertEqual(total, 3)

        # Connect and verify
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()

        # Check total count
        cursor.execute("SELECT COUNT(*) FROM memories")
        self.assertEqual(cursor.fetchone()[0], 3)

        # Check category filtering
        cursor.execute("SELECT COUNT(*) FROM memories WHERE category = 'work'")
        self.assertEqual(cursor.fetchone()[0], 1)

        # Check keyword search
        cursor.execute("SELECT id FROM memories WHERE content LIKE '%cortado%'")
        self.assertEqual(cursor.fetchone()[0], "mem_01")

        # Check json_extract from raw_json
        cursor.execute("SELECT json_extract(raw_json, '$.category') FROM memories WHERE id = 'mem_03'")
        self.assertEqual(cursor.fetchone()[0], "preferences")

        conn.close()

    def test_idempotence_and_replacement(self):
        batch1 = [
            {"id": "mem_01", "content": "Initial thought", "category": "notes", "created_at": "2026-09-24T08:00:00Z"}
        ]
        batch2 = [
            {"id": "mem_01", "content": "Updated refined thought", "category": "notes", "created_at": "2026-09-24T08:00:00Z"},
            {"id": "mem_02", "content": "New memory", "category": "work", "created_at": "2026-09-24T09:00:00Z"}
        ]
        f1 = self.dir_path / "b1.json"
        f2 = self.dir_path / "b2.json"
        f1.write_text(json.dumps(batch1), encoding="utf-8")
        f2.write_text(json.dumps(batch2), encoding="utf-8")

        load(str(self.db_path), [str(f1)])
        loaded, added, total = load(str(self.db_path), [str(f2)])

        self.assertEqual(loaded, 2)
        self.assertEqual(added, 1)  # Only mem_02 is new
        self.assertEqual(total, 2)

        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM memories WHERE id = 'mem_01'")
        self.assertEqual(cursor.fetchone()[0], "Updated refined thought")
        conn.close()

    def test_wrapped_json_and_bom(self):
        data = {
            "memories": [
                {"id": "mem_wrapped_1", "content": "Wrapped item", "category": "test"}
            ]
        }
        f = self.dir_path / "wrapped.json"
        # Write with UTF-8 BOM
        f.write_bytes(b"\xef\xbb\xbf" + json.dumps(data).encode("utf-8"))

        loaded, added, total = load(str(self.db_path), [str(f)])
        self.assertEqual(loaded, 1)
        self.assertEqual(added, 1)
        self.assertEqual(total, 1)

    def test_error_handling(self):
        # Missing id
        bad_item = [{"content": "No ID here"}]
        f_bad = self.dir_path / "bad.json"
        f_bad.write_text(json.dumps(bad_item), encoding="utf-8")
        with self.assertRaises(ValueError):
            rows_from(str(f_bad))

        # Not a list or valid dict
        f_invalid = self.dir_path / "invalid.json"
        f_invalid.write_text(json.dumps("just a string"), encoding="utf-8")
        with self.assertRaises(ValueError):
            rows_from(str(f_invalid))

        # Empty file
        f_empty = self.dir_path / "empty.json"
        f_empty.write_text("", encoding="utf-8")
        with self.assertRaises(ValueError):
            rows_from(str(f_empty))


if __name__ == "__main__":
    unittest.main()
