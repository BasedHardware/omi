"""Tests for the goals -> Org-mode exporter (#19532).

Pins TODO/DONE mapping with progress cookies, the ASCII progress bar, property
drawer keys, grouping and filters, Org syntax escaping, loose coercion, and the
no-overwrite / no-partial-file guarantees. All cases are hermetic: JSON fixtures
in, text out; no network, no CLI, no external services.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
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

ZWSP = "\u200b"
JST = timezone(timedelta(hours=9))


def goal(**overrides):
    base = {
        "id": "g1",
        "title": "Read books",
        "goal_type": "numeric",
        "target_value": 10.0,
        "current_value": 5.0,
        "min_value": 0.0,
        "max_value": 10.0,
        "unit": "books",
        "is_active": True,
        "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-09-15T00:00:00Z",
    }
    base.update(overrides)
    return base


class TestGoalsToOrg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, payload, **kwargs):
        self._n = getattr(self, "_n", 0) + 1
        source = self.tmp / "goals.json"
        source.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / f"out-{self._n}.org"
        counts = g2org.convert(source, destination, JST, **kwargs)
        return counts, destination.read_text(encoding="utf-8")

    # --- heading / cookie / bar rendering ---------------------------------

    def test_progress_cookie_and_bar(self):
        _, org = self.export([goal()])
        self.assertIn("* TODO Read books [50%] [5/10] :numeric:", org)
        self.assertIn("- Progress: [=========>          ] 50.0%", org)

    def test_bar_boundaries(self):
        self.assertEqual(g2org.progress_bar(0.0), "[" + ">" + " " * 19 + "] 0.0%")
        self.assertEqual(g2org.progress_bar(1.0), "[" + "=" * 19 + ">] 100.0%")
        self.assertIsNone(g2org.progress_bar(None))

    def test_done_when_target_reached(self):
        _, org = self.export([goal(current_value=10.0)])
        self.assertIn("* DONE Read books [100%] [10/10] :numeric:", org)
        self.assertIn("- Progress: [" + "=" * 19 + ">] 100.0%", org)

    def test_done_when_inactive(self):
        _, org = self.export([goal(is_active=False, current_value=2.0)])
        self.assertTrue(org.startswith("# -*- mode: org; coding: utf-8 -*-"))
        self.assertIn("* DONE Read books [20%] [2/10]", org)

    def test_boolean_goal_fraction(self):
        self.assertEqual(
            g2org.goal_fraction(
                goal(goal_type="boolean", current_value=1.0, target_value=1.0, min_value=0.0, max_value=1.0)
            ),
            1.0,
        )
        self.assertEqual(
            g2org.goal_fraction(
                goal(goal_type="boolean", current_value=0.0, target_value=1.0, min_value=0.0, max_value=1.0)
            ),
            0.0,
        )

    def test_qualitative_goal_has_no_metrics(self):
        _, org = self.export(
            [goal(goal_type="scale", target_value=0.0, current_value=0.0, min_value=0.0, max_value=0.0, unit=None)]
        )
        self.assertIn("- Progress: n/a (no metrics)", org)
        self.assertNotIn("[50%]", org)

    # --- escaping / ordering / drawer --------------------------------------

    def test_heading_escapes_org_syntax(self):
        self.assertEqual(g2org.heading_text("[#A] hit targets :urgent:"), ZWSP + "[#A] hit targets :urgent:" + ZWSP)
        self.assertEqual(g2org.heading_text("see <2026-10-01 Thu>"), "see <" + ZWSP + "2026-10-01 Thu>")
        self.assertEqual(g2org.heading_text(None), "(untitled goal)")
        self.assertEqual(g2org.heading_text("会議の\n準備"), "会議の 準備")
        self.assertEqual(g2org.heading_text({"k": "値"}), '{"k": "値"}')

    def test_property_drawer_keys(self):
        _, org = self.export([goal()])
        self.assertIn(
            ":PROPERTIES:\n:OMI_ID: g1\n:GOAL_TYPE: numeric\n:CURRENT_VALUE: 5\n"
            ":TARGET_VALUE: 10\n:MIN_VALUE: 0\n:MAX_VALUE: 10\n:UNIT: books\n"
            ":IS_ACTIVE: true\n:CREATED: [2026-09-01 Tue 09:00]\n"
            ":UPDATED: [2026-09-15 Tue 09:00]\n:END:",
            org,
        )

    def test_order_active_first_then_type_then_title(self):
        _, org = self.export(
            [
                goal(id="b", title="beta", goal_type="scale", is_active=True),
                goal(id="a", title="alpha", goal_type="scale", is_active=False),
                goal(id="c", title="Charlie", goal_type="numeric", is_active=True),
            ]
        )
        headings = [line for line in org.splitlines() if line.startswith("* ")]
        self.assertEqual(
            [h.split()[1] + " " + h.split()[2] for h in headings],
            ["TODO Charlie", "TODO beta", "DONE alpha"],
        )

    def test_group_by_status_and_type(self):
        _, org = self.export(
            [
                goal(id="a", title="active one", is_active=True),
                goal(id="b", title="inactive one", is_active=False, goal_type="scale"),
            ],
            group_by="status",
        )
        self.assertIn("* Active\n  * TODO active one", org)
        self.assertIn("* Completed & archived\n  * DONE inactive one", org)
        _, org2 = self.export([goal(), goal(id="s", title="s", goal_type="scale")], group_by="type")
        self.assertIn("* numeric\n  * TODO", org2)
        self.assertIn("* scale\n  * TODO", org2)

    def test_filters(self):
        goals = [
            goal(id="n", title="numeric one"),
            goal(id="s", title="scale one", goal_type="scale"),
            goal(id="s2", title="scale done", goal_type="scale", is_active=False),
        ]
        _, org = self.export(goals, active_only=True, goal_types="numeric,scale")
        self.assertIn("numeric one", org)
        self.assertIn("scale one", org)
        self.assertNotIn("scale done", org)
        _, org2 = self.export(goals, goal_types="numeric")
        self.assertIn("numeric one", org2)
        self.assertNotIn("scale one", org2)

    # --- envelopes / robustness -------------------------------------------

    def test_extract_goals_envelopes(self):
        g1, g2 = goal(), goal(id="g2")
        self.assertEqual(g2org.extract_goals([g1, g2]), [g1, g2])
        self.assertEqual(g2org.extract_goals({"goals": [g1, g2]}), [g1, g2])
        self.assertEqual(g2org.extract_goals({"items": [g1]}), [g1])
        self.assertEqual(g2org.extract_goals({"data": [g2]}), [g2])
        self.assertEqual(g2org.extract_goals({"goals": []}), [])
        self.assertEqual(g2org.extract_goals(g1), [g1])  # single goal object
        self.assertIsNone(g2org.extract_goals({"notes": "z", "kind": "goal-ish"}))
        self.assertIsNone(g2org.extract_goals("nope"))

    def test_empty_array_writes_header_only(self):
        (written, done), org = self.export([])
        self.assertEqual((written, done), (0, 0))
        self.assertTrue(org.startswith("# -*- mode: org; coding: utf-8 -*-\n#+TITLE: Omi goals\n"))
        self.assertNotIn("* TODO", org)

    def test_bad_input_leaves_no_file(self):
        destination = self.tmp / "out.org"
        for payload in ('{"id": "g1"}', "[1, 2]", "[{broken"):
            source = self.tmp / "bad.json"
            source.write_text(payload, encoding="utf-8")
            with self.assertRaises(ValueError):
                g2org.convert(source, destination, JST)
            self.assertFalse(destination.exists())

    def test_refuses_to_overwrite(self):
        source = self.tmp / "goals.json"
        source.write_text("[]", encoding="utf-8")
        destination = self.tmp / "out.org"
        destination.write_text("keep me", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            g2org.convert(source, destination, JST)
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep me")

    def test_bom_is_tolerated(self):
        source = self.tmp / "goals.json"
        source.write_bytes(
            (
                "[{\"id\": \"b1\", \"title\": \"bom\", \"goal_type\": \"scale\", "
                "\"current_value\": 1, \"target_value\": 2}]"
            ).encode("utf-8-sig")
        )
        destination = self.tmp / "out.org"
        g2org.convert(source, destination, JST)
        self.assertIn("* TODO bom", destination.read_text(encoding="utf-8"))

    def test_loose_coercion_of_metrics(self):
        self.assertEqual(g2org._as_float("3"), 3.0)
        self.assertEqual(g2org._as_float(" 4.5 "), 4.5)
        self.assertIsNone(g2org._as_float("high"))
        self.assertIsNone(g2org._as_float(None))
        self.assertEqual(g2org._as_float(True), 1.0)
        self.assertEqual(g2org._fmt_num(5.0), "5")
        self.assertEqual(g2org._fmt_num(2.5), "2.5")
        self.assertIsNone(g2org._fmt_num(None))

    def test_parse_offset_bounds(self):
        self.assertEqual(g2org.parse_offset("+09:00"), JST)
        self.assertEqual(g2org.parse_offset("-14:00"), timezone(-timedelta(hours=14)))
        for bad in ("+14:30", "+99:99", "9", ""):
            with self.assertRaises(argparse.ArgumentTypeError):
                g2org.parse_offset(bad)

    def test_output_dir_mode_with_collision_resolution(self):
        source = self.tmp / "goals.json"
        goals = [goal(id="a", title="Same name"), goal(id="b", title="Same name"), goal(id="c", title="Same Name")]
        source.write_text(json.dumps(goals), encoding="utf-8")
        out_dir = self.tmp / "org"
        written, extra = g2org.convert(source, "", JST, output_dir=out_dir)
        self.assertEqual(written, 3)
        names = sorted(p.name for p in out_dir.iterdir())
        self.assertEqual(names, ["same-name-2.org", "same-name-3.org", "same-name.org"])
        for name in names:
            text = (out_dir / name).read_text(encoding="utf-8")
            self.assertIn("#+TITLE: Omi goals", text)
            self.assertIn("* TODO", text)

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
