"""Tests for goals to HTML dashboard exporter.

Verifies:
- Self-contained HTML output structure and embedded CSS
- Executive statistics calculation (total, active, completed, completion rate)
- Goal cards rendering with dynamic progress bars and status badges
- Status filtering (all, active, completed)
- Both bare array and wrapped {"goals": [...]} input formats
- Deduplication of goal IDs
- XSS prevention / HTML escaping for special characters
- Overwrite protection and error handling for malformed input
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# Load goals_to_html script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_html.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "goals_to_html.py"

spec = importlib.util.spec_from_file_location("goals_to_html", script_path)
g2html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2html)


class TestGoalsToHtml(unittest.TestCase):
    def setUp(self):
        self.sample_goals = [
            {
                "id": "goal-001",
                "title": "Read 25 pages daily",
                "goal_type": "numeric",
                "current_value": 15,
                "target_value": 25,
                "min_value": 0,
                "unit": "pages",
                "is_active": True,
                "created_at": "2026-09-20T10:00:00Z"
            },
            {
                "id": "goal-002",
                "title": "Complete AI course certification",
                "goal_type": "boolean",
                "current_value": 1,
                "target_value": 1,
                "is_active": False,
                "created_at": "2026-09-18T08:00:00Z"
            },
            {
                "id": "goal-003",
                "title": "Practice mindful listening in conversations",
                "goal_type": "qualitative",
                "is_active": True,
                "created_at": "2026-09-22T14:30:00Z"
            }
        ]

    def test_basic_html_rendering_and_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            dst = Path(tmpdir) / "dashboard.html"
            src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            count = g2html.convert(str(src), str(dst), title="My 2026 OKRs")
            self.assertEqual(count, 3)
            self.assertTrue(dst.exists())

            html = dst.read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("<title>My 2026 OKRs</title>", html)
            self.assertIn("Total Goals", html)
            self.assertIn("33.3%", html)  # 1 of 3 completed
            self.assertIn("Read 25 pages daily", html)
            self.assertIn("Complete AI course certification", html)
            self.assertIn("Practice mindful listening", html)
            self.assertIn("badge-active", html)
            self.assertIn("badge-done", html)
            self.assertIn("progress-bar-fill", html)
            self.assertIn("60.0%", html)
            self.assertIn('id="search"', html)

    def test_wrapped_json_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "wrapped.json"
            dst = Path(tmpdir) / "dashboard.html"
            src.write_text(json.dumps({"goals": self.sample_goals}), encoding="utf-8")

            count = g2html.convert(str(src), str(dst))
            self.assertEqual(count, 3)

    def test_status_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            # Active only
            dst_active = Path(tmpdir) / "active.html"
            count_active = g2html.convert(str(src), str(dst_active), status_filter="active")
            self.assertEqual(count_active, 2)
            content_active = dst_active.read_text(encoding="utf-8")
            self.assertIn("Read 25 pages daily", content_active)
            self.assertNotIn("Complete AI course certification", content_active)

            # Completed only
            dst_done = Path(tmpdir) / "done.html"
            count_done = g2html.convert(str(src), str(dst_done), status_filter="completed")
            self.assertEqual(count_done, 1)
            content_done = dst_done.read_text(encoding="utf-8")
            self.assertNotIn("Read 25 pages daily", content_done)
            self.assertIn("Complete AI course certification", content_done)

    def test_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "dup.json"
            dst = Path(tmpdir) / "dashboard.html"
            items_with_dup = [self.sample_goals[0], self.sample_goals[0], self.sample_goals[1]]
            src.write_text(json.dumps(items_with_dup), encoding="utf-8")

            count = g2html.convert(str(src), str(dst))
            self.assertEqual(count, 2)

    def test_xss_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "xss.json"
            dst = Path(tmpdir) / "dashboard.html"
            xss_goal = [{
                "id": "xss-1",
                "title": "<script>alert('xss')</script> & <b>bold</b>",
                "goal_type": "<svg/onload=alert(1)>",
                "is_active": True
            }]
            src.write_text(json.dumps(xss_goal), encoding="utf-8")

            count = g2html.convert(str(src), str(dst))
            self.assertEqual(count, 1)

            html = dst.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert('xss')</script>", html)
            self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", html)
            self.assertIn("&lt;svg/onload=alert(1)&gt;", html)

    def test_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            dst = Path(tmpdir) / "dashboard.html"
            src.write_text(json.dumps(self.sample_goals), encoding="utf-8")
            dst.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2html.convert(str(src), str(dst), overwrite=False)

    def test_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.json"
            dst = Path(tmpdir) / "dashboard.html"
            bad.write_text("string not json array", encoding="utf-8")

            with self.assertRaises(ValueError):
                g2html.convert(str(bad), str(dst))


if __name__ == "__main__":
    unittest.main()
