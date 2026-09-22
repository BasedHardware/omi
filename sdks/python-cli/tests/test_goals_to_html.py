"""Tests for goals to self-contained HTML report converter.

Pins progress-percentage computation, HTML-escaping of untrusted goal
fields (title/unit), active vs. inactive grouping, and atomic-write /
overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_html.py"
spec = importlib.util.spec_from_file_location("goals_to_html", script_path)
g2h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2h)


class TestGoalsToHtml(unittest.TestCase):
    def setUp(self):
        self.sample_goals = [
            {
                "id": "g1",
                "title": "Read 20 books",
                "goal_type": "numeric",
                "current_value": 12,
                "target_value": 20,
                "min_value": 0,
                "max_value": 20,
                "unit": "books",
                "is_active": True,
            },
            {
                "id": "g2",
                "title": "Meditate daily",
                "goal_type": "boolean",
                "current_value": 1,
                "target_value": 1,
                "min_value": 0,
                "max_value": 1,
                "unit": "",
                "is_active": False,
            },
        ]

    def test_progress_pct(self):
        self.assertAlmostEqual(g2h.progress_pct(12, 20, 0, 20), 0.6)
        self.assertAlmostEqual(g2h.progress_pct(1, 1, 0, 1), 1.0)
        # target of 0 falls back to the min/max range instead of dividing by zero.
        self.assertAlmostEqual(g2h.progress_pct(5, 0, 0, 10), 0.5)
        # unparseable current clamps to 0 rather than raising.
        self.assertEqual(g2h.progress_pct("n/a", 10, 0, 10), 0.0)

    def test_conversion_and_grouping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            g2h.convert(json_file, html_file, title="My Goals")
            self.assertTrue(html_file.is_file())

            content = html_file.read_text(encoding="utf-8")
            self.assertIn("<title>My Goals</title>", content)
            self.assertIn("<h2>Active</h2>", content)
            self.assertIn("<h2>Completed / Inactive</h2>", content)
            self.assertIn("Read 20 books", content)
            self.assertIn("width: 60.0%", content)

    def test_html_escaping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            unsafe_goals = [
                {
                    "id": "g1",
                    "title": '<script>alert(1)</script> & "quotes"',
                    "current_value": 1,
                    "target_value": 2,
                    "unit": "<b>x</b>",
                    "is_active": True,
                }
            ]
            json_file.write_text(json.dumps(unsafe_goals), encoding="utf-8")

            g2h.convert(json_file, html_file)
            content = html_file.read_text(encoding="utf-8")

            self.assertNotIn("<script>alert(1)</script>", content)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)
            self.assertNotIn("<b>x</b>", content)

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps({"goals": self.sample_goals}), encoding="utf-8")

            g2h.convert(json_file, html_file)
            self.assertTrue(html_file.is_file())

    def test_empty_goals_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text("[]", encoding="utf-8")

            g2h.convert(json_file, html_file)
            self.assertIn("No goals found", html_file.read_text(encoding="utf-8"))

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(["not", "objects"]), encoding="utf-8")

            with self.assertRaises(ValueError):
                g2h.convert(json_file, html_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")
            html_file.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2h.convert(json_file, html_file)


if __name__ == "__main__":
    unittest.main()
