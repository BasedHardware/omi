"""Tests for the action items -> Org-mode exporter (#17539).

Pins TODO/DONE mapping, DEADLINE/CLOSED timestamps with time zone rollover,
Org syntax escaping in headings, ordering, loose field coercion, and the
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

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_org.py"
spec = importlib.util.spec_from_file_location("action_items_to_org", script_path)
ai2org = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2org)

ZWSP = "​"
JST = timezone(timedelta(hours=9))


class TestActionItemsToOrg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, items, zone=JST):
        source = self.tmp / "action_items.json"
        source.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "out.org"
        counts = ai2org.convert(source, destination, zone)
        return counts, destination.read_text(encoding="utf-8")

    def test_deadline_rolls_over_to_next_local_day(self):
        _, org = self.export([{"id": "a1", "description": "Pay rent", "completed": False,
                               "due_at": "2026-09-30T23:30:00Z"}])
        self.assertIn("* TODO Pay rent\nDEADLINE: <2026-10-01 Thu 08:30>", org)

    def test_offset_and_naive_timestamps(self):
        _, org = self.export([
            {"id": "a1", "description": "offset", "due_at": "2026-09-20T09:00:00+02:00"},
            {"id": "a2", "description": "naive", "due_at": "2026-09-21T10:00:00"},
        ])
        self.assertIn("DEADLINE: <2026-09-20 Sun 16:00>", org)
        self.assertIn("DEADLINE: <2026-09-21 Mon 19:00>", org)

    def test_done_item_gets_closed_and_deadline_on_one_line(self):
        _, org = self.export([{"id": "a1", "description": "Ship", "completed": True,
                               "completed_at": "2026-09-19T15:00:00Z",
                               "due_at": "2026-09-19T00:00:00Z"}])
        self.assertIn("* DONE Ship\nCLOSED: [2026-09-20 Sun 00:00] DEADLINE: <2026-09-19 Sat 09:00>", org)

    def test_completed_is_coerced_loosely(self):
        self.assertTrue(ai2org.is_done("yes"))
        self.assertTrue(ai2org.is_done(1))
        self.assertFalse(ai2org.is_done(0))
        self.assertFalse(ai2org.is_done("no"))
        self.assertFalse(ai2org.is_done(None))

    def test_heading_escapes_org_syntax(self):
        self.assertEqual(ai2org.heading_text("[#A] call Bob :urgent:"),
                         ZWSP + "[#A] call Bob :urgent:" + ZWSP)
        self.assertEqual(ai2org.heading_text("see <2026-10-01 Thu>"), "see <" + ZWSP + "2026-10-01 Thu>")
        self.assertEqual(ai2org.heading_text(None), "(no description)")
        self.assertEqual(ai2org.heading_text("会議の\n準備"), "会議の 準備")
        self.assertEqual(ai2org.heading_text({"k": "値"}), '{"k": "値"}')

    def test_order_open_by_deadline_then_undated_then_done(self):
        (written, undated), org = self.export([
            {"id": "d", "description": "done", "completed": True},
            {"id": "u", "description": "undated"},
            {"id": "late", "description": "late", "due_at": "2026-10-05T00:00:00Z"},
            {"id": "soon", "description": "soon", "due_at": "2026-10-01T00:00:00Z"},
        ])
        headings = [line for line in org.splitlines() if line.startswith("* ")]
        self.assertEqual(headings, ["* TODO soon", "* TODO late", "* TODO undated", "* DONE done"])
        self.assertEqual((written, undated), (4, 2))

    def test_property_drawer(self):
        _, org = self.export([{"id": "a1", "description": "x", "conversation_id": "c9",
                               "created_at": "2026-09-01T00:00:00Z"}])
        self.assertIn(":PROPERTIES:\n:OMI_ID: a1\n:CONVERSATION: c9\n:CREATED: [2026-09-01 Tue 09:00]\n:END:", org)

    def test_empty_array_writes_header_only(self):
        (written, undated), org = self.export([])
        self.assertEqual((written, undated), (0, 0))
        self.assertTrue(org.startswith("# -*- mode: org; coding: utf-8 -*-\n#+TITLE: Omi action items\n"))

    def test_bad_input_leaves_no_file(self):
        destination = self.tmp / "out.org"
        for payload in ('{"id": "a1"}', "[1, 2]", "[{broken"):
            source = self.tmp / "bad.json"
            source.write_text(payload, encoding="utf-8")
            with self.assertRaises(ValueError):
                ai2org.convert(source, destination, JST)
            self.assertFalse(destination.exists())

    def test_refuses_to_overwrite(self):
        source = self.tmp / "items.json"
        source.write_text("[]", encoding="utf-8")
        destination = self.tmp / "out.org"
        destination.write_text("keep me", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            ai2org.convert(source, destination, JST)
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep me")

    def test_parse_offset_bounds(self):
        self.assertEqual(ai2org.parse_offset("+09:00"), JST)
        self.assertEqual(ai2org.parse_offset("-14:00"), timezone(-timedelta(hours=14)))
        for bad in ("+14:30", "+99:99", "9", ""):
            with self.assertRaises(argparse.ArgumentTypeError):
                ai2org.parse_offset(bad)

    def test_cli_missing_input_exits_1_without_output(self):
        destination = self.tmp / "out.org"
        result = subprocess.run(
            [sys.executable, str(script_path), str(self.tmp / "missing.json"), str(destination)],
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertFalse(destination.exists())


if __name__ == "__main__":
    unittest.main()
