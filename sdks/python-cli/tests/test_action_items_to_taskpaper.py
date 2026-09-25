"""Tests for the action items -> TaskPaper exporter.

Pins the TaskPaper layout (Open:/Done: projects, tab-indented "- " tasks,
@due/@done/@created/@omi tags), local times with time zone rollover, escaping
of @tags inside descriptions, ordering, loose field coercion, and the
no-overwrite / no-partial-file guarantees.
"""

from __future__ import annotations

import argparse
from datetime import timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_taskpaper.py"
spec = importlib.util.spec_from_file_location("action_items_to_taskpaper", script_path)
ai2tp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2tp)

ZWSP = "​"
JST = timezone(timedelta(hours=9))


class TestActionItemsToTaskPaper(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, items, zone=JST):
        source = self.tmp / "action_items.json"
        source.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "omi.taskpaper"
        counts = ai2tp.convert(source, destination, zone)
        return counts, destination.read_text(encoding="utf-8").splitlines()

    def test_open_item_line(self):
        _, lines = self.export([{"id": "a1", "description": "Pay rent", "completed": False,
                                 "created_at": "2026-09-01T00:00:00Z", "due_at": "2026-09-30T23:30:00Z"}])
        self.assertEqual(lines, ["Open:", "\t- Pay rent @due(2026-10-01 08:30) @created(2026-09-01) @omi(a1)"])

    def test_done_item_with_and_without_completion_date(self):
        _, lines = self.export([
            {"id": "d1", "description": "Ship", "completed": True,
             "completed_at": "2026-09-19T15:00:00Z", "created_at": "2026-09-10T00:00:00Z"},
            {"id": "d2", "description": "Old", "completed": "yes", "created_at": "2026-09-10T00:00:00Z"},
        ])
        self.assertEqual(lines[0], "Done:")
        self.assertIn("\t- Ship @done(2026-09-20) @created(2026-09-10) @omi(d1)", lines)
        self.assertIn("\t- Old @done @created(2026-09-10) @omi(d2)", lines)

    def test_offset_and_naive_timestamps(self):
        _, lines = self.export([
            {"id": "a1", "description": "offset", "due_at": "2026-09-20T23:00:00-02:00"},
            {"id": "a2", "description": "naive", "due_at": "2026-09-21T20:00:00"},
        ])
        self.assertIn("\t- offset @due(2026-09-21 10:00) @omi(a1)", lines)
        self.assertIn("\t- naive @due(2026-09-22 05:00) @omi(a2)", lines)

    def test_completed_is_coerced_loosely(self):
        self.assertTrue(ai2tp.is_done("yes"))
        self.assertTrue(ai2tp.is_done(1))
        self.assertFalse(ai2tp.is_done(0))
        self.assertFalse(ai2tp.is_done("no"))
        self.assertFalse(ai2tp.is_done(None))

    def test_task_text_escapes_taskpaper_tags(self):
        self.assertEqual(ai2tp.task_text("ask @team about @done(x)"), f"ask {ZWSP}@team about {ZWSP}@done(x)")
        self.assertEqual(ai2tp.task_text("mail bob@example.com"), "mail bob@example.com")
        self.assertEqual(ai2tp.task_text("a @ b"), "a @ b")
        self.assertEqual(ai2tp.task_text("Plan:"), "Plan:")
        self.assertEqual(ai2tp.task_text(None), "(no description)")
        self.assertEqual(ai2tp.task_text("会議の\n準備"), "会議の 準備")
        self.assertEqual(ai2tp.task_text({"k": "値"}), '{"k": "値"}')

    def test_order_open_by_due_then_undated_then_done(self):
        (open_count, done_count, undated), lines = self.export([
            {"id": "d", "description": "done", "completed": True},
            {"id": "u", "description": "undated"},
            {"id": "late", "description": "late", "due_at": "2026-10-05T00:00:00Z"},
            {"id": "soon", "description": "soon", "due_at": "2026-10-01T00:00:00Z"},
        ])
        self.assertEqual(lines[0], "Open:")
        self.assertEqual(lines[4], "Done:")
        ids = [line.split("@omi(")[1].rstrip(")") for line in lines if "@omi(" in line]
        self.assertEqual(ids, ["soon", "late", "u", "d"])
        self.assertEqual((open_count, done_count, undated), (3, 1, 2))

    def test_unsafe_or_missing_id_is_left_out(self):
        _, lines = self.export([{"id": "a b", "description": "spaced"}, {"id": "x)y", "description": "paren"},
                                {"description": "no id"}])
        self.assertEqual(lines, ["Open:", "\t- spaced", "\t- paren", "\t- no id"])

    def test_empty_array_writes_empty_file(self):
        counts, lines = self.export([])
        self.assertEqual((counts, lines), ((0, 0, 0), []))

    def test_bad_input_leaves_no_file(self):
        destination = self.tmp / "omi.taskpaper"
        for payload in ('{"id": "a1"}', "[1, 2]", "[{broken"):
            source = self.tmp / "bad.json"
            source.write_text(payload, encoding="utf-8")
            with self.assertRaises(ValueError):
                ai2tp.convert(source, destination, JST)
            self.assertFalse(destination.exists())

    def test_refuses_to_overwrite(self):
        source = self.tmp / "items.json"
        source.write_text("[]", encoding="utf-8")
        destination = self.tmp / "omi.taskpaper"
        destination.write_text("keep me\n", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            ai2tp.convert(source, destination, JST)
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep me\n")

    def test_parse_offset_bounds(self):
        self.assertEqual(ai2tp.parse_offset("+09:00"), JST)
        self.assertEqual(ai2tp.parse_offset("-14:00"), timezone(-timedelta(hours=14)))
        for bad in ("+14:30", "+99:99", "9", ""):
            with self.assertRaises(argparse.ArgumentTypeError):
                ai2tp.parse_offset(bad)

    def test_cli_missing_input_exits_1_without_output(self):
        destination = self.tmp / "omi.taskpaper"
        result = subprocess.run(
            [sys.executable, str(script_path), str(self.tmp / "missing.json"), str(destination)],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
