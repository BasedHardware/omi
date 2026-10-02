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
        self.assertEqual(ai2todo.task_text("x"), ZWSP + "x")
        self.assertEqual(ai2todo.task_text("(A) urgent"), ZWSP + "(A) urgent")
        self.assertEqual(ai2todo.task_text("(A)"), ZWSP + "(A)")
        self.assertEqual(ai2todo.task_text("2026-10-01 launch"), ZWSP + "2026-10-01 launch")
        self.assertEqual(ai2todo.task_text("2026-10-01"), ZWSP + "2026-10-01")
        self.assertEqual(ai2todo.task_text("xylophone"), "xylophone")
        self.assertEqual(ai2todo.task_text("(Action)"), "(Action)")
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

    def test_issue_19382_bare_completion_and_priority_regression(self):
        """Regression test for Issue #19382: bare 'x' or '(A)' descriptions must not become syntax when metadata is appended."""
        items = [
            {"id": "open-x", "description": "x", "completed": False},
            {"id": "open-priority", "description": "(A)", "completed": False},
            {"id": "normal", "description": "buy milk", "completed": False},
            {"id": "real-done", "description": "done task", "completed": True},
        ]
        counts, lines = self.export(items, zone=timezone.utc)
        self.assertEqual(counts, (4, 4))
        # open-x must NOT start with bare "x "
        self.assertIn(f"{ZWSP}x omi:open-x", lines)
        # open-priority must NOT start with bare "(A) "
        self.assertIn(f"{ZWSP}(A) omi:open-priority", lines)
        # normal control item
        self.assertIn("buy milk omi:normal", lines)
        # real-done control item
        self.assertIn("x done task omi:real-done", lines)

    def test_extract_action_items_envelopes(self):
        item1 = {"id": "a1", "description": "Item 1", "completed": False}
        item2 = {"id": "a2", "description": "Item 2", "completed": True}

        # Bare list
        self.assertEqual(ai2todo.extract_action_items([item1, item2]), [item1, item2])
        self.assertEqual(ai2todo.extract_action_items([]), [])

        # Wrapped envelopes
        self.assertEqual(ai2todo.extract_action_items({"action_items": [item1, item2]}), [item1, item2])
        self.assertEqual(ai2todo.extract_action_items({"items": [item1]}), [item1])
        self.assertEqual(ai2todo.extract_action_items({"data": [item2]}), [item2])

        # Precedence: action_items > items > data
        self.assertEqual(
            ai2todo.extract_action_items({"action_items": [item1], "items": [item2]}),
            [item1],
        )

        # Empty envelopes
        self.assertEqual(ai2todo.extract_action_items({"action_items": []}), [])
        self.assertEqual(ai2todo.extract_action_items({"items": []}), [])
        self.assertEqual(ai2todo.extract_action_items({"data": []}), [])

        # Non-envelope dictionary returns None (raises ValueError on convert)
        self.assertIsNone(ai2todo.extract_action_items(item1))
        self.assertIsNone(ai2todo.extract_action_items({"action_items": "not-a-list"}))
        self.assertIsNone(ai2todo.extract_action_items("not-a-dict"))
        self.assertIsNone(ai2todo.extract_action_items(123))
        self.assertIsNone(ai2todo.extract_action_items(None))

    def test_export_wrapped_envelope(self):
        for key in ("action_items", "items", "data"):
            destination = self.tmp / f"todo_{key}.txt"
            source = self.tmp / f"{key}.json"
            source.write_text(
                json.dumps({key: [{"id": f"task_{key}", "description": f"Test {key}", "completed": False}]}),
                encoding="utf-8",
            )
            counts = ai2todo.convert(source, destination, JST)
            lines = destination.read_text(encoding="utf-8").splitlines()
            self.assertEqual(counts, (1, 1))
            self.assertEqual(lines, [f"Test {key} omi:task_{key}"])

    def test_export_empty_envelope_produces_empty_file(self):
        for key in ("action_items", "items", "data"):
            destination = self.tmp / f"todo_empty_{key}.txt"
            source = self.tmp / f"empty_{key}.json"
            source.write_text(json.dumps({key: []}), encoding="utf-8")
            counts = ai2todo.convert(source, destination, JST)
            lines = destination.read_text(encoding="utf-8").splitlines()
            self.assertEqual(counts, (0, 0))
            self.assertEqual(lines, [])
            self.assertTrue(destination.exists())

    def test_utf8_bom_handling(self):
        destination = self.tmp / "todo_bom.txt"
        source = self.tmp / "bom.json"
        payload = json.dumps([{"id": "bom1", "description": "BOM test", "completed": False}]).encode("utf-8-sig")
        source.write_bytes(payload)
        counts = ai2todo.convert(source, destination, JST)
        lines = destination.read_text(encoding="utf-8").splitlines()
        self.assertEqual(counts, (1, 1))
        self.assertEqual(lines, ["BOM test omi:bom1"])


if __name__ == "__main__":
    unittest.main()
