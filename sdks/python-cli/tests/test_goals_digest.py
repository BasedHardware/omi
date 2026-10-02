"""Unit tests for the goals_digest recipe.

Verifies:
- Resilient loading and envelope unwrapping.
- Multi-file ID deduplication preserving latest updated_at.
- KPI calculations and Achieved status/progress consistency.
- Inactive status precedence over progress completion.
- Markdown table cell hygiene (escaping pipes and line breaks).
- Goal-type breakdown aggregation.
- ASCII progress bar rendering.
- Path traversal and symlink protections.
- Atomic non-destructive writes.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any, Dict, List
import unittest

# Dynamically import goals_digest from examples
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_digest.py"
spec = importlib.util.spec_from_file_location("goals_digest", script_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load module from {script_path}")
gd = importlib.util.module_from_spec(spec)
sys.modules["goals_digest"] = gd
spec.loader.exec_module(gd)


SAMPLE_GOALS_PAGE1: List[Dict[str, Any]] = [
    {
        "id": "goal_1",
        "title": "Read 20 books",
        "goal_type": "numeric",
        "current_value": 10.0,
        "target_value": 20.0,
        "unit": "books",
        "is_active": True,
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-10T12:00:00Z",
    },
    {
        "id": "goal_2",
        "title": "Run 50km",
        "goal_type": "scale",
        "current_value": 50.0,
        "target_value": 50.0,
        "unit": "km",
        "is_active": True,
        "created_at": "2026-09-02T10:00:00Z",
        "updated_at": "2026-09-15T12:00:00Z",
    },
    {
        "id": "goal_3",
        "title": "Old goal to abandon",
        "goal_type": "boolean",
        "current_value": 0,
        "target_value": 1,
        "is_active": False,
        "status": "archived",
        "created_at": "2026-08-01T10:00:00Z",
        "updated_at": "2026-08-05T12:00:00Z",
    },
]

# Page 2 contains an updated version of goal_1 and a new goal_4
SAMPLE_GOALS_PAGE2: List[Dict[str, Any]] = [
    {
        "id": "goal_1",
        "title": "Read 20 books",
        "goal_type": "numeric",
        "current_value": 20.0,
        "target_value": 20.0,
        "unit": "books",
        "is_active": True,
        "created_at": "2026-09-01T10:00:00Z",
        "updated_at": "2026-09-25T18:00:00Z",
    },
    {
        "id": "goal_4",
        "title": "Meditate daily",
        "goal_type": "boolean",
        "current_value": True,
        "target_value": 1,
        "is_active": True,
        "created_at": "2026-09-20T10:00:00Z",
        "updated_at": "2026-09-22T10:00:00Z",
    },
]


class TestGoalsDigest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_deduplication_and_multi_file_loading(self) -> None:
        p1 = self.dir_path / "page1.json"
        p2 = self.dir_path / "page2.json"
        p1.write_text(json.dumps(SAMPLE_GOALS_PAGE1), encoding="utf-8")
        p2.write_text(json.dumps(SAMPLE_GOALS_PAGE2), encoding="utf-8")

        loaded = gd.load_and_deduplicate([p1, p2])
        self.assertEqual(len(loaded), 4)

        by_id = {g["id"]: g for g in loaded}
        self.assertEqual(by_id["goal_1"]["current_value"], 20.0)
        self.assertEqual(by_id["goal_1"]["updated_at"], "2026-09-25T18:00:00Z")

    def test_calculate_kpis(self) -> None:
        p1 = self.dir_path / "page1.json"
        p2 = self.dir_path / "page2.json"
        p1.write_text(json.dumps(SAMPLE_GOALS_PAGE1), encoding="utf-8")
        p2.write_text(json.dumps(SAMPLE_GOALS_PAGE2), encoding="utf-8")

        loaded = gd.load_and_deduplicate([p1, p2])
        kpis = gd.calculate_kpis(loaded)

        self.assertEqual(kpis.total_goals, 4)
        self.assertEqual(kpis.achieved_goals, 3)
        self.assertEqual(kpis.inactive_goals, 1)
        self.assertEqual(kpis.active_goals, 0)
        self.assertAlmostEqual(kpis.overall_progress, 75.0, places=1)

    def test_achieved_status_and_progress_consistency(self) -> None:
        goal_a = {
            "id": "g_comp",
            "title": "Early finish project",
            "goal_type": "scale",
            "current_value": 5,
            "target_value": 10,
            "status": "completed",
        }
        goal_b = {
            "id": "g_100",
            "title": "Full progress goal",
            "goal_type": "numeric",
            "current_value": 10,
            "target_value": 10,
        }

        prog_a = gd.calculate_progress(goal_a)
        cat_a, label_a = gd.determine_status(goal_a, prog_a)
        self.assertEqual(cat_a, "achieved")
        self.assertIn("Achieved", label_a)

        prog_b = gd.calculate_progress(goal_b)
        cat_b, label_b = gd.determine_status(goal_b, prog_b)
        self.assertEqual(cat_b, "achieved")
        self.assertIn("Achieved", label_b)

        kpi = gd.calculate_kpis([goal_a, goal_b])
        self.assertEqual(kpi.achieved_goals, 2)

    def test_inactive_precedence(self) -> None:
        """Archived or inactive goals with 100% progress must not be marked achieved."""
        archived_goal = {
            "id": "g_arch",
            "title": "Abandoned goal that reached 100",
            "goal_type": "numeric",
            "current_value": 10,
            "target_value": 10,
            "is_active": False,
            "status": "archived",
        }
        prog = gd.calculate_progress(archived_goal)
        self.assertEqual(prog, 100.0)
        cat, label = gd.determine_status(archived_goal, prog)
        self.assertEqual(cat, "inactive")
        self.assertIn("Inactive", label)

        kpis = gd.calculate_kpis([archived_goal])
        self.assertEqual(kpis.inactive_goals, 1)
        self.assertEqual(kpis.achieved_goals, 0)

    def test_markdown_table_escaping(self) -> None:
        nasty_goal = {
            "id": "g_nasty",
            "title": "Refactor parser | add tests\nand docs",
            "goal_type": "scale",
            "current_value": 5,
            "target_value": 10,
            "unit": "PRs | commits per day",
        }
        digest = gd.generate_markdown_digest([nasty_goal])
        goal_rows = [line for line in digest.splitlines() if "Refactor parser" in line]
        self.assertEqual(len(goal_rows), 1)
        row = goal_rows[0]

        unescaped_pipes = [
            i
            for i, c in enumerate(row)
            if c == "|" and (i == 0 or row[i - 1] != "\\")
        ]
        self.assertEqual(len(unescaped_pipes), 7, f"Goal row has torn columns: {row}")
        self.assertIn("Refactor parser \\| add tests and docs", digest)
        self.assertIn("PRs \\| commits per day", digest)

    def test_ascii_progress_bar_bounds(self) -> None:
        self.assertIn("[..........] 0.0%", gd.render_progress_bar(0.0))
        self.assertIn("[=====.....] 50.0%", gd.render_progress_bar(50.0))
        self.assertIn("[==========] 100.0%", gd.render_progress_bar(100.0))
        self.assertIn("[==========] 125.0%", gd.render_progress_bar(125.0))
        self.assertIn("[..........] -10.0%", gd.render_progress_bar(-10.0))

    def test_envelope_unwrapping(self) -> None:
        test_cases = [
            json.dumps({"goals": [{"id": "1", "title": "A"}]}),
            json.dumps({"items": [{"id": "2", "title": "B"}]}),
            json.dumps({"data": [{"id": "3", "title": "C"}]}),
            json.dumps({"results": [{"id": "4", "title": "D"}]}),
            json.dumps({"id": "5", "title": "Single Dict"}),
        ]
        for src in test_cases:
            goals = gd.extract_goals(src, "test_envelope")
            self.assertEqual(len(goals), 1)

    def test_missing_id_synthesis(self) -> None:
        raw = json.dumps([{"title": "Goal without id", "current_value": 5, "target_value": 10}])
        goals = gd.extract_goals(raw, "synthetic_test")
        self.assertEqual(len(goals), 1)
        self.assertTrue(goals[0]["id"].startswith("goal_"))

    def test_empty_input_handling(self) -> None:
        kpis = gd.calculate_kpis([])
        self.assertEqual(kpis.total_goals, 0)
        self.assertEqual(kpis.overall_progress, 0.0)

        digest = gd.generate_markdown_digest([])
        self.assertIn("Total Goals", digest)
        self.assertIn("No goals found matching criteria", digest)

    def test_path_traversal_guard(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            gd.write_digest("# test", "../forbidden.md")
        self.assertIn("Path traversal sequence '..' is forbidden", str(ctx.exception))

    def test_symlink_rejection(self) -> None:
        target_file = self.dir_path / "actual.md"
        target_file.write_text("# Target", encoding="utf-8")
        link_file = self.dir_path / "symlink.md"
        os.symlink(target_file, link_file)

        with self.assertRaises(ValueError) as ctx:
            gd.write_digest("# New Content", link_file, force=True)
        self.assertIn("symlink", str(ctx.exception).lower())

    def test_refuse_overwrite_without_force(self) -> None:
        target = self.dir_path / "existing.md"
        target.write_text("initial content", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            gd.write_digest("# new content", target, force=False)

        self.assertEqual(target.read_text(encoding="utf-8"), "initial content")

    def test_atomic_write_with_force(self) -> None:
        target = self.dir_path / "report.md"
        target.write_text("old", encoding="utf-8")

        gd.write_digest("# Brand New Content", target, force=True)
        self.assertEqual(target.read_text(encoding="utf-8"), "# Brand New Content")

    def test_type_breakdown_aggregation(self) -> None:
        goals = [
            {"id": "1", "goal_type": "scale", "current_value": 5, "target_value": 10},
            {"id": "2", "goal_type": "scale", "current_value": 10, "target_value": 10},
            {"id": "3", "goal_type": "numeric", "current_value": 8, "target_value": 10},
        ]
        digest = gd.generate_markdown_digest(goals)
        self.assertIn("## Breakdown by Goal Type", digest)
        self.assertIn("| `scale` | 2 | 1 (50.0%) |", digest)
        self.assertIn("| `numeric` | 1 | 0 (0.0%) |", digest)

    def test_cli_end_to_end_file_and_filters(self) -> None:
        p = self.dir_path / "goals.json"
        out = self.dir_path / "digest.md"
        p.write_text(json.dumps(SAMPLE_GOALS_PAGE1), encoding="utf-8")

        saved_argv = sys.argv
        try:
            sys.argv = [
                "goals_digest.py",
                str(p),
                "-o",
                str(out),
                "--status",
                "achieved",
                "--type",
                "scale",
                "--title",
                "Custom Test Digest",
            ]
            gd.main()
        finally:
            sys.argv = saved_argv

        self.assertTrue(out.exists())
        content = out.read_text(encoding="utf-8")
        self.assertIn("# Custom Test Digest", content)
        self.assertIn("Run 50km", content)
        self.assertNotIn("Read 20 books", content)
        self.assertNotIn("Old goal to abandon", content)

    def test_cli_stdin_streaming(self) -> None:
        raw_json = json.dumps([{"id": "pipe_1", "title": "Piped Goal", "current_value": 1, "target_value": 1}])
        saved_stdin = sys.stdin
        saved_stdout = sys.stdout
        saved_argv = sys.argv
        try:
            sys.stdin = io.StringIO(raw_json)
            sys.stdout = io.StringIO()
            sys.argv = ["goals_digest.py", "-"]
            gd.main()
            output = sys.stdout.getvalue()
            self.assertIn("# Omi Goals Executive Digest", output)
            self.assertIn("Piped Goal", output)
        finally:
            sys.stdin = saved_stdin
            sys.stdout = saved_stdout
            sys.argv = saved_argv

    def test_trailing_backslash_markdown_escaping(self) -> None:
        nasty_goal = {
            "id": "g_backslash",
            "title": "Windows Path C:\\",
            "goal_type": "scale",
            "current_value": 5,
            "target_value": 10,
            "unit": "steps\\",
        }
        digest = gd.generate_markdown_digest([nasty_goal])
        goal_rows = [line for line in digest.splitlines() if "Windows Path" in line]
        self.assertEqual(len(goal_rows), 1)
        row = goal_rows[0]
        unescaped_pipes = [
            i
            for i, c in enumerate(row)
            if c == "|" and (i == 0 or row[i - 1] != "\\")
        ]
        self.assertEqual(len(unescaped_pipes), 7, f"Table row column count torn: {row}")

    def test_nan_and_inf_defense(self) -> None:
        dirty_goal = {
            "id": "nan_inf_goal",
            "title": "Extreme numerical boundaries",
            "current_value": float("nan"),
            "target_value": float("inf"),
            "min_value": float("-inf"),
        }
        prog = gd.calculate_progress(dirty_goal)
        self.assertEqual(prog, 0.0)

        bar = gd.render_progress_bar(float("nan"))
        self.assertIn("0.0%", bar)
        bar_inf = gd.render_progress_bar(float("inf"))
        self.assertIn("0.0%", bar_inf)

        digest = gd.generate_markdown_digest([dirty_goal])
        self.assertIn("Extreme numerical boundaries", digest)

    def test_overflow_defense(self) -> None:
        large_val = "1" + "0" * 400
        dirty_goal = {
            "id": "overflow_goal",
            "title": "Huge numbers",
            "current_value": large_val,
            "target_value": large_val,
        }
        prog = gd.calculate_progress(dirty_goal)
        self.assertEqual(prog, 0.0)

    def test_string_boolean_normalization(self) -> None:
        self.assertIs(gd.normalize_bool_flag("True"), True)
        self.assertIs(gd.normalize_bool_flag("false"), False)
        self.assertIs(gd.normalize_bool_flag("YES"), True)
        self.assertIs(gd.normalize_bool_flag("no"), False)
        self.assertIs(gd.normalize_bool_flag(1), True)
        self.assertIs(gd.normalize_bool_flag(0), False)
        self.assertIsNone(gd.normalize_bool_flag("other"))

    def test_mixed_slash_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            gd.write_digest("# content", "output/..\\evil.md")
        with self.assertRaises(ValueError):
            gd.write_digest("# content", "subdir\\../evil.md")

    def test_date_only_iso_parsing(self) -> None:
        dt = gd.parse_datetime("2026-12-31")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 12)
        self.assertEqual(dt.day, 31)

    def test_reverse_goal_progress(self) -> None:
        goal = {
            "id": "weight_loss",
            "title": "Lose weight to 70kg",
            "current_value": 85,
            "min_value": 100,
            "target_value": 70,
        }
        prog = gd.calculate_progress(goal)
        self.assertAlmostEqual(prog, 50.0, places=1)


if __name__ == "__main__":
    unittest.main()
