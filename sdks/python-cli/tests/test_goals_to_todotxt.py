"""Hermetic tests for examples/goals_to_todotxt.py (#19113).

Covers: todo.txt mapping (active→(B), inactive→x), +category, metric tags
(cur/target/pct/unit), ZWSP syntax protection, sorting, and overwrite refusal.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import goals_to_todotxt as m  # noqa: E402

GOAL = {
    "id": "g1",
    "title": "Drink water",
    "category": "health",
    "goal_type": "numeric",
    "current_value": 1.0,
    "target_value": 2.0,
    "unit": "liters",
    "is_active": True,
}


class TestGoalLine(unittest.TestCase):
    def test_active_goal_priority_b(self):
        line = m.goal_line(GOAL)
        self.assertTrue(line.startswith("(B) "))
        self.assertIn("omi:g1", line)

    def test_inactive_goal_completed_prefix(self):
        line = m.goal_line({**GOAL, "is_active": False})
        self.assertTrue(line.startswith("x "))
        self.assertNotIn("(B)", line)

    def test_category_to_project_tag(self):
        line = m.goal_line(GOAL)
        self.assertIn("+health", line)

    def test_metric_tags(self):
        line = m.goal_line(GOAL)
        self.assertIn("cur:1", line)
        self.assertIn("target:2", line)
        self.assertIn("unit:liters", line)
        self.assertIn("pct:50%", line)

    def test_qualitative_goal_no_metric_tags(self):
        line = m.goal_line({"id": "g2", "title": "Relationships", "is_active": True})
        self.assertNotIn("cur:", line)
        self.assertNotIn("target:", line)
        self.assertNotIn("pct:", line)


class TestSyntaxProtection(unittest.TestCase):
    def test_title_starting_x_escaped(self):
        line = m.goal_line({"id": "g", "title": "x already done", "is_active": True})
        # ZWSP defuses the fake completion mark — the leading char is invisible
        self.assertIn("​x already done", line)
        self.assertNotIn("\nx already done", "\n" + line)

    def test_title_with_project_prefix_escaped(self):
        line = m.goal_line({"id": "g", "title": "+urgent thing", "is_active": True})
        self.assertIn("​+urgent", line)

    def test_title_with_reserved_key_escaped(self):
        line = m.goal_line({"id": "g", "title": "check due:tomorrow", "is_active": True})
        self.assertIn("due​:tomorrow", line)

    def test_priority_cookie_escaped(self):
        line = m.goal_line({"id": "g", "title": "(A) real title", "is_active": True})
        self.assertTrue(line.startswith("(B) ​(A) real title"))


class TestConvert(unittest.TestCase):
    def test_sorts_active_first(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text(
                json.dumps(
                    {
                        "goals": [
                            {"id": "old", "title": "done", "is_active": False},
                            GOAL,
                        ]
                    }
                )
            )
            dst = str(Path(td) / "out.txt")
            m.convert(str(src), dst)
            lines = Path(dst).read_text().strip().split("\n")
            self.assertTrue(lines[0].startswith("(B)"))
            self.assertTrue(lines[1].startswith("x "))

    def test_envelope_unwrap(self):
        for payload in ({"goals": [GOAL]}, {"items": [GOAL]}, {"data": [GOAL]}, [GOAL]):
            self.assertEqual(len(m.extract_goals(payload)), 1)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text(json.dumps([GOAL]))
            dst = Path(td) / "out.txt"
            dst.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert(str(src), str(dst))
            self.assertEqual(dst.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text(json.dumps([GOAL]))
            with self.assertRaises(ValueError):
                m.convert(str(src), "../escape.txt")

    def test_invalid_json_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text("{bad")
            with self.assertRaises(Exception):
                m.convert(str(src), str(Path(td) / "o.txt"))

    def test_non_dict_row_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "g.json"
            src.write_text(json.dumps([42]))
            with self.assertRaises(ValueError):
                m.convert(str(src), str(Path(td) / "o.txt"))


if __name__ == "__main__":
    unittest.main()
