"""Tests for goal list to JSON Lines (.jsonl) exporter."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_jsonl.py"
spec = importlib.util.spec_from_file_location("goals_to_jsonl", script_path)
g2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2j)


class TestGoalsToJsonl(unittest.TestCase):
    def test_convert_to_jsonl(self):
        sample = [
            {
                "id": "g1",
                "title": "Drink water",
                "goal_type": "habit",
                "current_value": 2.0,
                "target_value": 3.0,
                "unit": "L",
                "is_active": True,
            },
            {
                "id": "g2",
                "title": "Sleep 8h",
                "goal_type": "health",
                "current_value": 7.5,
                "target_value": 8.0,
                "unit": "hours",
                "is_active": True,
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "goals.json"
            jsonl_file = Path(tmp_dir) / "goals.jsonl"
            json_file.write_text(json.dumps(sample), encoding="utf-8")

            g2j.convert(str(json_file), str(jsonl_file))
            self.assertTrue(jsonl_file.exists())

            lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 2)
            rec1 = json.loads(lines[0])
            self.assertEqual(rec1["id"], "g1")
            self.assertEqual(rec1["title"], "Drink water")
            self.assertEqual(rec1["current_value"], 2.0)

    def test_append_with_deduplication(self):
        page1 = [
            {"id": "g1", "title": "Old title", "current_value": 1.0, "target_value": 5.0},
            {"id": "g2", "title": "Keep going", "current_value": 2.0, "target_value": 10.0},
        ]
        page2 = [
            {"id": "g1", "title": "Updated title", "current_value": 3.0, "target_value": 5.0},
            {"id": "g3", "title": "Brand new", "current_value": 0.0, "target_value": 1.0},
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "page1.json"
            f2 = Path(tmp_dir) / "page2.json"
            jsonl_file = Path(tmp_dir) / "goals.jsonl"

            f1.write_text(json.dumps(page1), encoding="utf-8")
            f2.write_text(json.dumps(page2), encoding="utf-8")

            g2j.convert(str(f1), str(jsonl_file))
            g2j.convert(str(f2), str(jsonl_file), append=True)

            lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 3)  # g1, g2, g3
            records = {json.loads(line)["id"]: json.loads(line) for line in lines}
            self.assertEqual(records["g1"]["title"], "Updated title")
            self.assertEqual(records["g1"]["current_value"], 3.0)

    def test_refuse_overwrite_without_append(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "goals.json"
            jsonl_file = Path(tmp_dir) / "goals.jsonl"
            json_file.write_text(json.dumps([]), encoding="utf-8")
            jsonl_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2j.convert(str(json_file), str(jsonl_file), append=False)


if __name__ == "__main__":
    unittest.main()
