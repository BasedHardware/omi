"""Tests for the action items -> Taskwarrior import exporter.

Pins the Taskwarrior import shape (status, UTC dates, +omi tag, omiid
attribute), stable UUIDs derived from the Omi id, loose field coercion, and
the no-overwrite / no-partial-file guarantees.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_taskwarrior.py"
spec = importlib.util.spec_from_file_location("action_items_to_taskwarrior", script_path)
ai2tw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2tw)


class TestActionItemsToTaskwarrior(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, items, name="omi_tasks.json"):
        source = self.tmp / "action_items.json"
        source.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / name
        counts = ai2tw.convert(source, destination)
        return counts, json.loads(destination.read_text(encoding="utf-8"))

    def test_open_item(self):
        _, tasks = self.export([{"id": "a1", "description": "Pay rent", "completed": False,
                                 "created_at": "2026-09-01T09:00:00+09:00",
                                 "updated_at": "2026-09-02T00:00:00Z",
                                 "due_at": "2026-09-30T23:30:00Z"}])
        self.assertEqual(tasks, [{
            "description": "Pay rent",
            "uuid": str(uuid.uuid5(ai2tw.OMI_NAMESPACE, "a1")),
            "status": "pending",
            "entry": "20260901T000000Z",
            "modified": "20260902T000000Z",
            "due": "20260930T233000Z",
            "tags": ["omi"],
            "omiid": "a1",
        }])

    def test_completed_item_with_and_without_completion_date(self):
        _, tasks = self.export([
            {"id": "d1", "description": "Ship", "completed": True, "completed_at": "2026-09-19T15:00:00Z"},
            {"id": "d2", "description": "Old", "completed": "yes"},
        ])
        self.assertEqual([t["status"] for t in tasks], ["completed", "completed"])
        self.assertEqual(tasks[0]["end"], "20260919T150000Z")
        self.assertNotIn("end", tasks[1])

    def test_completed_at_is_ignored_for_open_items(self):
        _, tasks = self.export([{"id": "a1", "description": "x", "completed": False,
                                 "completed_at": "2026-09-19T15:00:00Z"}])
        self.assertEqual(tasks[0]["status"], "pending")
        self.assertNotIn("end", tasks[0])

    def test_dates_are_converted_to_utc(self):
        self.assertEqual(ai2tw.tw_date("2026-09-20T23:00:00-02:00"), "20260921T010000Z")
        self.assertEqual(ai2tw.tw_date("2026-09-21T08:30:00+09:00"), "20260920T233000Z")
        self.assertEqual(ai2tw.tw_date("2026-09-21T20:00:00"), "20260921T200000Z")
        for bad in ("", "tomorrow", None, 1758000000, {"at": "x"}):
            self.assertIsNone(ai2tw.tw_date(bad))

    def test_uuid_is_stable_across_exports(self):
        _, first = self.export([{"id": "a1", "description": "one"}], "first.json")
        _, second = self.export([{"id": "a1", "description": "one, edited", "completed": True}], "second.json")
        self.assertEqual(first[0]["uuid"], second[0]["uuid"])
        self.assertNotEqual(first[0]["uuid"], str(uuid.uuid5(ai2tw.OMI_NAMESPACE, "a2")))

    def test_missing_id_gets_no_uuid_and_is_counted(self):
        (pending, completed, without_id), tasks = self.export([{"description": "no id"}, {"id": "  ", "description": "blank"}])
        self.assertEqual((pending, completed, without_id), (2, 0, 2))
        for task in tasks:
            self.assertNotIn("uuid", task)
            self.assertNotIn("omiid", task)

    def test_description_is_one_line_and_never_empty(self):
        _, tasks = self.export([
            {"id": "a", "description": "会議の\n準備\t🎧"},
            {"id": "b", "description": None},
            {"id": "c", "description": "   "},
            {"id": "d", "description": {"k": "値"}},
            {"id": 42, "description": 7},
        ])
        self.assertEqual([t["description"] for t in tasks],
                         ["会議の 準備 🎧", "(no description)", "(no description)", '{"k": "値"}', "7"])
        self.assertEqual(tasks[4]["omiid"], "42")

    def test_completed_is_coerced_loosely(self):
        self.assertTrue(ai2tw.is_done("yes"))
        self.assertTrue(ai2tw.is_done(1))
        self.assertFalse(ai2tw.is_done(0))
        self.assertFalse(ai2tw.is_done("no"))
        self.assertFalse(ai2tw.is_done(None))

    def test_empty_array_writes_empty_list(self):
        counts, tasks = self.export([])
        self.assertEqual((counts, tasks), ((0, 0, 0), []))

    def test_bad_input_leaves_no_file(self):
        destination = self.tmp / "omi_tasks.json"
        for payload in ('{"id": "a1"}', "[1, 2]", "[{broken"):
            source = self.tmp / "bad.json"
            source.write_text(payload, encoding="utf-8")
            with self.assertRaises(ValueError):
                ai2tw.convert(source, destination)
            self.assertFalse(destination.exists())

    def test_refuses_to_overwrite(self):
        source = self.tmp / "items.json"
        source.write_text("[]", encoding="utf-8")
        destination = self.tmp / "omi_tasks.json"
        destination.write_text("keep me\n", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            ai2tw.convert(source, destination)
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep me\n")

    def test_cli_missing_input_exits_1_without_output(self):
        destination = self.tmp / "omi_tasks.json"
        result = subprocess.run(
            [sys.executable, str(script_path), str(self.tmp / "missing.json"), str(destination)],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
