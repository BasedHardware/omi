"""Tests for goals to markdown exporter recipe.

Pins frontmatter generation, progress bar calculation, boolean and numeric formatting,
grouping strategies (by type, by status), envelope unwrapping, and traversal safety.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load goals_to_markdown example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_markdown.py"
spec = importlib.util.spec_from_file_location("goals_to_markdown", script_path)
assert spec is not None and spec.loader is not None
g2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2m)


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
        md = g2m.goals_to_markdown(self.sample_goals, title="Personal Dashboard")
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
        pct, detail = g2m.calculate_progress(self.sample_goals[0])
        self.assertEqual(pct, 50.0)
        self.assertEqual(detail, "25/50 pages")

        bar = g2m.render_progress_bar(50.0)
        self.assertEqual(bar, "[█████░░░░░] 50%")

        # 100% numeric
        pct, detail = g2m.calculate_progress(self.sample_goals[1])
        self.assertEqual(pct, 100.0)
        self.assertEqual(detail, "2/2 liters")

        # Boolean done
        pct, detail = g2m.calculate_progress(self.sample_goals[2])
        self.assertEqual(pct, 100.0)
        self.assertEqual(detail, "Done")

    def test_goal_item_formatting(self):
        # Inactive / completed item has [x] checkbox
        line_meditate = g2m.format_goal_item(self.sample_goals[2])
        self.assertTrue(line_meditate.startswith("- [x] **Morning Meditation**"))
        self.assertIn("`#boolean`", line_meditate)
        self.assertIn("🆔 `goal_03_meditate`", line_meditate)

        # In-progress item has [ ] checkbox
        line_read = g2m.format_goal_item(self.sample_goals[0])
        self.assertTrue(line_read.startswith("- [ ] **Read 50 Pages Daily**"))
        self.assertIn("25/50 pages", line_read)

    def test_group_by_type(self):
        md = g2m.goals_to_markdown(self.sample_goals, group_by="type")
        self.assertIn("## 📊 Numeric Goals (2)", md)
        self.assertIn("## 🎯 Daily Habits & Boolean Targets (1)", md)
        self.assertIn("## 📈 Scale & Quality Metrics (1)", md)

    def test_group_by_status(self):
        md = g2m.goals_to_markdown(self.sample_goals, group_by="status")
        self.assertIn("## 🎯 Active Goals (3)", md)
        self.assertIn("## ✅ Completed / Inactive (1)", md)

    def test_envelope_unwrapping(self):
        raw_list = self.sample_goals
        self.assertEqual(len(g2m.unwrap_goals(raw_list)), 4)

        dict_envelope = {"goals": self.sample_goals}
        self.assertEqual(len(g2m.unwrap_goals(dict_envelope)), 4)

        items_envelope = {"items": self.sample_goals}
        self.assertEqual(len(g2m.unwrap_goals(items_envelope)), 4)

        invalid_data = "not a list or dict"
        self.assertEqual(g2m.unwrap_goals(invalid_data), [])

    def test_directory_export_traversal_safety(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_dir = Path(tmpdir)
            g2m.write_directory_export(self.sample_goals, out_dir, group_by="type")

            numeric_file = out_dir / "numeric_goals.md"
            self.assertTrue(numeric_file.exists())
            content = numeric_file.read_text(encoding="utf-8")
            self.assertIn("Read 50 Pages Daily", content)
            self.assertIn("Drink 2 Liters Water", content)

    def test_sanitize_filename(self):
        self.assertEqual(g2m.sanitize_filename("valid_name.md"), "valid_name.md")
        self.assertEqual(g2m.sanitize_filename("../../../etc/passwd"), "etc_passwd")
        self.assertEqual(g2m.sanitize_filename("bad:name/test?"), "bad_name_test")


if __name__ == "__main__":
    unittest.main()
