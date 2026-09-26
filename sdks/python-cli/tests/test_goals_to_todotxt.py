"""Tests for goal list to todo.txt format exporter."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_todotxt.py"
spec = importlib.util.spec_from_file_location("goals_to_todotxt", script_path)
g2t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2t)


class TestGoalsToTodotxt(unittest.TestCase):
    def test_convert_active_and_completed_goals(self):
        sample_goals = [
            {
                "id": "g-1",
                "title": "Reach 10k steps",
                "goal_type": "fitness",
                "current_value": 7500,
                "target_value": 10000,
                "unit": "steps",
                "is_active": True,
            },
            {
                "id": "g-2",
                "title": "Ship v2 release",
                "goal_type": "work",
                "current_value": 1,
                "target_value": 1,
                "is_active": False,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "goals.json"
            txt_file = Path(tmp_dir) / "todo.txt"
            json_file.write_text(json.dumps(sample_goals), encoding="utf-8")

            g2t.convert(str(json_file), str(txt_file))
            self.assertTrue(txt_file.exists())

            lines = txt_file.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 2)

            # First goal is active -> priority (B), +fitness, @omi, tags
            self.assertTrue(lines[0].startswith("(B) Reach 10k steps"))
            self.assertIn("+fitness", lines[0])
            self.assertIn("@omi", lines[0])
            self.assertIn("cur:7500", lines[0])
            self.assertIn("target:10000", lines[0])
            self.assertIn("pct:75.0%", lines[0])
            self.assertIn("unit:steps", lines[0])
            self.assertIn("id:g-1", lines[0])

            # Second goal is inactive -> starts with x
            self.assertTrue(lines[1].startswith("x Ship v2 release"))
            self.assertIn("+work", lines[1])
            self.assertIn("id:g-2", lines[1])

    def test_syntax_collision_escaping(self):
        sample = [
            {
                "id": "g-collision",
                "title": "+ImportantProject @Context target:override x CompletedLookalike",
                "goal_type": "health",
                "is_active": True,
            }
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "goals.json"
            txt_file = Path(tmp_dir) / "todo.txt"
            json_file.write_text(json.dumps(sample), encoding="utf-8")

            g2t.convert(str(json_file), str(txt_file))
            content = txt_file.read_text(encoding="utf-8")
            self.assertIn(g2t.ZWSP + "+ImportantProject", content)
            self.assertIn(g2t.ZWSP + "@Context", content)
            self.assertIn("target" + g2t.ZWSP + ":override", content)

    def test_refuse_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "goals.json"
            txt_file = Path(tmp_dir) / "todo.txt"
            json_file.write_text(json.dumps([]), encoding="utf-8")
            txt_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2t.convert(str(json_file), str(txt_file))


if __name__ == "__main__":
    unittest.main()
