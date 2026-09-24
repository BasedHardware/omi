"""Tests for Omi action items to JSONL export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_jsonl.py"
spec = importlib.util.spec_from_file_location("action_items_to_jsonl", script_path)
a2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2j)


class TestActionItemsToJsonl(unittest.TestCase):
    def test_utc_stamp_and_boolean_parsing(self):
        self.assertEqual(a2j.utc_stamp("2026-09-24T15:00:00Z"), "2026-09-24 15:00:00")
        self.assertIsNone(a2j.utc_stamp(None))
        self.assertTrue(a2j.parse_boolean(True))
        self.assertTrue(a2j.parse_boolean("yes"))
        self.assertTrue(a2j.parse_boolean(1))
        self.assertFalse(a2j.parse_boolean(False))
        self.assertFalse(a2j.parse_boolean("no"))
        self.assertFalse(a2j.parse_boolean(0))

    def test_extract_action_items_array_and_wrapped(self):
        raw_list = '[{"id": "act-1", "description": "Review PR"}]'
        raw_wrapped = '{"action_items": [{"id": "act-2", "description": "Submit bounty"}]}'

        res1 = a2j.extract_action_items(raw_list)
        res2 = a2j.extract_action_items(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "act-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "act-2")

    def test_extract_action_items_validation_errors(self):
        with self.assertRaises(ValueError):
            a2j.extract_action_items('{"items": "invalid"}')
        with self.assertRaises(ValueError):
            a2j.extract_action_items('[{"invalid": "data"}]')

    def test_normalize_record_fields(self):
        sample = {
            "id": "act-99",
            "title": "Complete pipeline expansion",
            "completed": False,
            "due_at": "2026-09-30T23:59:59Z",
            "conversation_id": "conv-555",
        }
        rec = a2j.normalize_record(sample)
        self.assertEqual(rec["id"], "act-99")
        self.assertEqual(rec["description"], "Complete pipeline expansion")
        self.assertFalse(rec["completed"])
        self.assertEqual(rec["due_at"], "2026-09-30 23:59:59")
        self.assertEqual(rec["conversation_id"], "conv-555")

    def test_convert_paths_deduplication_and_status_filtering(self):
        item1 = {"id": "act-1", "description": "Task 1", "completed": False}
        item2 = {"id": "act-2", "description": "Task 2", "completed": True}
        item1_dup = {"id": "act-1", "description": "Task 1 duplicate", "completed": False}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f1 = tmp / "data1.json"
            f2 = tmp / "data2.json"
            out_file = tmp / "output.jsonl"

            f1.write_text(json.dumps([item1, item2]), encoding="utf-8")
            f2.write_text(json.dumps([item1_dup]), encoding="utf-8")

            # Check deduplication
            count = a2j.convert_paths_to_jsonl([f1, f2], out_file)
            self.assertEqual(count, 2)

            # Check open only
            out_open = tmp / "open.jsonl"
            count_open = a2j.convert_paths_to_jsonl([f1, f2], out_open, status_filter="open")
            self.assertEqual(count_open, 1)
            line = json.loads(out_open.read_text(encoding="utf-8").strip())
            self.assertEqual(line["id"], "act-1")
            self.assertFalse(line["completed"])


if __name__ == "__main__":
    unittest.main()
