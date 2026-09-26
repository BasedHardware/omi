#!/usr/bin/env python3
"""
Unit tests for sdks/python-cli/examples/memories_to_digest.py
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from memories_to_digest import (
    convert,
    generate_digest,
    load,
    parse_offset,
    parse_time,
    text,
)


class TestMemoriesToDigest(unittest.TestCase):

    def test_text_helper(self):
        self.assertEqual(text("  hello   world  \n"), "hello world")
        self.assertEqual(text(None), "")
        self.assertEqual(text(123), "123")
        self.assertEqual(text(["tag1", "tag2"]), '["tag1", "tag2"]')
        self.assertEqual(text({"key": "val"}), '{"key": "val"}')

    def test_parse_time(self):
        t1 = parse_time("2026-09-20T14:30:00Z")
        self.assertIsNotNone(t1)
        self.assertEqual(t1.year, 2026)
        self.assertEqual(t1.month, 9)
        self.assertEqual(t1.day, 20)
        self.assertEqual(t1.tzinfo, timezone.utc)

        t2 = parse_time("2026-09-20T22:30:00+08:00")
        self.assertIsNotNone(t2)
        self.assertEqual(t2.hour, 14)  # 22:30 +08:00 is 14:30 UTC

        self.assertIsNone(parse_time("invalid-date"))
        self.assertIsNone(parse_time(None))
        self.assertIsNone(parse_time(12345))

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+00:00"), timedelta(0))
        self.assertEqual(parse_offset("+08:00"), timedelta(hours=8))
        self.assertEqual(parse_offset("-05:30"), timedelta(hours=-5, minutes=-30))

        with self.assertRaises(ValueError):
            parse_offset("8")
        with self.assertRaises(ValueError):
            parse_offset("+0800")
        with self.assertRaises(ValueError):
            parse_offset("invalid")

    def test_load_and_deduplicate(self):
        data1 = [
            {"id": "mem_1", "content": "Learned Python 3.12 syntax", "category": "learnings"},
            {"id": "mem_2", "content": "Meeting with client at 2pm", "category": "work"},
        ]
        data2 = [
            {"id": "mem_2", "content": "Updated meeting notes", "category": "work"},
            {"id": "mem_3", "content": "Prefers dark mode in IDEs", "category": "preferences"},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "f1.json"
            p2 = Path(tmpdir) / "f2.json"
            p1.write_text(json.dumps(data1), encoding="utf-8")
            p2.write_text(json.dumps(data2), encoding="utf-8")

            res = load([str(p1), str(p2)])
            self.assertEqual(len(res), 3)
            self.assertIn("mem_1", res)
            self.assertIn("mem_2", res)
            self.assertIn("mem_3", res)
            # Second file overwrite for duplicate ID
            self.assertEqual(res["mem_2"]["content"], "Updated meeting notes")

    def test_load_stdin(self):
        data = [{"id": "mem_stdin", "content": "Piped via stdin"}]
        with patch("sys.stdin", io.StringIO(json.dumps(data))):
            res = load(["-"])
            self.assertEqual(len(res), 1)
            self.assertEqual(res["mem_stdin"]["content"], "Piped via stdin")

    def test_load_invalid_formats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            p_not_found = Path(tmpdir) / "nonexistent.json"
            with self.assertRaises(FileNotFoundError):
                load([str(p_not_found)])

            p_bad_json = Path(tmpdir) / "bad.json"
            p_bad_json.write_text("{corrupt", encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(p_bad_json)])

            p_not_array = Path(tmpdir) / "not_array.json"
            p_not_array.write_text('{"id": "1"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(p_not_array)])

            p_missing_id = Path(tmpdir) / "no_id.json"
            p_missing_id.write_text('[{"content": "missing id"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(p_missing_id)])

    def test_generate_digest_tables_and_sections(self):
        sample_memories = {
            "m1": {
                "id": "m1",
                "content": "Finished implementing SQLite caching",
                "category": "work",
                "created_at": "2026-09-20T10:00:00Z",
                "tags": ["sqlite", "backend", "cache"],
            },
            "m2": {
                "id": "m2",
                "content": "Learned about Rust ownership and lifetimes",
                "category": "learnings",
                "created_at": "2026-09-20T16:00:00Z",
                "tags": ["rust", "study"],
            },
            "m3": {
                "id": "m3",
                "content": "Prefers mechanical keyboards with tactile switches",
                "category": "preferences",
                "created_at": "2026-09-21T09:00:00Z",
                "tags": ["hardware", "gear"],
            },
            "m4": {
                "id": "m4",
                "content": "Meeting summary with design team",
                "category": "work",
                "created_at": "2026-09-21T15:00:00Z",
                "tags": ["design", "backend"],
            },
        }

        output = generate_digest(sample_memories, title="Weekly Second Brain Digest")

        self.assertIn("# Weekly Second Brain Digest", output)
        self.assertIn("**Total Memories**: 4", output)
        self.assertIn("**Active Days**: 2", output)
        self.assertIn("## Daily Activity", output)
        self.assertIn("| 2026-09-21 | 2 |", output)
        self.assertIn("| 2026-09-20 | 2 |", output)

        self.assertIn("## Category Distribution", output)
        self.assertIn("`work`", output)
        self.assertIn("50.0%", output)

        self.assertIn("## Top Knowledge Tags & Themes", output)
        self.assertIn("`#backend`", output)

        self.assertIn("## Recent Knowledge Highlights", output)
        self.assertIn("Prefers mechanical keyboards", output)
        self.assertIn("Learned about Rust ownership", output)

    def test_date_filtering(self):
        sample_memories = {
            "m_old": {
                "id": "m_old",
                "content": "August memory",
                "category": "work",
                "created_at": "2026-08-15T12:00:00Z",
            },
            "m_sept": {
                "id": "m_sept",
                "content": "September memory",
                "category": "work",
                "created_at": "2026-09-10T12:00:00Z",
            },
            "m_future": {
                "id": "m_future",
                "content": "October memory",
                "category": "work",
                "created_at": "2026-10-01T12:00:00Z",
            },
        }

        since_dt = datetime(2026, 9, 1, tzinfo=timezone.utc)
        until_dt = datetime(2026, 9, 30, 23, 59, 59, tzinfo=timezone.utc)

        output = generate_digest(sample_memories, since=since_dt, until=until_dt)
        self.assertIn("**Total Memories**: 1", output)
        self.assertIn("September memory", output)
        self.assertNotIn("August memory", output)
        self.assertNotIn("October memory", output)

    def test_utc_offset_boundary(self):
        sample = {
            "late_night": {
                "id": "late_night",
                "content": "Late night thought",
                "created_at": "2026-09-20T23:30:00Z",
            }
        }
        # UTC 23:30 is 2026-09-20 in UTC
        out_utc = generate_digest(sample, offset=timedelta(0))
        self.assertIn("2026-09-20", out_utc)

        # In +02:00 timezone, it is 01:30 on 2026-09-21
        out_local = generate_digest(sample, offset=timedelta(hours=2))
        self.assertIn("2026-09-21", out_local)

    def test_empty_memories(self):
        output = generate_digest({})
        self.assertIn("**Total Memories**: 0", output)
        self.assertIn("_No memories found matching the specified criteria._", output)

    def test_convert_file_overwrite_protection(self):
        sample = [{"id": "m1", "content": "Memory 1"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "source.json"
            dst = Path(tmpdir) / "digest.md"
            src.write_text(json.dumps(sample), encoding="utf-8")
            dst.write_text("existing content", encoding="utf-8")

            # Without force -> error
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(dst), force=False)

            # With force -> success
            convert([str(src)], str(dst), force=True)
            self.assertIn("Memory 1", dst.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
