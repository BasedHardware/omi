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

    def test_fold_line_multibyte_utf8(self):
        # Multi-byte UTF-8 characters crossing 75-octet boundary
        line = "DESCRIPTION:" + "\u00e9" * 40
        folded = fold_line(line)
        self.assertIn("\r\n ", folded)
        parts = folded.split("\r\n")
        for part in parts:
            self.assertLessEqual(len(part.encode("utf-8")), 75)
        # Verify unfolds losslessly
        unfolded = folded.replace("\r\n ", "")
        self.assertEqual(unfolded, line)

    def test_build_ics_non_ascii(self):
        non_ascii_title = "\u5b8c\u6210\u6bcf\u5929\u9605\u8bfb\u4e00\u5c0f\u65f6\u7684\u76ee\u6807\u5e76\u8bb0\u5f55\u5fc3\u5f97\u4f53\u4f1a"
        goals = [{"id": "g_cjk", "title": non_ascii_title, "is_active": True}]
        ics = build_ics(goals)
        self.assertIn("BEGIN:VCALENDAR", ics)
        self.assertIn(non_ascii_title, ics)
        self.assertIn("STATUS:CONFIRMED", ics)

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
