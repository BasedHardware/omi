"""Tests for Omi goals to Markdown exporter."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_markdown.py"
spec = importlib.util.spec_from_file_location("goals_to_markdown", script_path)
g2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2m)


class TestGoalsToMarkdown(unittest.TestCase):
    def test_goal_type_taxonomy_and_formatting(self):
        """Verify boolean, scale, and numeric goal types map to correct labels and emojis."""
        goals = [
            {
                "id": "g-num",
                "title": "Run 100km",
                "goal_type": "numeric",
                "desired_outcome": "Complete 100km endurance target",
                "current_value": 45.0,
                "target_value": 100.0,
                "unit": "km",
                "is_active": True,
            },
            {
                "id": "g-scale",
                "title": "Energy Level",
                "goal_type": "scale",
                "desired_outcome": "Maintain high focus daily",
                "current_value": 8.0,
                "target_value": 10.0,
                "is_active": True,
            },
            {
                "id": "g-bool",
                "title": "Morning Stretch",
                "goal_type": "boolean",
                "desired_outcome": "Daily flexibility habit",
                "current_value": 1.0,
                "target_value": 1.0,
                "is_active": True,
            },
        ]

        formatted_num = g2m.format_goal(goals[0])
        self.assertIn("🎯 Run 100km", formatted_num)
        self.assertIn("**Type:** Numeric Target", formatted_num)
        self.assertIn("45 / 100 km", formatted_num)
        self.assertIn("Complete 100km endurance target", formatted_num)

        formatted_scale = g2m.format_goal(goals[1])
        self.assertIn("📊 Energy Level", formatted_scale)
        self.assertIn("**Type:** Scale (1-10)", formatted_scale)
        self.assertIn("8 / 10", formatted_scale)

        formatted_bool = g2m.format_goal(goals[2])
        self.assertIn("✅ Morning Stretch", formatted_bool)
        self.assertIn("**Type:** Yes/No Check", formatted_bool)

    def test_goal_type_meta_aligns_with_api_enum(self):
        """Verify GOAL_TYPE_META strictly contains 'boolean', 'scale', and 'numeric'."""
        expected_keys = {"boolean", "scale", "numeric"}
        self.assertEqual(set(g2m.GOAL_TYPE_META.keys()), expected_keys)
        self.assertEqual(g2m.GOAL_TYPE_META["boolean"]["label"], "Yes/No Check")
        self.assertEqual(g2m.GOAL_TYPE_META["scale"]["label"], "Scale (1-10)")
        self.assertEqual(g2m.GOAL_TYPE_META["numeric"]["label"], "Numeric Target")

    def test_missing_and_non_numeric_values_handled_gracefully(self):
        """Ensure format_goal and _safe_float handle missing or non-numeric values without crashing."""
        # Non-numeric string target
        goal_str_target = {
            "title": "Flexible Target",
            "goal_type": "scale",
            "current_value": "8",
            "target_value": "ten",
        }
        out1 = g2m.format_goal(goal_str_target)
        self.assertIn("Flexible Target", out1)
        self.assertIn("8 / ten", out1)

        # Missing current_value with valid numeric target
        goal_missing_current = {
            "title": "Goal Without Current",
            "goal_type": "numeric",
            "target_value": 50.0,
            "unit": "pages",
        }
        out2 = g2m.format_goal(goal_missing_current)
        self.assertIn("Goal Without Current", out2)
        self.assertIn("0 / 50 pages", out2)

        # Numeric strings for both current and target
        goal_numeric_strings = {
            "title": "String Floats",
            "goal_type": "numeric",
            "current_value": "12.5",
            "target_value": "25.0",
        }
        out3 = g2m.format_goal(goal_numeric_strings)
        self.assertIn("12.5 / 25", out3)
        self.assertIn("[█████░░░░░] 50%", out3)

        # Non-numeric current value with valid target
        goal_invalid_current = {
            "title": "Invalid Current",
            "goal_type": "numeric",
            "current_value": "unknown",
            "target_value": 100,
        }
        out4 = g2m.format_goal(goal_invalid_current)
        self.assertIn("unknown / 100", out4)

        # Empty dictionary fallback
        out_empty = g2m.format_goal({})
        self.assertIn("Untitled Goal", out_empty)
        self.assertIn("🟢 Active", out_empty)

    def test_qualitative_goal_without_target(self):
        """Qualitative goals omit target and progress metrics cleanly."""
        goal = {
            "id": "g-qual",
            "title": "Reflect on gratitude",
            "goal_type": "scale",
            "desired_outcome": "Build positive mindset",
            "current_value": None,
            "target_value": None,
            "is_active": True,
        }
        output = g2m.format_goal(goal)
        self.assertIn("Reflect on gratitude", output)
        self.assertNotIn("**Progress:**", output)
        self.assertIn("Build positive mindset", output)

    def test_build_markdown_document_active_and_completed(self):
        """Verify active and completed goals are partitioned into their respective document sections."""
        goals = [
            {
                "id": "g-act",
                "title": "Active Sprint",
                "goal_type": "numeric",
                "is_active": True,
                "current_value": 2.0,
                "target_value": 5.0,
            },
            {
                "id": "g-inact",
                "title": "Finished Milestone",
                "goal_type": "numeric",
                "is_active": False,
                "current_value": 10.0,
                "target_value": 10.0,
            },
        ]

        doc = g2m.build_markdown_document(goals)
        self.assertIn("## Active Goals", doc)
        self.assertIn("Active Sprint", doc)
        self.assertIn("## Completed / Inactive Goals", doc)
        self.assertIn("Finished Milestone", doc)
        self.assertIn("`2` (`1 active`, `1 completed`)", doc)

    def test_progress_bar_rendering(self):
        """Verify progress bar calculations, boundary handling, and non-numeric safety."""
        self.assertEqual(g2m.format_progress_bar(5.0, 10.0, length=10), "[█████░░░░░] 50%")
        self.assertEqual(g2m.format_progress_bar(10.0, 10.0, length=10), "[██████████] 100%")
        self.assertEqual(g2m.format_progress_bar(15.0, 10.0, length=10), "[██████████] 100%")
        self.assertEqual(g2m.format_progress_bar(0.0, 10.0, length=10), "[░░░░░░░░░░] 0%")
        self.assertEqual(g2m.format_progress_bar(None, 10.0), "")
        self.assertEqual(g2m.format_progress_bar(5.0, None), "")
        self.assertEqual(g2m.format_progress_bar(5.0, 0.0), "")
        self.assertEqual(g2m.format_progress_bar(5.0, -10.0), "")
        self.assertEqual(g2m.format_progress_bar("abc", 10.0), "")
        self.assertEqual(g2m.format_progress_bar(5.0, "xyz"), "")
        self.assertEqual(g2m.format_progress_bar(True, 10.0), "")

    def test_group_by_type_generation(self):
        """Verify grouping goals by goal_type produces separate category files."""
        goals = [
            {"id": "g1", "title": "Bool Goal", "goal_type": "boolean", "is_active": True},
            {"id": "g2", "title": "Scale Goal", "goal_type": "scale", "is_active": True},
            {"id": "g3", "title": "Num Goal", "goal_type": "numeric", "is_active": True},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "goals"
            out_dir.mkdir(parents=True, exist_ok=True)

            grouped = {}
            for g in goals:
                t = str(g.get("goal_type") or "scale").strip().lower()
                grouped.setdefault(t, []).append(g)

            for gtype, items in grouped.items():
                label = g2m.GOAL_TYPE_META.get(gtype, {}).get("label", gtype.capitalize())
                content = g2m.build_markdown_document(items, title=f"Omi Goals - {label}")
                (out_dir / f"Goals_{gtype.capitalize()}.md").write_text(content, encoding="utf-8")

            created = sorted([f.name for f in out_dir.glob("*.md")])
            self.assertEqual(created, ["Goals_Boolean.md", "Goals_Numeric.md", "Goals_Scale.md"])


if __name__ == "__main__":
    unittest.main()
