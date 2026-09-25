"""Tests for the action items -> todo.txt exporter.

Pins the todo.txt line layout (completion mark, dates, due:/omi: tags), local
calendar dates with time zone rollover, escaping of todo.txt syntax inside
descriptions, ordering, loose field coercion, and the no-overwrite /
no-partial-file guarantees.
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

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_todotxt.py"
spec = importlib.util.spec_from_file_location("action_items_to_todotxt", script_path)
ai2todo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2todo)

ZWSP = "​"
JST = timezone(timedelta(hours=9))


class TestActionItemsToTodoTxt(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, items, zone=JST):
        source = self.tmp / "action_items.json"
        source.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "todo.txt"
        counts = ai2todo.convert(source, destination, zone)
        return counts, destination.read_text(encoding="utf-8").splitlines()

    def test_open_item_line(self):
        _, lines = self.export([{"id": "a1", "description": "Pay rent", "completed": False,
                                 "created_at": "2026-09-01T00:00:00Z", "due_at": "2026-09-30T23:30:00Z"}])
        self.assertEqual(lines, ["2026-09-01 Pay rent due:2026-10-01 omi:a1"])

    def test_done_item_with_and_without_completion_date(self):
        _, lines = self.export([
            {"id": "d1", "description": "Ship", "completed": True,
             "completed_at": "2026-09-19T15:00:00Z", "created_at": "2026-09-10T00:00:00Z"},
            {"id": "d2", "description": "Old", "completed": "yes", "created_at": "2026-09-10T00:00:00Z"},
        ])
        self.assertIn("x 2026-09-20 2026-09-10 Ship omi:d1", lines)
        self.assertIn("x Old omi:d2", lines)

    def test_offset_and_naive_timestamps(self):
        _, lines = self.export([
            {"id": "a1", "description": "offset", "due_at": "2026-09-20T23:00:00-02:00"},
            {"id": "a2", "description": "naive", "due_at": "2026-09-21T20:00:00"},
        ])
        self.assertIn("offset due:2026-09-21 omi:a1", lines)
        self.assertIn("naive due:2026-09-22 omi:a2", lines)

    def test_completed_is_coerced_loosely(self):
        self.assertTrue(ai2todo.is_done("yes"))
        self.assertTrue(ai2todo.is_done(1))
        self.assertFalse(ai2todo.is_done(0))
        self.assertFalse(ai2todo.is_done("no"))
        self.assertFalse(ai2todo.is_done(None))

    def test_task_text_escapes_todotxt_syntax(self):
        self.assertEqual(ai2todo.task_text("ask +team @office"), f"ask {ZWSP}+team {ZWSP}@office")
        self.assertEqual(ai2todo.task_text("move due:2026-01-01"), f"move due{ZWSP}:2026-01-01")
        self.assertEqual(ai2todo.task_text("see https://example.com"), "see https://example.com")
        self.assertEqual(ai2todo.task_text("x marks the spot"), ZWSP + "x marks the spot")
        self.assertEqual(ai2todo.task_text("(A) urgent"), ZWSP + "(A) urgent")
        self.assertEqual(ai2todo.task_text("2026-10-01 launch"), ZWSP + "2026-10-01 launch")
        self.assertEqual(ai2todo.task_text("a + b"), "a + b")
        self.assertEqual(ai2todo.task_text(None), "(no description)")
        self.assertEqual(ai2todo.task_text("会議の\n準備"), "会議の 準備")
        self.assertEqual(ai2todo.task_text({"k": "値"}), '{"k": "値"}')

    def test_order_open_by_due_then_undated_then_done(self):
        (written, undated), lines = self.export([
            {"id": "d", "description": "done", "completed": True},
            {"id": "u", "description": "undated"},
            {"id": "late", "description": "late", "due_at": "2026-10-05T00:00:00Z"},
            {"id": "soon", "description": "soon", "due_at": "2026-10-01T00:00:00Z"},
        ])
        self.assertEqual([line.split(" omi:")[1] for line in lines], ["soon", "late", "u", "d"])
        self.assertEqual((written, undated), (4, 2))

    def test_id_with_whitespace_or_missing_is_left_out(self):
        _, lines = self.export([{"id": "a b", "description": "spaced"}, {"description": "no id"}])
        self.assertEqual(lines, ["spaced", "no id"])

    def test_empty_array_writes_empty_file(self):
        (written, undated), lines = self.export([])
        self.assertEqual((written, undated, lines), (0, 0, []))

    def test_bad_input_leaves_no_file(self):
        destination = self.tmp / "todo.txt"
        for payload in ('{"id": "a1"}', "[1, 2]", "[{broken"):
            source = self.tmp / "bad.json"
            source.write_text(payload, encoding="utf-8")
            with self.assertRaises(ValueError):
                ai2todo.convert(source, destination, JST)
            self.assertFalse(destination.exists())

    def test_refuses_to_overwrite(self):
        source = self.tmp / "items.json"
        source.write_text("[]", encoding="utf-8")
        destination = self.tmp / "todo.txt"
        destination.write_text("keep me\n", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            ai2todo.convert(source, destination, JST)
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep me\n")

    def test_parse_offset_bounds(self):
        self.assertEqual(ai2todo.parse_offset("+09:00"), JST)
        self.assertEqual(ai2todo.parse_offset("-14:00"), timezone(-timedelta(hours=14)))
        for bad in ("+14:30", "+99:99", "9", ""):
            with self.assertRaises(argparse.ArgumentTypeError):
                ai2todo.parse_offset(bad)

    def test_cli_missing_input_exits_1_without_output(self):
        destination = self.tmp / "todo.txt"
        result = subprocess.run(
            [sys.executable, str(script_path), str(self.tmp / "missing.json"), str(destination)],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
