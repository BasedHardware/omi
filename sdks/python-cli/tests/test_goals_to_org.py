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
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

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

    def test_progress_uses_target_instead_of_scale_maximum(self):
        for goal_type in ("numeric", "scale"):
            for current, percent, state in ((2.5, 50, "TODO"), (5, 100, "DONE"), (8, 100, "DONE")):
                with self.subTest(goal_type=goal_type, current=current):
                    (_, done), org = self.export(
                        [goal(goal_type=goal_type, target_value=5, current_value=current, max_value=10)]
                    )
                    self.assertIn(f"* {state} Read books [{percent}%] [{current}/5]", org)
                    self.assertEqual(done, int(state == "DONE"))

    def test_progress_uses_minimum_as_baseline(self):
        _, org = self.export([goal(current_value=4, min_value=2, target_value=6, max_value=10)])
        self.assertIn("* TODO Read books [50%] [4/6]", org)
        _, org = self.export([goal(current_value=6, min_value=2, target_value=6, max_value=10)])
        self.assertIn("* DONE Read books [100%] [6/6]", org)

    def test_progress_without_bounds_and_below_baseline(self):
        _, org = self.export([goal(current_value=3, target_value=6, min_value=None, max_value=None)])
        self.assertIn("* TODO Read books [50%] [3/6]", org)
        _, org = self.export([goal(current_value=1, min_value=2, target_value=6)])
        self.assertIn("* TODO Read books [0%] [1/6]", org)

    def test_missing_metrics_remain_todo(self):
        _, org = self.export([{"id": "q1", "title": "Reflect more", "is_active": True}])
        self.assertIn("* TODO Reflect more :scale:", org)
        self.assertIn("- Progress: n/a (no metrics)", org)
        self.assertNotIn("[0/0]", org)

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

    def test_property_drawer_precedes_body_in_all_grouping_modes(self):
        for group_by in ("none", "status", "type"):
            with self.subTest(group_by=group_by):
                _, org = self.export([goal()], group_by=group_by)
                lines = org.splitlines()
                heading = next(i for i, line in enumerate(lines) if "TODO Read books" in line)
                self.assertEqual(lines[heading + 1], ":PROPERTIES:")
                end = lines.index(":END:", heading)
                self.assertTrue(lines[end + 1].startswith("- Progress: "))

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
        self.assertIn("* Active\n** TODO active one", org)
        self.assertIn("* Completed & archived\n** DONE inactive one", org)
        _, org2 = self.export([goal(), goal(id="s", title="s", goal_type="scale")], group_by="type")
        self.assertIn("* numeric\n** TODO", org2)
        self.assertIn("* scale\n** TODO", org2)

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

    def test_output_dir_preserves_existing_file(self):
        source = self.tmp / "goals.json"
        source.write_text(json.dumps([goal()]), encoding="utf-8")
        out_dir = self.tmp / "org"
        out_dir.mkdir()
        existing = out_dir / "read-books.org"
        original = b"User notes that must survive\n"
        existing.write_bytes(original)
        with self.assertRaises(FileExistsError):
            g2org.convert(source, "", JST, output_dir=out_dir)
        self.assertTrue(existing.exists())
        self.assertEqual(existing.read_bytes(), original)

    def test_failed_creation_never_attempts_cleanup(self):
        source = self.tmp / "goals.json"
        source.write_text(json.dumps([goal()]), encoding="utf-8")
        original_open = Path.open

        def denied_open(path, mode="r", *args, **kwargs):
            if mode == "xb":
                raise PermissionError("creation denied")
            return original_open(path, mode, *args, **kwargs)

        for directory_mode in (False, True):
            with self.subTest(directory_mode=directory_mode):
                with patch.object(Path, "open", denied_open), patch.object(Path, "unlink") as unlink:
                    with self.assertRaisesRegex(PermissionError, "creation denied"):
                        g2org.convert(
                            source,
                            self.tmp / "out.org",
                            JST,
                            output_dir=self.tmp / "org" if directory_mode else None,
                        )
                    unlink.assert_not_called()

    def test_failed_write_removes_only_new_partial_file(self):
        source = self.tmp / "goals.json"
        source.write_text(json.dumps([goal()]), encoding="utf-8")
        original_open = Path.open
        unrelated = self.tmp / "keep.org"
        unrelated.write_bytes(b"keep me")

        def failing_open(path, mode="r", *args, **kwargs):
            handle = original_open(path, mode, *args, **kwargs)
            if mode == "xb":

                def fail_write(payload):
                    handle.write(payload[:10])
                    handle.flush()
                    raise OSError("simulated disk full")

                writer = MagicMock(wraps=handle)
                writer.write.side_effect = fail_write
                writer.__enter__.return_value = writer
                writer.__exit__.side_effect = lambda *exc: handle.close()
                return writer
            return handle

        for directory_mode in (False, True):
            with self.subTest(directory_mode=directory_mode):
                destination = self.tmp / "out.org"
                out_dir = self.tmp / "org"
                with patch.object(Path, "open", failing_open):
                    with self.assertRaisesRegex(OSError, "simulated disk full"):
                        g2org.convert(source, destination, JST, output_dir=out_dir if directory_mode else None)
                target = out_dir / "read-books.org" if directory_mode else destination
                self.assertFalse(target.exists())
                self.assertEqual(unrelated.read_bytes(), b"keep me")

    def test_cli_stdin_accepts_utf8_with_and_without_bom(self):
        for bom in (False, True):
            with self.subTest(bom=bom):
                destination = self.tmp / f"stdin-{bom}.org"
                payload = json.dumps([goal(title="Read \u4e66\u7c4d")], ensure_ascii=False)
                result = subprocess.run(
                    [sys.executable, str(script_path), "-", str(destination), "--utc-offset", "+00:00"],
                    input=payload.encode("utf-8-sig" if bom else "utf-8"),
                    capture_output=True,
                    env={**os.environ, "PYTHONUTF8": "1"},
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8"))
                self.assertIn("* TODO Read \u4e66\u7c4d [50%]", destination.read_text(encoding="utf-8"))

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
