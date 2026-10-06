"""Hermetic unit tests for goals_to_todotxt.py recipe."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

# Add examples directory to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from goals_to_todotxt import (
    ZWSP,
    calculate_progress_pct,
    clean_num,
    convert,
    format_goal_line,
    one_line,
    task_text,
    validate_path,
)


class TestGoalsToTodotxt(unittest.TestCase):
    def test_one_line(self):
        self.assertEqual(one_line(None), "")
        self.assertEqual(one_line("hello\nworld   test"), "hello world test")
        self.assertEqual(one_line(123), "123")

    def test_task_text_zwsp(self):
        # Leading priority or completion marker
        self.assertEqual(task_text("(A) High priority"), f"{ZWSP}(A) High priority")
        self.assertEqual(task_text("x Completed"), f"{ZWSP}x Completed")

        # Plus and at symbols
        self.assertEqual(task_text("+project @context"), f"{ZWSP}+project {ZWSP}@context")

        # Reserved keys
        self.assertEqual(task_text("target:100 cur:50"), f"target{ZWSP}:100 cur{ZWSP}:50")

    def test_clean_num(self):
        self.assertEqual(clean_num(10.0), "10")
        self.assertEqual(clean_num(10.5), "10.5")
        self.assertEqual(clean_num("5"), "5")

    def test_calculate_progress_pct(self):
        # Numeric
        self.assertEqual(
            calculate_progress_pct({"goal_type": "numeric", "current_value": 5, "target_value": 10}),
            50.0,
        )
        # Scale
        self.assertEqual(
            calculate_progress_pct({
                "goal_type": "scale",
                "current_value": 5,
                "min_value": 0,
                "max_value": 10,
            }),
            50.0,
        )
        # Boolean
        self.assertEqual(
            calculate_progress_pct({"goal_type": "boolean", "current_value": 1, "target_value": 1}),
            100.0,
        )
        self.assertEqual(
            calculate_progress_pct({"goal_type": "boolean", "current_value": 0, "target_value": 1}),
            0.0,
        )

    def test_format_active_and_inactive_goal(self):
        active_goal = {
            "id": "goal_1",
            "title": "Read 20 books",
            "goal_type": "numeric",
            "current_value": 10,
            "target_value": 20,
            "unit": "books",
            "is_active": True,
            "created_at": "2026-09-17T12:00:00Z",
        }
        line = format_goal_line(active_goal)
        self.assertTrue(line.startswith("(B) 2026-09-17 Read 20 books +numeric"))
        self.assertIn("cur:10", line)
        self.assertIn("target:20", line)
        self.assertIn("pct:50.0%", line)
        self.assertIn("unit:books", line)
        self.assertIn("id:goal_1", line)

        inactive_goal = {
            "id": "goal_2",
            "title": "Old goal",
            "goal_type": "scale",
            "current_value": 10,
            "target_value": 10,
            "is_active": False,
        }
        inactive_line = format_goal_line(inactive_goal)
        self.assertTrue(inactive_line.startswith("x Old goal +scale"))

    def test_validate_path(self):
        self.assertEqual(validate_path("safe/path.txt"), Path("safe/path.txt"))
        with self.assertRaises(ValueError):
            validate_path("../traversal.txt")

    def test_envelope_unwrapping(self):
        envelope = {
            "goals": [
                {
                    "id": "g_env",
                    "title": "Wrapped goal",
                    "current_value": 1,
                    "target_value": 2,
                    "is_active": True,
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "envelope.json"
            dst = Path(tmpdir) / "envelope.txt"
            src.write_text(json.dumps(envelope), encoding="utf-8")
            count = convert(src, dst)
            self.assertEqual(count, 1)
            content = dst.read_text(encoding="utf-8")
            self.assertIn("(B) Wrapped goal", content)

    def test_convert_goals_to_todotxt_e2e(self):
        sample = [
            {
                "id": "goal_1",
                "title": "Fitness challenge",
                "goal_type": "numeric",
                "current_value": 30,
                "target_value": 60,
                "unit": "minutes",
                "is_active": True,
                "created_at": "2026-09-17T10:00:00Z",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sample.json"
            dst = Path(tmpdir) / "todo.txt"
            src.write_text(json.dumps(sample), encoding="utf-8")

            count = convert(src, dst)
            self.assertEqual(count, 1)

            content = dst.read_text(encoding="utf-8")
            self.assertIn("(B) 2026-09-17 Fitness challenge +numeric cur:30 target:60 pct:50.0% unit:minutes id:goal_1", content)

    def test_overwrite_behavior(self):
        sample = [{"id": "g1", "title": "Test", "is_active": True}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "sample.json"
            dst = Path(tmpdir) / "todo.txt"
            src.write_text(json.dumps(sample), encoding="utf-8")

            convert(src, dst)
            self.assertTrue(dst.exists())

            with self.assertRaises(FileExistsError):
                convert(src, dst, overwrite=False)

            convert(src, dst, overwrite=True)
            self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
