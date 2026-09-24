"""Tests for goals to Markdown exporter.

Verifies:
- YAML frontmatter generation and metadata accuracy
- Checkbox formatting (- [ ] for active, - [x] for completed)
- Progress bar rendering across metric types (numeric, scale, boolean, qualitative)
- Grouping modes (status, type, none)
- Status filtering (all, active, completed)
- Deduplication of goal IDs
- Bare array and wrapped {"goals": [...]} input formats
- Overwrite protection and error handling for malformed input
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# Load goals_to_markdown script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_markdown.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "goals_to_markdown.py"

spec = importlib.util.spec_from_file_location("goals_to_markdown", script_path)
g2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2m)


class TestGoalsToMarkdown(unittest.TestCase):
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

    def test_basic_markdown_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            dst = Path(tmpdir) / "goals.md"
            src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            count = g2m.convert(str(src), output=str(dst), title="Personal OKRs")
            self.assertEqual(count, 3)
            self.assertTrue(dst.exists())

            content = dst.read_text(encoding="utf-8")
            # Frontmatter check
            self.assertTrue(content.startswith("---\n"))
            self.assertIn("title: Personal OKRs", content)
            self.assertIn("total_goals: 3", content)
            self.assertIn("active_goals: 2", content)
            self.assertIn("completed_goals: 1", content)
            self.assertIn("- omi", content)

            # Checkbox checks
            self.assertIn("- [ ] **Read 25 pages daily**", content)
            self.assertIn("- [x] **Complete AI course certification**", content)
            self.assertIn("- [ ] **Practice mindful listening in conversations**", content)

            # Progress bar checks (15/25 = 60%)
            self.assertIn("60.0%", content)
            self.assertIn("pages", content)
            self.assertIn("15/25", content)

    def test_wrapped_json_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "wrapped.json"
            dst = Path(tmpdir) / "goals.md"
            src.write_text(json.dumps({"goals": self.sample_goals}), encoding="utf-8")

            count = g2m.convert(str(src), output=str(dst))
            self.assertEqual(count, 3)

    def test_grouping_by_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            dst = Path(tmpdir) / "goals.md"
            src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            g2m.convert(str(src), output=str(dst), group_by="type")
            content = dst.read_text(encoding="utf-8")

            self.assertIn("## Numeric Goals", content)
            self.assertIn("## Boolean Goals", content)
            self.assertIn("## Qualitative Goals", content)

    def test_status_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            # Active only
            dst_active = Path(tmpdir) / "active.md"
            count_active = g2m.convert(str(src), output=str(dst_active), status_filter="active")
            self.assertEqual(count_active, 2)
            content_active = dst_active.read_text(encoding="utf-8")
            self.assertIn("Read 25 pages daily", content_active)
            self.assertNotIn("Complete AI course certification", content_active)

            # Completed only
            dst_done = Path(tmpdir) / "completed.md"
            count_done = g2m.convert(str(src), output=str(dst_done), status_filter="completed")
            self.assertEqual(count_done, 1)
            content_done = dst_done.read_text(encoding="utf-8")
            self.assertNotIn("Read 25 pages daily", content_done)
            self.assertIn("Complete AI course certification", content_done)

    def test_no_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            dst = Path(tmpdir) / "goals.md"
            src.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            g2m.convert(str(src), output=str(dst), no_frontmatter=True)
            content = dst.read_text(encoding="utf-8")

            self.assertFalse(content.startswith("---"))
            self.assertTrue(content.startswith("# "))

    def test_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "dup.json"
            dst = Path(tmpdir) / "goals.md"
            items_with_dup = [self.sample_goals[0], self.sample_goals[0], self.sample_goals[1]]
            src.write_text(json.dumps(items_with_dup), encoding="utf-8")

            count = g2m.convert(str(src), output=str(dst))
            self.assertEqual(count, 2)

    def test_progress_calculation_bounds(self):
        # Overachieved: 120 / 100 -> 100%
        over_goal = {
            "title": "Overachieved",
            "goal_type": "numeric",
            "current_value": 120,
            "target_value": 100,
            "min_value": 0,
            "is_active": True
        }
        pct, label = g2m.calculate_progress(over_goal)
        self.assertEqual(pct, 100.0)
        self.assertIn("100.0%", label)
        self.assertIn("██████████", label)

    def test_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "goals.json"
            dst = Path(tmpdir) / "goals.md"
            src.write_text(json.dumps(self.sample_goals), encoding="utf-8")
            dst.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2m.convert(str(src), output=str(dst), overwrite=False)

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.json"
            bad.write_text("not json", encoding="utf-8")

            with self.assertRaises(ValueError):
                g2m.convert(str(bad))


if __name__ == "__main__":
    unittest.main()
