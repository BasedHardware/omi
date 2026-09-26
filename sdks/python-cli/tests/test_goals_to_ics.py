import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_ics import (
    build_ics,
    convert,
    fold_line,
    ics_text,
    make_vevent,
)


class TestGoalsToIcs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ics_text_escaping(self):
        raw = "Drink 2L, water; and tea\\juice"
        escaped = ics_text(raw)
        self.assertIn("\\,", escaped)
        self.assertIn("\\;", escaped)
        self.assertIn("\\\\", escaped)

    def test_fold_line(self):
        short = "SUMMARY:Short text"
        self.assertEqual(fold_line(short), short)

        long_line = "DESCRIPTION:" + "a" * 100
        folded = fold_line(long_line)
        self.assertIn("\r\n ", folded)
        for part in folded.split("\r\n"):
            self.assertLessEqual(len(part.encode("utf-8")), 75)

    def test_build_ics_structure(self):
        goals = [
            {
                "id": "goal_1",
                "title": "Gym 4x weekly",
                "is_active": True,
                "current_value": 3,
                "target_value": 4,
                "unit": "times",
                "created_at": "2026-09-20T08:00:00Z",
            }
        ]
        ics = build_ics(goals)
        self.assertTrue(ics.startswith("BEGIN:VCALENDAR"))
        self.assertIn("BEGIN:VEVENT", ics)
        self.assertIn("UID:omi-goal-goal_1@omi.me", ics)
        self.assertIn("Gym 4x weekly", ics)
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))

    def test_convert_exclusive_creation(self):
        goals = [{"id": "g1", "title": "Read daily", "is_active": True}]
        in_file = self.dir_path / "goals.json"
        in_file.write_text(json.dumps(goals), encoding="utf-8")
        out_file = self.dir_path / "calendar.ics"

        convert([str(in_file)], out_file)
        self.assertTrue(out_file.exists())
        self.assertIn("Read daily", out_file.read_text(encoding="utf-8"))

        with self.assertRaises(FileExistsError):
            convert([str(in_file)], out_file)


if __name__ == "__main__":
    unittest.main()
