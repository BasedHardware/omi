"""Tests for goals to markdown exporter recipe.

Pins frontmatter generation, progress bar calculation, boolean and numeric formatting,
grouping strategies (by type, by status), envelope unwrapping, traversal safety,
overwrite protection, and CLI conversions.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

# Ensure examples directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from goals_to_markdown import (
    parse_datetime,
    render_progress_bar,
    calculate_progress,
    format_goal_item,
    unwrap_goals,
    generate_frontmatter,
    goals_to_markdown,
    sanitize_filename,
    write_directory_export,
    main,
)


class TestGoalsToMarkdown(unittest.TestCase):
    def setUp(self):
        self.sample_goals = [
            {
                "id": "goal_01_read",
                "title": "Read 50 Pages Daily",
                "goal_type": "numeric",
                "current_value": 25.0,
                "target_value": 50.0,
                "min_value": 0.0,
                "max_value": 100.0,
                "unit": "pages",
                "is_active": True,
                "updated_at": "2026-09-27T08:00:00Z",
            },
            {
                "id": "goal_02_water",
                "title": "Drink 2 Liters Water",
                "goal_type": "numeric",
                "current_value": 2.0,
                "target_value": 2.0,
                "min_value": 0.0,
                "max_value": 3.0,
                "unit": "liters",
                "is_active": True,
                "updated_at": "2026-09-27T07:30:00Z",
            },
            {
                "id": "goal_03_meditate",
                "title": "Morning Meditation",
                "goal_type": "boolean",
                "current_value": 1.0,
                "target_value": 1.0,
                "min_value": 0.0,
                "max_value": 1.0,
                "unit": None,
                "is_active": False,
                "updated_at": "2026-09-26T12:00:00Z",
            },
            {
                "id": "goal_04_stress",
                "title": "Keep Daily Stress Low",
                "goal_type": "scale",
                "current_value": 3.0,
                "target_value": 5.0,
                "min_value": 1.0,
                "max_value": 10.0,
                "unit": "/10",
                "is_active": True,
                "updated_at": None,
            },
        ]

    def test_frontmatter_and_summary(self):
        md = goals_to_markdown(self.sample_goals, title="Personal Dashboard")
        self.assertIn("---", md)
        self.assertIn("type: goals", md)
        self.assertIn("total: 4", md)
        self.assertIn("active: 3", md)
        self.assertIn("completed: 1", md)
        self.assertIn("tags:", md)
        self.assertIn("  - omi", md)
        self.assertIn("  - goals", md)
        self.assertIn("# Personal Dashboard", md)

    def test_progress_bar_calculation(self):
        # 50% numeric
        pct, detail = calculate_progress(self.sample_goals[0])
        self.assertEqual(pct, 50.0)
        self.assertEqual(detail, "25/50 pages")

        bar = render_progress_bar(50.0)
        self.assertEqual(bar, "[█████░░░░░] 50%")

        # 100% numeric
        pct, detail = calculate_progress(self.sample_goals[1])
        self.assertEqual(pct, 100.0)
        self.assertEqual(detail, "2/2 liters")

        # Boolean done
        pct, detail = calculate_progress(self.sample_goals[2])
        self.assertEqual(pct, 100.0)
        self.assertEqual(detail, "Done")

        # Boolean not done
        not_done = {"goal_type": "boolean", "current_value": 0.0, "target_value": 1.0}
        pct, detail = calculate_progress(not_done)
        self.assertEqual(pct, 0.0)
        self.assertEqual(detail, "Not done")

    def test_goal_item_formatting(self):
        # Inactive / completed item has [x] checkbox
        line_meditate = format_goal_item(self.sample_goals[2])
        self.assertTrue(line_meditate.startswith("- [x] **Morning Meditation**"))
        self.assertIn("`#boolean`", line_meditate)
        self.assertIn("🆔 `goal_03_meditate`", line_meditate)

        # In-progress item has [ ] checkbox
        line_read = format_goal_item(self.sample_goals[0])
        self.assertTrue(line_read.startswith("- [ ] **Read 50 Pages Daily**"))
        self.assertIn("25/50 pages", line_read)

    def test_group_by_type(self):
        md = goals_to_markdown(self.sample_goals, group_by="type")
        self.assertIn("## 📊 Numeric Goals (2)", md)
        self.assertIn("## 🎯 Daily Habits & Boolean Targets (1)", md)
        self.assertIn("## 📈 Scale & Quality Metrics (1)", md)

    def test_group_by_status(self):
        md = goals_to_markdown(self.sample_goals, group_by="status")
        self.assertIn("## 🎯 Active Goals (3)", md)
        self.assertIn("## ✅ Completed / Inactive (1)", md)

    def test_envelope_unwrapping(self):
        raw_list = self.sample_goals
        self.assertEqual(len(unwrap_goals(raw_list)), 4)

        dict_envelope = {"goals": self.sample_goals}
        self.assertEqual(len(unwrap_goals(dict_envelope)), 4)

        items_envelope = {"items": self.sample_goals}
        self.assertEqual(len(unwrap_goals(items_envelope)), 4)

        empty_envelope = {"goals": []}
        self.assertEqual(len(unwrap_goals(empty_envelope)), 0)

        single_obj = self.sample_goals[0]
        self.assertEqual(len(unwrap_goals(single_obj)), 1)

        invalid_data = "not a list or dict"
        self.assertEqual(unwrap_goals(invalid_data), [])
        self.assertEqual(unwrap_goals(None), [])

    def test_directory_export_traversal_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            count = write_directory_export(self.sample_goals, out_dir, group_by="type")
            self.assertEqual(count, 3)

            numeric_file = out_dir / "numeric_goals.md"
            self.assertTrue(numeric_file.exists())
            content = numeric_file.read_text(encoding="utf-8")
            self.assertIn("Read 50 Pages Daily", content)
            self.assertIn("Drink 2 Liters Water", content)

    def test_sanitize_filename(self):
        self.assertEqual(sanitize_filename("valid_name.md"), "valid_name.md")
        self.assertEqual(sanitize_filename("../../../etc/passwd"), "etc_passwd")
        self.assertEqual(sanitize_filename("bad:name/test?"), "bad_name_test")

    def test_file_output_and_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "goals.json"
            out_file = Path(tmpdir) / "Goals.md"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            # Positional CLI execution
            exit_code = main([str(json_file), str(out_file)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("Read 50 Pages Daily", content)

            # Refuse overwrite without --force
            exit_code_overwrite = main([str(json_file), str(out_file)])
            self.assertNotEqual(exit_code_overwrite, 0)

            # Overwrite with --force
            exit_code_forced = main([str(json_file), str(out_file), "--force"])
            self.assertEqual(exit_code_forced, 0)

    def test_active_only_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "goals.json"
            out_file = Path(tmpdir) / "ActiveGoals.md"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            exit_code = main([str(json_file), "-o", str(out_file), "--active-only"])
            self.assertEqual(exit_code, 0)

            content = out_file.read_text(encoding="utf-8")
            self.assertIn("goal_01_read", content)
            self.assertNotIn("goal_03_meditate", content)


if __name__ == "__main__":
    unittest.main()
