import json
import tempfile
import unittest
from datetime import timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_html import (
    build_report,
    generate_html,
    load,
    parse_offset,
    to_bool,
)


class TestGoalsToHtml(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_offset(self):
        tz = parse_offset("+05:30")
        self.assertEqual(str(tz), "UTC+05:30")
        with self.assertRaises(ValueError):
            parse_offset("+99:00")

    def test_to_bool(self):
        self.assertTrue(to_bool(True))
        self.assertTrue(to_bool("active"))
        self.assertTrue(to_bool("yes"))
        self.assertFalse(to_bool(False))
        self.assertFalse(to_bool("false"))

    def test_html_xss_escaping(self):
        malicious = [
            {
                "id": "g1",
                "title": "<script>alert('xss')</script>",
                "goal_type": "<b>bold</b>",
                "current_value": 5,
                "target_value": 10,
                "unit": "<img src=x onerror=1>",
                "is_active": True,
            }
        ]
        html = generate_html(malicious, timezone.utc)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", html)
        self.assertNotIn("<img src=x", html)

    def test_build_report_exclusive_creation(self):
        goals = [
            {"id": "g1", "title": "Run 5k", "is_active": True, "current_value": 3, "target_value": 5}
        ]
        in_file = self.dir_path / "goals.json"
        in_file.write_text(json.dumps(goals), encoding="utf-8")
        out_file = self.dir_path / "report.html"

        build_report([str(in_file)], out_file, timezone.utc)
        self.assertTrue(out_file.exists())
        self.assertIn("Run 5k", out_file.read_text(encoding="utf-8"))

        # Refuse overwrite
        with self.assertRaises(FileExistsError):
            build_report([str(in_file)], out_file, timezone.utc)


if __name__ == "__main__":
    unittest.main()
