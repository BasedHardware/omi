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
                "title": "Launch Mobile App",
                "description": "Finalize iOS and Android build",
                "progress": 75,
                "target_date": "2026-12-01T00:00:00Z"
            },
            {
                "id": "g2",
                "title": "Read 10 books",
                "completed": True,
                "progress": 100
            }
        ]
        cal = generate_vcalendar(goals)
        self.assertIn("BEGIN:VCALENDAR", cal)
        self.assertIn("BEGIN:VTODO", cal)
        self.assertIn("SUMMARY:Launch Mobile App", cal)
        self.assertIn("PERCENT-COMPLETE:75", cal)
        self.assertIn("STATUS:IN-PROCESS", cal)
        self.assertIn("DUE:20261201T000000Z", cal)

        # Completed goal
        self.assertIn("SUMMARY:Read 10 books", cal)
        self.assertIn("PERCENT-COMPLETE:100", cal)
        self.assertIn("STATUS:COMPLETED", cal)
        self.assertIn("END:VCALENDAR", cal)


if __name__ == "__main__":
    unittest.main()
