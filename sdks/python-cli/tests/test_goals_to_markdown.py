"""Tests for goals to markdown checklist exporter recipe.

Validates pure standard library implementation, frontmatter structure,
hierarchical checklist trees, progress calculations, status/type grouping,
strict path traversal defense, atomic file replacement, multi-file deduplication,
corrupted field resilience, and CLI subprocess execution.
"""

from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# Dynamically load goals_to_markdown recipe
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_markdown.py"
spec = importlib.util.spec_from_file_location("goals_to_markdown", script_path)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load module from {script_path}")
g2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2m)


class TestGoalsToMarkdown(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_goals = [
            {
                "id": "goal_run_100k",
                "title": "Run 100 Kilometers this Month",
                "goal_type": "numeric",
                "current_value": 60.0,
                "target_value": 100.0,
                "min_value": 0.0,
                "unit": "km",
                "status": "focused",
                "is_active": True,
                "desired_outcome": "Improve marathon cardiovascular endurance.",
                "why_it_matters": "Build stamina for the upcoming half-marathon.",
                "subtasks": [
                    {"title": "Run 25 km in week 1", "completed": True},
                    {"title": "Run 25 km in week 2", "completed": True},
                    {"title": "Complete 30 km long run", "completed": False},
                ],
                "success_criteria": [
                    "Maintain average pace under 5:30 min/km",
                    "Complete final 20 km taper run",
                ],
                "created_at": "2026-10-01T08:00:00Z",
                "updated_at": "2026-10-02T12:00:00Z",
            },
            {
                "id": "goal_meditation",
                "title": "Morning Meditation Routine",
                "goal_type": "boolean",
                "current_value": True,
                "target_value": 1.0,
                "min_value": 0.0,
                "status": "achieved",
                "is_active": True,
                "desired_outcome": "Establish daily mindfulness practice.",
                "subtasks": [
                    "Meditate for 15 minutes before breakfast",
                    "Log streak in Omi daily review",
                ],
                "success_criteria": [
                    "Consistently practice for 14 consecutive days",
                ],
                "created_at": "2026-09-20T07:00:00Z",
                "updated_at": "2026-09-25T07:00:00Z",
            },
            {
                "id": "goal_spanish",
                "title": "Learn 500 Spanish Words",
                "goal_type": "scale",
                "current_value": 50.0,
                "target_value": 500.0,
                "min_value": 0.0,
                "unit": "words",
                "status": "paused",
                "is_active": False,
                "subtasks": [],
                "success_criteria": [],
                "created_at": "2026-08-01T10:00:00Z",
                "updated_at": "2026-08-15T18:00:00Z",
            },
        ]

    def test_frontmatter_and_summary_generation(self) -> None:
        md = g2m.goals_to_markdown(self.sample_goals, title="Sprint Goals")
        self.assertIn("---", md)
        self.assertIn("type: goals", md)
        self.assertRegex(md, r"(?m)^total: 3$")
        self.assertRegex(md, r"(?m)^active: 1$")
        self.assertRegex(md, r"(?m)^achieved: 1$")
        self.assertRegex(md, r"(?m)^inactive: 1$")
        self.assertIn("tags:", md)
        self.assertIn("  - omi", md)
        self.assertIn("  - goals", md)

        self.assertIn("# Sprint Goals", md)
        self.assertIn(
            "> **Summary:** 1 active, 1 achieved, 1 inactive (3 total).",
            md,
        )

    def test_hierarchical_checklist_tree_rendering(self) -> None:
        goal = self.sample_goals[0]
        tree = g2m.format_goal_tree(goal)

        # Top-level item
        self.assertIn("- [ ] **Run 100 Kilometers this Month**", tree)
        self.assertIn("`[======....] 60.0%`", tree)
        self.assertIn("*(60 / 100 km · `#goal_run_100k`)*", tree)

        # Outcomes and why blockquotes
        self.assertIn("  > **Outcome:** Improve marathon cardiovascular endurance.", tree)
        self.assertIn("  > **Why:** Build stamina for the upcoming half-marathon.", tree)

        # Subtasks indented
        self.assertIn("  - [x] Run 25 km in week 1", tree)
        self.assertIn("  - [x] Run 25 km in week 2", tree)
        self.assertIn("  - [ ] Complete 30 km long run", tree)

        # Success criteria indented
        self.assertIn("  - [ ] Maintain average pace under 5:30 min/km", tree)
        self.assertIn("  - [ ] Complete final 20 km taper run", tree)

    def test_achieved_goal_checked_boxes(self) -> None:
        goal = self.sample_goals[1]
        tree = g2m.format_goal_tree(goal)

        # Top-level item checked
        self.assertIn("- [x] **Morning Meditation Routine**", tree)
        self.assertIn("`[==========] 100.0%`", tree)
        self.assertIn("*(Boolean · `#goal_meditation`)*", tree)

        # Subtasks and success criteria checked when goal is achieved
        self.assertIn("  - [x] Meditate for 15 minutes before breakfast", tree)
        self.assertIn("  - [x] Consistently practice for 14 consecutive days", tree)

    def test_progress_calculation(self) -> None:
        # Standard ascending numeric
        g_asc = {"goal_type": "numeric", "current_value": 75, "target_value": 100, "min_value": 0}
        self.assertEqual(g2m.calculate_progress(g_asc), 75.0)

        # Descending (inverse) goal (target < min)
        g_desc = {"goal_type": "numeric", "current_value": 20, "target_value": 10, "min_value": 30}
        # (30 - 20) / (30 - 10) = 10 / 20 = 50.0%
        self.assertEqual(g2m.calculate_progress(g_desc), 50.0)

        # Boolean goal
        self.assertEqual(g2m.calculate_progress({"goal_type": "boolean", "current_value": True}), 100.0)
        self.assertEqual(g2m.calculate_progress({"goal_type": "boolean", "current_value": False}), 0.0)
        self.assertEqual(g2m.calculate_progress({"goal_type": "boolean", "current_value": "yes"}), 100.0)
        self.assertEqual(g2m.calculate_progress({"goal_type": "boolean", "status": "achieved"}), 100.0)

        # Target equals min_value boundary
        g_eq = {"goal_type": "numeric", "current_value": 5, "target_value": 5, "min_value": 5}
        self.assertEqual(g2m.calculate_progress(g_eq), 100.0)

        # Clamping
        g_over = {"goal_type": "numeric", "current_value": 150, "target_value": 100, "min_value": 0}
        self.assertEqual(g2m.calculate_progress(g_over), 100.0)
        g_under = {"goal_type": "numeric", "current_value": -10, "target_value": 100, "min_value": 0}
        self.assertEqual(g2m.calculate_progress(g_under), 0.0)

    def test_progress_bar_rendering(self) -> None:
        bar_0 = g2m.render_progress_bar(0.0)
        self.assertEqual(bar_0, "`[..........] 0.0%`")

        bar_50 = g2m.render_progress_bar(50.0)
        self.assertEqual(bar_50, "`[=====.....] 50.0%`")

        bar_100 = g2m.render_progress_bar(100.0)
        self.assertEqual(bar_100, "`[==========] 100.0%`")

    def test_status_grouping(self) -> None:
        md = g2m.goals_to_markdown(self.sample_goals, group_by="status")
        self.assertIn("## 🟢 Active Goals", md)
        self.assertIn("## ✅ Achieved Goals", md)
        self.assertIn("## ⚪ Inactive Goals", md)
        self.assertIn("Run 100 Kilometers this Month", md)
        self.assertIn("Morning Meditation Routine", md)
        self.assertIn("Learn 500 Spanish Words", md)

    def test_type_grouping(self) -> None:
        md = g2m.goals_to_markdown(self.sample_goals, group_by="type")
        self.assertIn("## 🎯 Numeric Goals", md)
        self.assertIn("## 📊 Scale Goals", md)
        self.assertIn("## 🔘 Boolean Goals", md)
        self.assertIn("Run 100 Kilometers this Month", md)
        self.assertIn("Learn 500 Spanish Words", md)
        self.assertIn("Morning Meditation Routine", md)

    def test_flat_grouping(self) -> None:
        md = g2m.goals_to_markdown(self.sample_goals, group_by="none")
        self.assertNotIn("## 🟢 Active Goals", md)
        self.assertNotIn("## 🎯 Numeric Goals", md)
        self.assertIn("- [ ] **Run 100 Kilometers this Month**", md)
        self.assertIn("- [x] **Morning Meditation Routine**", md)
        self.assertIn("- [ ] **Learn 500 Spanish Words**", md)

    def test_empty_goals_rendering(self) -> None:
        md = g2m.goals_to_markdown([])
        self.assertIn("total: 0", md)
        self.assertIn("overall_progress: 0.0%", md)
        self.assertIn("_No goals found._", md)

    def test_path_traversal_defense(self) -> None:
        forbidden_paths = [
            "../secret.md",
            "folder/../../secret.md",
            "..\\windows\\secret.md",
            "a/b/../../../root.md",
        ]
        for bad_path in forbidden_paths:
            with self.assertRaises(ValueError):
                g2m.validate_safe_path(bad_path)

            with self.assertRaises(ValueError):
                g2m.atomic_write_file(bad_path, "malicious content")

    def test_atomic_file_replacement_and_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "output.md"
            content1 = "# Initial Goals"
            content2 = "# Overwritten Goals"

            # 1. First write succeeds
            g2m.atomic_write_file(out_file, content1, force=False)
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.read_text(encoding="utf-8"), content1)

            # 2. Writing without force raises FileExistsError
            with self.assertRaises(FileExistsError):
                g2m.atomic_write_file(out_file, content2, force=False)
            self.assertEqual(out_file.read_text(encoding="utf-8"), content1)

            # 3. Writing with force overwrites safely
            g2m.atomic_write_file(out_file, content2, force=True)
            self.assertEqual(out_file.read_text(encoding="utf-8"), content2)

            # Verify no temporary files left in directory
            tmp_files = [f.name for f in Path(tmp_dir).iterdir() if f.name.startswith(".output.md.tmp_")]
            self.assertEqual(len(tmp_files), 0)

    def test_multi_file_deduplication(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_v1 = Path(tmp_dir) / "page1.json"
            file_v2 = Path(tmp_dir) / "page2.json"

            # Goal with earlier timestamp
            item_v1 = {
                "id": "goal_marathon",
                "title": "Train for Marathon (v1)",
                "current_value": 20.0,
                "target_value": 42.0,
                "updated_at": "2026-10-01T10:00:00Z",
            }
            # Same Goal with later timestamp (should win)
            item_v2 = {
                "id": "goal_marathon",
                "title": "Train for Marathon (v2 Updated)",
                "current_value": 35.0,
                "target_value": 42.0,
                "updated_at": "2026-10-02T15:00:00Z",
            }
            # Distinct goal
            item_other = {
                "id": "goal_swim",
                "title": "Swim 2k",
                "current_value": 1.0,
                "target_value": 2.0,
            }

            file_v1.write_text(json.dumps([item_v1, item_other]), encoding="utf-8")
            file_v2.write_text(json.dumps([item_v2]), encoding="utf-8")

            merged = g2m.load_and_deduplicate([str(file_v1), str(file_v2)])
            self.assertEqual(len(merged), 2)

            marathon_item = next(it for it in merged if it["id"] == "goal_marathon")
            self.assertEqual(marathon_item["title"], "Train for Marathon (v2 Updated)")
            self.assertEqual(marathon_item["current_value"], 35.0)

    def test_extract_goals_various_formats(self) -> None:
        # 1. Plain list
        raw_list = [{"id": "g1", "title": "G1"}]
        self.assertEqual(len(g2m.extract_goals(raw_list)), 1)

        # 2. Wrapped in "goals"
        raw_goals = {"goals": [{"id": "g2", "title": "G2"}]}
        self.assertEqual(len(g2m.extract_goals(raw_goals)), 1)

        # 3. Wrapped in "items"
        raw_items = {"items": [{"id": "g3", "title": "G3"}]}
        self.assertEqual(len(g2m.extract_goals(raw_items)), 1)

        # 4. Single dictionary
        raw_single = {"id": "g4", "title": "G4"}
        self.assertEqual(len(g2m.extract_goals(raw_single)), 1)

        # 5. Missing ID fallback
        raw_noid = {"title": "Goal Without ID"}
        extracted = g2m.extract_goals(raw_noid)
        self.assertEqual(len(extracted), 1)
        self.assertTrue(extracted[0]["id"].startswith("goal_"))

    def test_corrupted_fields_and_resilience(self) -> None:
        # None and NaN numbers
        g_dirty = {
            "id": "dirty_1",
            "title": "  Dirty Goal \n with newlines  ",
            "current_value": float("nan"),
            "target_value": None,
            "min_value": "invalid_string",
            "subtasks": "not a list",
            "success_criteria": None,
        }
        self.assertEqual(g2m.safe_float(float("nan")), 0.0)
        self.assertEqual(g2m.safe_float(float("inf")), 0.0)
        self.assertEqual(g2m.safe_float("invalid"), 0.0)
        self.assertEqual(g2m.safe_float("123.45"), 123.45)

        tree = g2m.format_goal_tree(g_dirty)
        self.assertIn("Dirty Goal with newlines", tree)

        # Untitled fallback
        g_empty = {"id": "empty_title", "title": ""}
        tree_empty = g2m.format_goal_tree(g_empty)
        self.assertIn("Untitled Goal", tree_empty)

    def test_utf8_bom_handling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bom_file = Path(tmp_dir) / "bom.json"
            content = json.dumps([{"id": "bom_goal", "title": "BOM Goal"}]).encode("utf-8-sig")
            bom_file.write_bytes(content)

            goals = g2m.load_and_deduplicate([str(bom_file)])
            self.assertEqual(len(goals), 1)
            self.assertEqual(goals[0]["id"], "bom_goal")

    def test_cli_output_dir_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "goals.json"
            input_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            out_dir = Path(tmp_dir) / "notes"

            # Test --group-by type into directory
            ret = g2m.main(
                [
                    str(input_file),
                    "-d",
                    str(out_dir),
                    "--group-by",
                    "type",
                    "-f",
                ]
            )
            self.assertEqual(ret, 0)
            self.assertTrue((out_dir / "numeric_goals.md").exists())
            self.assertTrue((out_dir / "scale_goals.md").exists())
            self.assertTrue((out_dir / "boolean_goals.md").exists())

    def test_cli_filter_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            input_file = Path(tmp_dir) / "goals.json"
            input_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")
            out_file = Path(tmp_dir) / "filtered.md"

            # Filter by status: achieved
            ret = g2m.main(
                [
                    str(input_file),
                    "-o",
                    str(out_file),
                    "--status",
                    "achieved",
                    "-f",
                ]
            )
            self.assertEqual(ret, 0)
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("total: 1", content)
            self.assertIn("Morning Meditation Routine", content)
            self.assertNotIn("Run 100 Kilometers", content)

    def test_subprocess_stdin_pipeline(self) -> None:
        """Verify real CLI subprocess invocation via Unix-like stdin pipeline."""
        payload = json.dumps(
            [
                {
                    "id": "subp_goal",
                    "title": "Subprocess Pipe Goal",
                    "goal_type": "numeric",
                    "current_value": 42,
                    "target_value": 100,
                    "unit": "%",
                }
            ]
        ).encode("utf-8")

        proc = subprocess.run(
            [sys.executable, str(script_path), "-"],
            input=payload,
            capture_output=True,
            check=True,
        )
        self.assertEqual(proc.returncode, 0)
        output_str = proc.stdout.decode("utf-8")
        self.assertIn("---", output_str)
        self.assertIn("type: goals", output_str)
        self.assertIn("Subprocess Pipe Goal", output_str)
        self.assertIn("`[====......] 42.0%`", output_str)

    def test_subprocess_traversal_rejection(self) -> None:
        """Verify CLI rejects traversal path with non-zero exit code and error message."""
        proc = subprocess.run(
            [sys.executable, str(script_path), "-", "-o", "../forbidden.md"],
            input=b"[]",
            capture_output=True,
        )
        self.assertNotEqual(proc.returncode, 0)
        err_msg = proc.stderr.decode("utf-8")
        self.assertIn("Path traversal sequence '..' is forbidden", err_msg)

    def test_safe_float_overflow_protection(self) -> None:
        """Verify safe_float gracefully handles massive integers and overflow strings without crashing."""
        huge_int = 10**1000
        self.assertEqual(g2m.safe_float(huge_int, default=42.0), 42.0)
        self.assertEqual(g2m.safe_float("1e1000", default=7.0), 7.0)

    def test_descending_goal_missing_current_value(self) -> None:
        """Verify descending goal with current_value=None defaults to 0% progress and uncompleted."""
        goal = {
            "id": "goal_screen_time",
            "title": "Reduce Screen Time to 2 Hours",
            "goal_type": "numeric",
            "current_value": None,
            "target_value": 2.0,
            "min_value": 8.0,
            "status": "in_progress",
        }
        # Must not treat None as 0 and falsely declare 100% progress
        self.assertEqual(g2m.calculate_progress(goal), 0.0)
        self.assertFalse(g2m.is_goal_completed(goal))

    def test_qualitative_goal_handling(self) -> None:
        """Verify qualitative goal with target_value == min_value is only completed if marked achieved."""
        qual_goal = {
            "id": "goal_read_book",
            "title": "Read Domain-Driven Design",
            "goal_type": "scale",
            "current_value": None,
            "target_value": 0.0,
            "min_value": 0.0,
            "status": "active",
        }
        self.assertEqual(g2m.calculate_progress(qual_goal), 0.0)
        self.assertFalse(g2m.is_goal_completed(qual_goal))

        # When completed, progress is 100.0%
        qual_goal["status"] = "completed"
        self.assertEqual(g2m.calculate_progress(qual_goal), 100.0)
        self.assertTrue(g2m.is_goal_completed(qual_goal))

    def test_extract_goals_single_dict_wrapper(self) -> None:
        """Verify top-level dictionary wrapping a single goal object is correctly unwrapped."""
        payload = {
            "goals": {
                "id": "wrapped_goal_1",
                "title": "Wrapped Goal Title",
                "goal_type": "numeric",
                "current_value": 5,
                "target_value": 10,
            }
        }
        extracted = g2m.extract_goals(payload)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["id"], "wrapped_goal_1")
        self.assertEqual(extracted[0]["title"], "Wrapped Goal Title")

    def test_subtask_string_boolean_false(self) -> None:
        """Verify subtask with string completed='false' renders unchecked [ ] instead of checked [x]."""
        goal = {
            "id": "goal_subtasks_bool",
            "title": "Subtask String Boolean Check",
            "goal_type": "numeric",
            "current_value": 0,
            "target_value": 10,
            "subtasks": [
                {"title": "Pending Item", "completed": "false"},
                {"title": "Done Item", "completed": "true"},
            ],
        }
        tree = g2m.format_goal_tree(goal)
        self.assertIn("  - [ ] Pending Item", tree)
        self.assertIn("  - [x] Done Item", tree)


if __name__ == "__main__":
    unittest.main()
