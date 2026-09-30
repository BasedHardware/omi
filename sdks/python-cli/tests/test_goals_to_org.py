"""Hermetic unit tests for the Omi goals -> Org-mode exporter (Issue #19993).

Covers progress cookies, 20-cell ASCII progress bars, TODO/DONE states,
property drawers, heading escaping, grouping modes, type/status filtering,
envelope unwrapping, BOM tolerance, stdin support, collision resolution,
and overwrite protection.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path

script_path = Path(__file__).resolve().parent / "goals_to_org.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_org.py"

spec = importlib.util.spec_from_file_location("goals_to_org", script_path)
g2org = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2org)

JST = timezone(timedelta(hours=9))
ZWSP = "\u200b"


class TestGoalsToOrg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._counter = 0

    def tearDown(self):
        self._tmp.cleanup()

    def export_single(self, goals, **kwargs):
        self._counter += 1
        source = self.tmp / f"goals_{self._counter}.json"
        source.write_text(json.dumps(goals, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / f"out_{self._counter}.org"
        counts = g2org.convert(source, destination=destination, zone=kwargs.get("zone", JST), **kwargs)
        return counts, destination.read_text(encoding="utf-8")

    def test_01_boolean_goal_done_when_completed(self):
        goal = {
            "id": "g-bool-1",
            "title": "Pass driver license test",
            "goal_type": "boolean",
            "current_value": 1.0,
            "target_value": 1.0,
            "is_active": True,
        }
        counts, org = self.export_single([goal])
        self.assertEqual(counts, (1, 1))
        self.assertIn("* DONE Pass driver license test [100%] [1/1]", org)
        self.assertIn("Progress: [====================] 100%", org)

    def test_02_boolean_goal_todo_when_incomplete(self):
        goal = {
            "id": "g-bool-2",
            "title": "Buy concert tickets",
            "goal_type": "boolean",
            "current_value": 0.0,
            "target_value": 1.0,
            "is_active": True,
        }
        counts, org = self.export_single([goal])
        self.assertEqual(counts, (1, 0))
        self.assertIn("* TODO Buy concert tickets [0%] [0/1]", org)
        self.assertIn("Progress: [--------------------] 0%", org)

    def test_03_numeric_progress_cookie_and_bar(self):
        goal = {
            "id": "g-num-1",
            "title": "Read 10 books",
            "goal_type": "numeric",
            "current_value": 5,
            "target_value": 10,
            "min_value": 0,
            "max_value": 10,
            "unit": "books",
            "is_active": True,
        }
        counts, org = self.export_single([goal])
        self.assertEqual(counts, (1, 0))
        self.assertIn("* TODO Read 10 books [50%] [5/10]", org)
        self.assertIn("Progress: [==========----------] 50%", org)
        self.assertIn("Unit: books", org)

    def test_04_scale_progress_cookie_and_bar(self):
        goal = {
            "id": "g-scale-1",
            "title": "Meditation mindfulness level",
            "goal_type": "scale",
            "current_value": 7.5,
            "target_value": 10,
            "min_value": 0,
            "max_value": 10,
            "is_active": True,
        }
        counts, org = self.export_single([goal])
        self.assertEqual(counts, (1, 0))
        self.assertIn("* TODO Meditation mindfulness level [75%] [7.5/10]", org)
        self.assertIn("Progress: [===============-----] 75%", org)

    def test_05_done_when_metric_reaches_target(self):
        goal = {
            "id": "g-num-done",
            "title": "Run 50km",
            "goal_type": "numeric",
            "current_value": 50,
            "target_value": 50,
            "is_active": True,
            "updated_at": "2026-09-30T10:00:00Z",
        }
        counts, org = self.export_single([goal])
        self.assertEqual(counts, (1, 1))
        self.assertIn("* DONE Run 50km [100%] [50/50]", org)
        self.assertIn("CLOSED: [2026-09-30 Wed 19:00]", org)

    def test_06_done_when_inactive(self):
        goal = {
            "id": "g-inactive",
            "title": "Learn Latin",
            "goal_type": "numeric",
            "current_value": 2,
            "target_value": 10,
            "is_active": False,
        }
        counts, org = self.export_single([goal])
        self.assertEqual(counts, (1, 1))
        self.assertIn("* DONE Learn Latin [20%] [2/10]", org)
        self.assertIn(":IS_ACTIVE: False", org)

    def test_07_property_drawer_keys(self):
        goal = {
            "id": "omi_goal_123",
            "title": "Save money",
            "goal_type": "numeric",
            "current_value": 2500,
            "target_value": 5000,
            "min_value": 0,
            "max_value": 5000,
            "unit": "USD",
            "is_active": True,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-06-01T12:00:00Z",
        }
        _, org = self.export_single([goal])
        self.assertIn(":OMI_ID: omi_goal_123", org)
        self.assertIn(":GOAL_TYPE: numeric", org)
        self.assertIn(":CURRENT_VALUE: 2500", org)
        self.assertIn(":TARGET_VALUE: 5000", org)
        self.assertIn(":MIN_VALUE: 0", org)
        self.assertIn(":MAX_VALUE: 5000", org)
        self.assertIn(":UNIT: USD", org)
        self.assertIn(":IS_ACTIVE: True", org)
        self.assertIn(":CREATED: [2026-01-01 Thu 09:00]", org)
        self.assertIn(":UPDATED: [2026-06-01 Mon 21:00]", org)

    def test_08_heading_escapes_org_syntax(self):
        self.assertEqual(g2org.heading_text("[#A] Important goal :tag:"), ZWSP + "[#A] Important goal :tag:" + ZWSP)
        self.assertEqual(g2org.heading_text("Target <2026-10-01 Thu>"), "Target <" + ZWSP + "2026-10-01 Thu>")
        self.assertEqual(g2org.heading_text(""), "(no title)")
        self.assertEqual(g2org.heading_text(None), "(no title)")

    def test_09_group_by_status(self):
        goals = [
            {"id": "1", "title": "Goal Open", "current_value": 0, "target_value": 10, "is_active": True},
            {"id": "2", "title": "Goal Closed", "current_value": 10, "target_value": 10, "is_active": True},
        ]
        _, org = self.export_single(goals, group_by="status")
        self.assertIn("* Active Goals [1]", org)
        self.assertIn("** TODO Goal Open", org)
        self.assertIn("* Completed / Inactive Goals [1]", org)
        self.assertIn("** DONE Goal Closed", org)

    def test_10_group_by_type(self):
        goals = [
            {"id": "1", "title": "Numeric G", "goal_type": "numeric", "current_value": 1, "target_value": 10},
            {"id": "2", "title": "Boolean G", "goal_type": "boolean", "current_value": 0, "target_value": 1},
        ]
        _, org = self.export_single(goals, group_by="type")
        self.assertIn("* Boolean Goals [1]", org)
        self.assertIn("** TODO Boolean G", org)
        self.assertIn("* Numeric Goals [1]", org)
        self.assertIn("** TODO Numeric G", org)

    def test_11_group_by_none(self):
        goals = [
            {"id": "1", "title": "G1", "current_value": 1, "target_value": 2},
            {"id": "2", "title": "G2", "current_value": 2, "target_value": 2},
        ]
        _, org = self.export_single(goals, group_by="none")
        self.assertIn("* TODO G1", org)
        self.assertIn("* DONE G2", org)
        self.assertNotIn("** TODO", org)

    def test_12_active_only_filter(self):
        goals = [
            {"id": "1", "title": "Active One", "is_active": True},
            {"id": "2", "title": "Archived One", "is_active": False},
        ]
        counts, org = self.export_single(goals, active_only=True)
        self.assertEqual(counts, (1, 0))
        self.assertIn("Active One", org)
        self.assertNotIn("Archived One", org)

    def test_13_goal_type_filter(self):
        goals = [
            {"id": "1", "title": "Scale G", "goal_type": "scale"},
            {"id": "2", "title": "Numeric G", "goal_type": "numeric"},
            {"id": "3", "title": "Boolean G", "goal_type": "boolean"},
        ]
        counts, org = self.export_single(goals, goal_types=["scale", "boolean"])
        self.assertEqual(counts, (2, 0))
        self.assertIn("Scale G", org)
        self.assertIn("Boolean G", org)
        self.assertNotIn("Numeric G", org)

    def test_14_envelope_unwrapping(self):
        for key in ("goals", "items", "data"):
            wrapped = {key: [{"id": f"g-{key}", "title": f"Title {key}"}]}
            counts, org = self.export_single(wrapped)
            self.assertEqual(counts, (1, 0))
            self.assertIn(f"Title {key}", org)

    def test_15_bare_list_and_single_object(self):
        single = {"id": "single-g", "title": "Single Goal Item"}
        counts, org = self.export_single(single)
        self.assertEqual(counts, (1, 0))
        self.assertIn("Single Goal Item", org)

    def test_16_utf8_bom_tolerance(self):
        raw = '\ufeff[{"id": "bom-1", "title": "BOM Goal"}]'
        src = self.tmp / "bom.json"
        src.write_bytes(raw.encode("utf-8"))
        dst = self.tmp / "bom.org"
        counts = g2org.convert(src, dst, JST)
        self.assertEqual(counts, (1, 0))
        self.assertIn("BOM Goal", dst.read_text(encoding="utf-8"))

    def test_17_stdin_pipe_support(self):
        payload = json.dumps([{"id": "stdin-1", "title": "Piped Goal"}])
        old_stdin = sys.stdin
        sys.stdin = io.StringIO(payload)
        try:
            # We mock sys.stdin.buffer.read
            old_buffer = sys.stdin.buffer if hasattr(sys.stdin, "buffer") else None

            class MockBuffer:
                def read(self):
                    return payload.encode("utf-8")

            sys.stdin.buffer = MockBuffer()
            dst = self.tmp / "piped.org"
            counts = g2org.convert("-", dst, JST)
            self.assertEqual(counts, (1, 0))
            self.assertIn("Piped Goal", dst.read_text(encoding="utf-8"))
        finally:
            sys.stdin = old_stdin

    def test_18_output_dir_mode_with_collision_resolution(self):
        goals = [
            {"id": "1", "title": "Exercise Daily", "current_value": 1, "target_value": 1},
            {"id": "2", "title": "Exercise Daily", "current_value": 0, "target_value": 1},
            {"id": "3", "title": "Exercise Daily", "current_value": 0, "target_value": 1},
        ]
        src = self.tmp / "collision.json"
        src.write_text(json.dumps(goals), encoding="utf-8")
        out_dir = self.tmp / "individual_goals"
        written, completed = g2org.convert(src, zone=JST, output_dir=out_dir)
        self.assertEqual(written, 3)
        self.assertEqual(completed, 1)

        f1 = out_dir / "Exercise_Daily.org"
        f2 = out_dir / "Exercise_Daily-2.org"
        f3 = out_dir / "Exercise_Daily-3.org"
        self.assertTrue(f1.exists())
        self.assertTrue(f2.exists())
        self.assertTrue(f3.exists())
        self.assertIn("DONE Exercise Daily", f1.read_text(encoding="utf-8"))
        self.assertIn("TODO Exercise Daily", f2.read_text(encoding="utf-8"))

    def test_19_refusal_to_overwrite_without_force(self):
        src = self.tmp / "in.json"
        src.write_text(json.dumps([{"id": "1", "title": "T1"}]), encoding="utf-8")
        dst = self.tmp / "dest.org"
        dst.write_text("existing content", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            g2org.convert(src, destination=dst, zone=JST, force=False)

        # Overwrite works when force=True
        g2org.convert(src, destination=dst, zone=JST, force=True)
        self.assertIn("T1", dst.read_text(encoding="utf-8"))

    def test_20_utc_offset_parsing_and_conversion(self):
        tz = g2org.parse_offset("+05:30")
        self.assertEqual(tz.utcoffset(None), timedelta(hours=5, minutes=30))
        tz_neg = g2org.parse_offset("-08:00")
        self.assertEqual(tz_neg.utcoffset(None), timedelta(hours=-8))

        with self.assertRaises(argparse.ArgumentTypeError):
            g2org.parse_offset("+15:00")
        with self.assertRaises(argparse.ArgumentTypeError):
            g2org.parse_offset("invalid")


if __name__ == "__main__":
    unittest.main()
