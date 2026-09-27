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
        """Verify progress bar calculations and boundary handling."""
        self.assertEqual(g2m.format_progress_bar(5.0, 10.0, length=10), "[█████░░░░░] 50%")
        self.assertEqual(g2m.format_progress_bar(10.0, 10.0, length=10), "[██████████] 100%")
        self.assertEqual(g2m.format_progress_bar(0.0, 10.0, length=10), "[░░░░░░░░░░] 0%")
        self.assertEqual(g2m.format_progress_bar(None, 10.0), "")
        self.assertEqual(g2m.format_progress_bar(5.0, None), "")
        self.assertEqual(g2m.format_progress_bar(5.0, 0.0), "")


if __name__ == "__main__":
    unittest.main()
