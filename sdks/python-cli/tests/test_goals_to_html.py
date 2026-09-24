"""Tests for goals_to_html recipe.

Covers:
- Progress percentage calculation
- CSS progress bar rendering
- Status categorization into Active, Completed, and Inactive
- HTML escaping and sanitization
- Deduplication of records across export pages
- Error handling on invalid records
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load goals_to_html example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_html.py"
spec = importlib.util.spec_from_file_location("goals_to_html", script_path)
g2h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2h)

convert_paths_to_html = g2h.convert_paths_to_html
generate_html_dashboard = g2h.generate_html_dashboard
calculate_progress_pct = g2h.calculate_progress_pct
utc_stamp = g2h.utc_stamp


SAMPLE_GOALS = [
    {
        "id": "goal_1",
        "title": "Read 20 books & articles",
        "goal_type": "learning",
        "current_value": 15,
        "target_value": 20,
        "unit": "books",
        "is_active": True,
        "created_at": "2026-09-01T10:00:00Z",
    },
    {
        "id": "goal_2",
        "title": "Complete triathlon <script>alert(1)</script>",  # XSS probe
        "goal_type": "fitness",
        "current_value": 100,
        "target_value": 100,
        "unit": "km",
        "is_active": True,
    },
    {
        "id": "goal_3",
        "title": "Archived habit",
        "goal_type": "habit",
        "current_value": 2,
        "target_value": 10,
        "is_active": False,
    },
]


class TestGoalsToHtml(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_calculate_progress_pct(self):
        self.assertEqual(calculate_progress_pct(15, 20), 75.0)
        self.assertEqual(calculate_progress_pct(100, 100), 100.0)
        self.assertEqual(calculate_progress_pct(0, 50), 0.0)
        self.assertEqual(calculate_progress_pct(None, 50), 0.0)
        self.assertEqual(calculate_progress_pct(10, 0), 0.0)

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-01T10:00:00Z"), "2026-09-01 10:00:00")
        self.assertEqual(utc_stamp(""), "")
        self.assertEqual(utc_stamp(None), "")

    def test_html_escaping(self):
        xss_goals = [
            {
                "id": "xss_1",
                "title": "Clean Title <script>alert('title')</script>",
                "current_value": "<img src=x onerror=alert(1)>",
                "target_value": "<svg onload=alert(2)>",
                "unit": "<b>unit</b>",
                "is_active": True,
            }
        ]
        dashboard = generate_html_dashboard(xss_goals + SAMPLE_GOALS)
        self.assertNotIn("<script>", dashboard)
        self.assertNotIn("<img", dashboard)
        self.assertNotIn("<svg", dashboard)
        self.assertNotIn("<b>unit</b>", dashboard)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", dashboard)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", dashboard)
        self.assertIn("&lt;svg onload=alert(2)&gt;", dashboard)
        self.assertIn("&lt;b&gt;unit&lt;/b&gt;", dashboard)
        self.assertIn("Read 20 books &amp; articles", dashboard)

    def test_non_numeric_values_do_not_crash(self):
        non_numeric = [
            {
                "id": "goal_str_curr",
                "title": "String metric goal",
                "current_value": "abc",
                "target_value": 20,
                "is_active": True,
            },
            {
                "id": "goal_str_target",
                "title": "String target goal",
                "current_value": 10,
                "target_value": "xyz",
                "is_active": True,
            },
        ]
        dashboard = generate_html_dashboard(non_numeric)
        self.assertIn("String metric goal", dashboard)
        self.assertIn("abc / 20", dashboard)
        self.assertIn("10 / xyz", dashboard)

    def test_dashboard_metrics_and_sections(self):
        dashboard = generate_html_dashboard(SAMPLE_GOALS)
        self.assertIn("3 total objective(s) tracked", dashboard)
        self.assertIn("Active Objectives</div>", dashboard)
        self.assertIn("Completed Goals (1)", dashboard)
        self.assertIn("Active Goals (1)", dashboard)
        self.assertIn("Inactive / Archived (1)", dashboard)
        self.assertIn("33.3%</div>", dashboard)  # 1 completed out of 3 = 33.3%
        self.assertIn("badge-active", dashboard)
        self.assertIn("badge-done", dashboard)
        self.assertIn("badge-inactive", dashboard)
        self.assertIn("progress-bar-fill", dashboard)

    def test_deduplication(self):
        duplicated = [SAMPLE_GOALS[0], SAMPLE_GOALS[0]]
        dashboard = generate_html_dashboard(duplicated)
        self.assertIn("1 total objective(s) tracked", dashboard)

    def test_convert_to_file(self):
        json_file = self.dir_path / "goals.json"
        json_file.write_text(json.dumps(SAMPLE_GOALS), encoding="utf-8")
        out_html = self.dir_path / "goals.html"

        count = convert_paths_to_html([json_file], out_html)
        self.assertEqual(count, 3)
        self.assertTrue(out_html.exists())
        content = out_html.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("Omi Goals Dashboard", content)

    def test_missing_id_raises_value_error(self):
        invalid = [{"title": "No ID goal"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_paths_to_html([json_file])
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
