"""Hermetic unit tests for memories_to_parquet.py recipe."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add examples directory to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from memories_to_parquet import (
    HAS_PYARROW,
    SCHEMA_FIELDS,
    convert,
    normalize_record,
    validate_path,
)

if HAS_PYARROW:
    import pyarrow.parquet as pq


class TestMemoriesToParquet(unittest.TestCase):
    def test_normalize_record(self):
        item = {
            "id": "mem_1",
            "content": "Quick brown fox jumps",
            "category": "learning",
            "visibility": "private",
            "tags": ["fox", "quick"],
            "created_at": "2026-09-17T12:00:00Z",
            "manually_added": True,
        }
        norm = normalize_record(item)
        self.assertEqual(norm["id"], "mem_1")
        self.assertEqual(norm["category"], "learning")
        self.assertEqual(norm["tags"], ["fox", "quick"])
        self.assertEqual(norm["char_len"], 21)
        self.assertEqual(norm["word_count"], 4)
        self.assertTrue(norm["manually_added"])
        self.assertFalse(norm["reviewed"])
        self.assertFalse(norm["edited"])

    def test_validate_path(self):
        self.assertEqual(validate_path("safe/path.parquet"), Path("safe/path.parquet"))
        with self.assertRaises(ValueError):
            validate_path("../traversal.parquet")

    def test_schema_fields(self):
        field_names = [f[0] for f in SCHEMA_FIELDS]
        self.assertIn("id", field_names)
        self.assertIn("content", field_names)
        self.assertIn("char_len", field_names)
        self.assertIn("word_count", field_names)
        # Ensure no phantom fields
        self.assertNotIn("user_id", field_names)
        self.assertNotIn("conversation_id", field_names)

    @unittest.skipUnless(HAS_PYARROW, "pyarrow required for Parquet conversion tests")
    def test_convert_memories_to_parquet_e2e(self):
        sample = [
            {
                "id": "mem_100",
                "content": "Meeting with engineering team",
                "category": "work",
                "visibility": "private",
                "tags": ["work", "meeting"],
                "created_at": "2026-09-17T14:00:00Z",
                "updated_at": "2026-09-17T15:00:00Z",
                "manually_added": True,
                "reviewed": False,
                "edited": False,
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sample.json"
            dst = Path(tmpdir) / "sample.parquet"
            src.write_text(json.dumps(sample), encoding="utf-8")

            count = convert(src, dst)
            self.assertEqual(count, 1)
            self.assertTrue(dst.exists())

            table = pq.read_table(dst)
            self.assertEqual(table.num_rows, 1)
            self.assertIn("id", table.column_names)
            self.assertIn("content", table.column_names)
            self.assertIn("word_count", table.column_names)
            self.assertEqual(table["id"][0].as_py(), "mem_100")
            self.assertEqual(table["word_count"][0].as_py(), 4)

    @unittest.skipUnless(HAS_PYARROW, "pyarrow required for Parquet conversion tests")
    def test_envelope_unwrapping(self):
        envelope = {
            "memories": [
                {"id": "m1", "content": "Memory 1"},
                {"id": "m2", "content": "Memory 2"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "envelope.json"
            dst = Path(tmpdir) / "envelope.parquet"
            src.write_text(json.dumps(envelope), encoding="utf-8")

            count = convert(src, dst)
            self.assertEqual(count, 2)
            table = pq.read_table(dst)
            self.assertEqual(table.num_rows, 2)

    @unittest.skipUnless(HAS_PYARROW, "pyarrow required for Parquet conversion tests")
    def test_real_cli_memory_shape(self):
        # Exact payload shape emitted by `omi --json memory list --limit 200`
        real_payload = [
            {
                "id": "66432b0e-9276-42d4-a15e-5b1fa85149c4",
                "content": "User prefers dark mode interfaces.",
                "category": "preference",
                "visibility": "private",
                "tags": ["ui", "settings"],
                "created_at": "2026-09-17T10:30:00Z",
                "updated_at": "2026-09-17T10:30:00Z",
                "manually_added": False,
                "reviewed": True,
                "edited": False,
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "real.json"
            dst = Path(tmpdir) / "real.parquet"
            src.write_text(json.dumps(real_payload), encoding="utf-8")

            count = convert(src, dst)
            self.assertEqual(count, 1)
            table = pq.read_table(dst)
            self.assertEqual(table["category"][0].as_py(), "preference")
            self.assertEqual(table["char_len"][0].as_py(), 34)

    @unittest.skipUnless(HAS_PYARROW, "pyarrow required for Parquet conversion tests")
    def test_compression_options(self):
        sample = [{"id": "m1", "content": "Test compression"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "comp.json"
            src.write_text(json.dumps(sample), encoding="utf-8")

            for codec in ("snappy", "gzip", "none"):
                dst = Path(tmpdir) / f"comp_{codec}.parquet"
                count = convert(src, dst, compression=codec)
                self.assertEqual(count, 1)
                self.assertTrue(dst.exists())

    @unittest.skipUnless(HAS_PYARROW, "pyarrow required for Parquet conversion tests")
    def test_overwrite_behavior(self):
        sample = [{"id": "m1", "content": "Memory"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "mem.json"
            dst = Path(tmpdir) / "mem.parquet"
            src.write_text(json.dumps(sample), encoding="utf-8")

            convert(src, dst)
            self.assertTrue(dst.exists())

            with self.assertRaises(FileExistsError):
                convert(src, dst, overwrite=False)

            convert(src, dst, overwrite=True)
            self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
