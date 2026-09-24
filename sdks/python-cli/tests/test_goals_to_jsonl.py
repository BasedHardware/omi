"""Tests for Omi goals to JSONL export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "goals_to_jsonl.py"
spec = importlib.util.spec_from_file_location("goals_to_jsonl", script_path)
g2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2j)


class TestGoalsToJsonl(unittest.TestCase):
    def test_utc_stamp_and_number_parsing(self):
        self.assertEqual(g2j.utc_stamp("2026-09-24T16:00:00Z"), "2026-09-24 16:00:00")
        self.assertIsNone(g2j.utc_stamp(None))
        self.assertEqual(g2j.parse_float("15.5"), 15.5)
        self.assertEqual(g2j.parse_float(None, 2.0), 2.0)
        self.assertTrue(g2j.parse_boolean("yes"))
        self.assertFalse(g2j.parse_boolean("no"))

    def test_extract_goals_array_and_wrapped(self):
        raw_list = '[{"id": "goal-1", "title": "Read 10 books"}]'
        raw_wrapped = '{"goals": [{"id": "goal-2", "title": "Run 50km"}]}'

        res1 = g2j.extract_goals(raw_list)
        res2 = g2j.extract_goals(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "goal-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "goal-2")

    def test_extract_goals_validation_errors(self):
        with self.assertRaises(ValueError):
            g2j.extract_goals('{"items": 123}')
        with self.assertRaises(ValueError):
            g2j.extract_goals('[{"no_id": "test"}]')

    def test_normalize_record_fields_and_progress_calculation(self):
        sample = {
            "id": "g-10",
            "title": "Drink 2L Water Daily",
            "target_value": 2.0,
            "current_value": 1.5,
            "unit": "liters",
            "target_date": "2026-12-31T00:00:00Z",
        }
        rec = g2j.normalize_record(sample)
        self.assertEqual(rec["id"], "g-10")
        self.assertEqual(rec["title"], "Drink 2L Water Daily")
        self.assertEqual(rec["target_value"], 2.0)
        self.assertEqual(rec["current_value"], 1.5)
        self.assertEqual(rec["unit"], "liters")
        self.assertEqual(rec["progress_pct"], 75.0)
        self.assertFalse(rec["completed"])

    def test_convert_paths_deduplication_and_filtering(self):
        item1 = {"id": "g-1", "title": "Run marathon", "target_value": 42.0, "current_value": 10.0}
        item2 = {"id": "g-2", "title": "Save $1000", "target_value": 1000.0, "current_value": 1000.0}
        item1_dup = {"id": "g-1", "title": "Run marathon duplicate", "target_value": 42.0, "current_value": 10.0}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f1 = tmp / "data1.json"
            f2 = tmp / "data2.json"
            out_file = tmp / "output.jsonl"

            f1.write_text(json.dumps([item1, item2]), encoding="utf-8")
            f2.write_text(json.dumps([item1_dup]), encoding="utf-8")

            # Check deduplication
            count = g2j.convert_paths_to_jsonl([f1, f2], out_file)
            self.assertEqual(count, 2)

            # Check active only
            out_active = tmp / "active.jsonl"
            count_act = g2j.convert_paths_to_jsonl([f1, f2], out_active, status_filter="active")
            self.assertEqual(count_act, 1)
            line = json.loads(out_active.read_text(encoding="utf-8").strip())
            self.assertEqual(line["id"], "g-1")
            self.assertFalse(line["completed"])


if __name__ == "__main__":
    unittest.main()
