import unittest
import sys
from pathlib import Path

# Add examples dir to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_vtodo import generate_vcalendar, escape_ics, extract_goals


class TestGoalsToVTodo(unittest.TestCase):
    def test_escape_ics(self):
        self.assertEqual(escape_ics("Goal, finish; now\nstep 2"), "Goal\\, finish\\; now\\nstep 2")

    def test_generate_vtodo(self):
        goals = [
            {
                "id": "g1",
                "title": "Run 20 kilometers",
                "goal_type": "numeric",
                "current_value": 15,
                "target_value": 20,
                "unit": "km",
                "status": "focused",
                "created_at": "2026-09-01T08:00:00Z"
            },
            {
                "id": "g2",
                "title": "Read 10 books",
                "goal_type": "numeric",
                "current_value": 10,
                "target_value": 10,
                "unit": "books",
                "status": "achieved",
                "created_at": "2026-08-01T08:00:00Z",
                "updated_at": "2026-09-20T12:00:00Z"
            },
            {
                "id": "g3",
                "title": "Setup daily backup",
                "goal_type": "boolean",
                "current_value": 1,
                "target_value": 1,
                "status": "achieved"
            },
            {
                "id": "g4",
                "title": "Old marathon goal",
                "goal_type": "numeric",
                "current_value": 2,
                "target_value": 42,
                "status": "abandoned"
            }
        ]
        cal = generate_vcalendar(goals)
        self.assertIn("BEGIN:VCALENDAR", cal)
        self.assertIn("BEGIN:VTODO", cal)

        # In-process goal with derived progress
        self.assertIn("SUMMARY:Run 20 kilometers", cal)
        self.assertIn("PERCENT-COMPLETE:75", cal)
        self.assertIn("STATUS:IN-PROCESS", cal)
        self.assertIn("DESCRIPTION:Type: numeric | Progress: 15 / 20 km | Omi status: focused", cal)
        self.assertIn("CREATED:20260901T080000Z", cal)

        # Achieved goal
        self.assertIn("SUMMARY:Read 10 books", cal)
        self.assertIn("PERCENT-COMPLETE:100", cal)
        self.assertIn("STATUS:COMPLETED", cal)
        self.assertIn("COMPLETED:20260920T120000Z", cal)

        # Boolean goal
        self.assertIn("SUMMARY:Setup daily backup", cal)
        self.assertIn("PERCENT-COMPLETE:100", cal)
        self.assertIn("STATUS:COMPLETED", cal)

        # Abandoned goal
        self.assertIn("SUMMARY:Old marathon goal", cal)
        self.assertIn("STATUS:CANCELLED", cal)
        self.assertIn("END:VCALENDAR", cal)

    def test_extract_goals(self):
        raw = '{"goals": [{"id": "g10", "title": "Hydrate daily"}]}'
        items = extract_goals(raw)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "g10")

    def test_extract_goals_validation(self):
        with self.assertRaises(ValueError):
            extract_goals("")
        with self.assertRaises(ValueError):
            extract_goals("{invalid")


if __name__ == "__main__":
    unittest.main()
