#!/usr/bin/env python3
"""
Unit tests for sdks/python-cli/examples/action_items_to_digest.py
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import sys
from pathlib import Path

# Add examples and tests directory to sys.path so pytest discovers example modules in CI
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_digest import (
    convert,
    generate_digest,
    is_completed,
    load,
    parse_offset,
    parse_time,
    text,
)


class TestActionItemsToDigest(unittest.TestCase):

    def test_text_helper(self):
        self.assertEqual(text("  clean   inbox  \n"), "clean inbox")
        self.assertEqual(text(None), "")
        self.assertEqual(text(42), "42")
        self.assertEqual(text(["item1", "item2"]), '["item1", "item2"]')
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
        self.assertEqual(t2.hour, 14)

        self.assertIsNone(parse_time("invalid-time"))
        self.assertIsNone(parse_time(None))
        self.assertIsNone(parse_time(""))

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+00:00"), timedelta(0))
        self.assertEqual(parse_offset("+08:00"), timedelta(hours=8))
        self.assertEqual(parse_offset("-05:00"), timedelta(hours=-5))

        with self.assertRaises(ValueError):
            parse_offset("+8")
        with self.assertRaises(ValueError):
            parse_offset("+0800")
        with self.assertRaises(ValueError):
            parse_offset("invalid")

    def test_is_completed(self):
        self.assertTrue(is_completed(True))
        self.assertTrue(is_completed(1))
        self.assertTrue(is_completed("true"))
        self.assertTrue(is_completed("True"))
        self.assertTrue(is_completed("completed"))
        self.assertTrue(is_completed("done"))
        self.assertTrue(is_completed("1"))

        self.assertFalse(is_completed(False))
        self.assertFalse(is_completed(0))
        self.assertFalse(is_completed("false"))
        self.assertFalse(is_completed("pending"))
        self.assertFalse(is_completed(None))

    def test_load_and_deduplicate(self):
        data1 = [
            {"id": "t1", "description": "Review PR 100", "completed": False},
            {"id": "t2", "description": "Write documentation", "completed": False},
        ]
        data2 = [
            {"id": "t2", "description": "Write documentation", "completed": True},
            {"id": "t3", "description": "Deploy to staging", "completed": False},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "f1.json"
            p2 = Path(tmpdir) / "f2.json"
            p1.write_text(json.dumps(data1), encoding="utf-8")
            p2.write_text(json.dumps(data2), encoding="utf-8")

            res = load([str(p1), str(p2)])
            self.assertEqual(len(res), 3)
            self.assertIn("t1", res)
            self.assertIn("t2", res)
            self.assertIn("t3", res)
            # t2 updated to completed
            self.assertTrue(res["t2"]["completed"])

    def test_load_stdin(self):
        data = [{"id": "t_pipe", "description": "Task via stdin", "completed": False}]
        with patch("sys.stdin", io.StringIO(json.dumps(data))):
            res = load(["-"])
            self.assertEqual(len(res), 1)
            self.assertEqual(res["t_pipe"]["description"], "Task via stdin")

    def test_load_invalid_formats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                load([str(Path(tmpdir) / "missing.json")])

            p_bad = Path(tmpdir) / "bad.json"
            p_bad.write_text("{corrupt", encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(p_bad)])

            p_noid = Path(tmpdir) / "no_id.json"
            p_noid.write_text('[{"description": "No ID task"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(p_noid)])

            p_nondict = Path(tmpdir) / "non_dict.json"
            p_nondict.write_text('["string item"]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(p_nondict)])

    def test_generate_digest_metrics_and_tables(self):
        fixed_now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        sample_tasks = {
            "t1": {
                "id": "t1",
                "description": "Prepare release notes",
                "completed": True,
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-21T10:00:00Z",
            },
            "t2": {
                "id": "t2",
                "description": "Fix bug in parser",
                "completed": False,
                "created_at": "2026-09-21T14:00:00Z",
                "due_at": "2026-09-23T10:00:00Z",  # Overdue relative to 2026-09-24
            },
            "t3": {
                "id": "t3",
                "description": "Schedule design sync",
                "completed": False,
                "created_at": "2026-09-22T09:00:00Z",
                "due_at": "2026-09-28T10:00:00Z",  # Future due date
            },
            "t4": {
                "id": "t4",
                "description": "Refactor database migrations",
                "completed": True,
                "created_at": "2026-09-22T15:00:00Z",
            },
        }

        fixed_now = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
        output = generate_digest(sample_tasks, title="Sprint Task Velocity Digest", now=fixed_now)

        self.assertIn("# Sprint Task Velocity Digest", output)
        self.assertIn("**Total Tasks**: 4", output)
        self.assertIn("**Completed**: 2", output)
        self.assertIn("**Pending**: 2", output)
        self.assertIn("**Completion Rate**: 50.0%", output)

        # Overdue check
        self.assertIn("Overdue Tasks Attention Required", output)
        self.assertIn("OVERDUE: 2026-09-23", output)
        self.assertIn("Fix bug in parser", output)

        # Timeline table
        self.assertIn("## Daily Task Timeline", output)
        self.assertIn("| 2026-09-22 | 2 |", output)
        self.assertIn("| 2026-09-21 | 1 |", output)
        self.assertIn("| 2026-09-20 | 1 |", output)

        # Pending queue
        self.assertIn("## Pending Action Queue", output)
        self.assertIn("Schedule design sync", output)

        # Completed highlights
        self.assertIn("## Recently Completed Highlights", output)
        self.assertIn("Prepare release notes", output)
        self.assertIn("Refactor database migrations", output)

    def test_date_filtering(self):
        sample = {
            "old": {"id": "old", "description": "Old task", "created_at": "2026-08-10T10:00:00Z"},
            "mid": {"id": "mid", "description": "September task", "created_at": "2026-09-15T10:00:00Z"},
            "fut": {"id": "fut", "description": "October task", "created_at": "2026-10-05T10:00:00Z"},
        }
        since_dt = datetime(2026, 9, 1, tzinfo=timezone.utc)
        until_dt = datetime(2026, 9, 30, tzinfo=timezone.utc)

        output = generate_digest(sample, since=since_dt, until=until_dt)
        self.assertIn("**Total Tasks**: 1", output)
        self.assertIn("September task", output)
        self.assertNotIn("Old task", output)
        self.assertNotIn("October task", output)

    def test_empty_tasks(self):
        output = generate_digest({})
        self.assertIn("**Total Tasks**: 0", output)
        self.assertIn("_No action items found matching the specified criteria._", output)

    def test_convert_file_overwrite_protection(self):
        sample = [{"id": "t1", "description": "Test task", "completed": False}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            dst = Path(tmpdir) / "digest.md"
            src.write_text(json.dumps(sample), encoding="utf-8")
            dst.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                convert([str(src)], str(dst), force=False)

            convert([str(src)], str(dst), force=True)
            self.assertIn("Test task", dst.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
