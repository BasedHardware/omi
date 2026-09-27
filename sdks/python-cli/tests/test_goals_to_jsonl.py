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
                "goal_id": "g1",
                "title": "Drink water",
                "desired_outcome": "Drink 3 liters of water daily",
                "why_it_matters": "Improve hydration and health",
                "success_criteria": ["Track daily volume"],
                "horizon_at": "2026-12-31T23:59:59Z",
                "status": "in_progress",
                "focus_rank": 1,
                "metric": None,
                "source": "manual",
                "goal_type": "scale",
                "current_value": 2.0,
                "target_value": 3.0,
                "min_value": 0.0,
                "max_value": 10.0,
                "unit": "L",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
            },
            {
                "id": "g2",
                "goal_id": "g2",
                "title": "Sleep 8h",
                "desired_outcome": "Consistent sleep schedule",
                "why_it_matters": "Cognitive performance",
                "success_criteria": ["Sleep before 11 PM"],
                "horizon_at": None,
                "status": "active",
                "focus_rank": 2,
                "metric": None,
                "source": "manual",
                "goal_type": "scale",
                "current_value": 7.5,
                "target_value": 8.0,
                "min_value": 0.0,
                "max_value": 12.0,
                "unit": "hours",
                "is_active": True,
                "created_at": "2026-01-01T00:00:00Z",
                "updated_at": "2026-01-02T00:00:00Z",
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
            self.assertEqual(rec1["desired_outcome"], "Drink 3 liters of water daily")
            self.assertEqual(rec1["why_it_matters"], "Improve hydration and health")
            self.assertEqual(rec1["current_value"], 2.0)
            self.assertEqual(rec1["target_value"], 3.0)
            self.assertEqual(rec1["unit"], "L")
            self.assertNotIn("description", rec1)

            rec2 = json.loads(lines[1])
            self.assertEqual(rec2["id"], "g2")
            self.assertEqual(rec2["title"], "Sleep 8h")
            self.assertNotIn("description", rec2)

    def test_append_with_deduplication(self):
        page1 = [
            {"id": "g1", "title": "Old title", "desired_outcome": "Old outcome", "current_value": 1.0, "target_value": 5.0},
            {"id": "g2", "title": "Keep going", "desired_outcome": "Steady progress", "current_value": 2.0, "target_value": 10.0},
        ]
        page2 = [
            {"id": "g1", "title": "Updated title", "desired_outcome": "Updated outcome", "current_value": 3.0, "target_value": 5.0},
            {"id": "g3", "title": "Brand new", "desired_outcome": "New milestone", "current_value": 0.0, "target_value": 1.0},
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
            self.assertEqual(records["g1"]["desired_outcome"], "Updated outcome")
            self.assertEqual(records["g1"]["current_value"], 3.0)
            self.assertEqual(records["g2"]["title"], "Keep going")
            self.assertEqual(records["g3"]["title"], "Brand new")

    def test_refuse_overwrite_without_append(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "goals.json"
            jsonl_file = Path(tmp_dir) / "goals.jsonl"
            json_file.write_text(json.dumps([]), encoding="utf-8")
            original_content = "existing pre-allocated content\n"
            jsonl_file.write_text(original_content, encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2j.convert(str(json_file), str(jsonl_file), append=False)

            # Assert existing file content is strictly preserved
            self.assertEqual(jsonl_file.read_text(encoding="utf-8"), original_content)

    def test_invalid_input_errors(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            non_existent = Path(tmp_dir) / "missing.json"
            jsonl_file = Path(tmp_dir) / "goals.jsonl"
            with self.assertRaises(FileNotFoundError):
                g2j.convert(str(non_existent), str(jsonl_file))

            invalid_json = Path(tmp_dir) / "bad.json"
            invalid_json.write_text("{not json}", encoding="utf-8")
            with self.assertRaises(ValueError):
                g2j.convert(str(invalid_json), str(jsonl_file))

            not_a_list = Path(tmp_dir) / "dict.json"
            not_a_list.write_text(json.dumps({"id": "g1"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                g2j.convert(str(not_a_list), str(jsonl_file))


if __name__ == "__main__":
    unittest.main()
