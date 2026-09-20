import unittest
from pathlib import Path
import sys

# Ensure examples directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_markdown import (
    generate_dashboard,
    goal_to_markdown,
    render_progress_bar,
    slugify,
)


class TestGoalsToMarkdown(unittest.TestCase):
    def test_render_progress_bar(self):
        bar_50 = render_progress_bar(50, 100, width=10)
        self.assertIn("50.0%", bar_50)
        self.assertEqual(bar_50, "[█████░░░░░] 50.0%")

        bar_100 = render_progress_bar(100, 100, width=10)
        self.assertIn("100.0%", bar_100)
        self.assertEqual(bar_100, "[██████████] 100.0%")

        bar_0 = render_progress_bar(0, 100, width=10)
        self.assertEqual(bar_0, "[░░░░░░░░░░] 0.0%")

        bar_invalid = render_progress_bar(10, 0, width=10)
        self.assertEqual(bar_invalid, "[░░░░░░░░░░] N/A")

    def test_slugify(self):
        self.assertEqual(slugify("Run 100km in 2026!"), "run_100km_in_2026")
        self.assertEqual(slugify(""), "goal")

    def test_goal_to_markdown(self):
        goal = {
            "id": "g_123",
            "title": "Gym 4 times a week",
            "goal_type": "scale",
            "current_value": 3,
            "target_value": 4,
            "unit": "sessions",
            "is_active": True,
            "created_at": "2026-09-20T10:00:00Z",
            "updated_at": "2026-09-20T10:00:00Z",
        }
        md = goal_to_markdown(goal)
        self.assertIn('title: "Gym 4 times a week"', md)
        self.assertIn("tags:", md)
        self.assertIn("  - active", md)
        self.assertIn("# Gym 4 times a week", md)
        self.assertIn("3 sessions", md)

    def test_generate_dashboard(self):
        goals = [
            {"id": "1", "title": "Active Goal", "is_active": True, "current_value": 5, "target_value": 10},
            {"id": "2", "title": "Done Goal", "is_active": False, "current_value": 10, "target_value": 10},
        ]
        dashboard = generate_dashboard(goals)
        self.assertIn("# Omi Goals Dashboard", dashboard)
        self.assertIn("**Active Goals:** 1", dashboard)
        self.assertIn("**Completed / Inactive:** 1", dashboard)
        self.assertIn("Active Goal", dashboard)
        self.assertIn("Done Goal", dashboard)


if __name__ == "__main__":
    unittest.main()
