"""Tests for goals to JSONL converter.

Pins progress_pct computation and injection, field preservation, wrapped-
object input, non-object rejection, empty-list handling, and atomic-write /
overwrite-refusal behavior.
"""

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
    def setUp(self):
        self.sample_goals = [
            {
                "id": "g1",
                "title": "Read 20 books",
                "current_value": 12,
                "target_value": 20,
                "min_value": 0,
                "max_value": 20,
                "unit": "books",
                "is_active": True,
            },
            {
                "id": "g2",
                "title": "Meditate",
                "current_value": 1,
                "target_value": 1,
                "is_active": False,
            },
        ]

    def test_progress_pct(self):
        self.assertAlmostEqual(g2j.progress_pct(12, 20, 0, 20), 0.6)
        self.assertAlmostEqual(g2j.progress_pct(5, 0, 0, 10), 0.5)
        self.assertIsNone(g2j.progress_pct("n/a", None, None, None))

    def test_conversion_adds_progress_pct(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")

            g2j.convert(json_file, jsonl_file)
            lines = jsonl_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)

            first = json.loads(lines[0])
            self.assertEqual(first["id"], "g1")
            self.assertAlmostEqual(first["progress_pct"], 0.6)
            self.assertEqual(first["title"], "Read 20 books")

            second = json.loads(lines[1])
            self.assertAlmostEqual(second["progress_pct"], 1.0)

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps({"goals": self.sample_goals}), encoding="utf-8")

            g2j.convert(json_file, jsonl_file)
            self.assertEqual(len(jsonl_file.read_text(encoding="utf-8").splitlines()), 2)

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text("[]", encoding="utf-8")

            g2j.convert(json_file, jsonl_file)
            self.assertEqual(jsonl_file.read_text(encoding="utf-8"), "")

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps([1, 2]), encoding="utf-8")

            with self.assertRaises(ValueError):
                g2j.convert(json_file, jsonl_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps(self.sample_goals), encoding="utf-8")
            jsonl_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                g2j.convert(json_file, jsonl_file)


if __name__ == "__main__":
    unittest.main()
