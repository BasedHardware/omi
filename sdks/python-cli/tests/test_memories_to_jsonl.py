"""Tests for Omi memories to JSONL export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_jsonl.py"
spec = importlib.util.spec_from_file_location("memories_to_jsonl", script_path)
m2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2j)


class TestMemoriesToJsonl(unittest.TestCase):
    def test_utc_stamp_normalization(self):
        self.assertEqual(m2j.utc_stamp("2026-09-24T12:00:00Z"), "2026-09-24 12:00:00")
        self.assertIsNone(m2j.utc_stamp(None))
        self.assertEqual(m2j.utc_stamp("raw-invalid"), "raw-invalid")

    def test_extract_memories_array_and_wrapped(self):
        raw_list = '[{"id": "mem-1", "content": "Prefers tea over coffee"}]'
        raw_wrapped = '{"memories": [{"id": "mem-2", "content": "Speaks Spanish"}]}'

        res1 = m2j.extract_memories(raw_list)
        res2 = m2j.extract_memories(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "mem-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "mem-2")

    def test_extract_memories_validation_errors(self):
        with self.assertRaises(ValueError):
            m2j.extract_memories('{"data": "not-an-array"}')
        with self.assertRaises(ValueError):
            m2j.extract_memories('[{"no_id": "test"}]')

    def test_normalize_record_fields_and_tags(self):
        sample = {
            "id": "m-50",
            "content": "Working on autonomous bounty agents",
            "category": "WORK",
            "tags": ["ai", "agents", "python"],
            "visibility": "Private",
            "created_at": "2026-09-24T14:15:00Z",
        }
        rec = m2j.normalize_record(sample)
        self.assertEqual(rec["id"], "m-50")
        self.assertEqual(rec["content"], "Working on autonomous bounty agents")
        self.assertEqual(rec["category"], "work")
        self.assertEqual(rec["tags"], ["ai", "agents", "python"])
        self.assertEqual(rec["visibility"], "private")
        self.assertEqual(rec["created_at"], "2026-09-24 14:15:00")

    def test_convert_paths_deduplication_and_filtering(self):
        item1 = {"id": "m-1", "content": "Item 1", "category": "work"}
        item2 = {"id": "m-2", "content": "Item 2", "category": "personal"}
        item1_duplicate = {"id": "m-1", "content": "Item 1 duplicate", "category": "work"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f1 = tmp / "data1.json"
            f2 = tmp / "data2.json"
            out_file = tmp / "output.jsonl"

            f1.write_text(json.dumps([item1, item2]), encoding="utf-8")
            f2.write_text(json.dumps([item1_duplicate]), encoding="utf-8")

            # Test deduplication
            count = m2j.convert_paths_to_jsonl([f1, f2], out_file)
            self.assertEqual(count, 2)

            lines = out_file.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 2)

            # Test filtering by category
            out_filtered = tmp / "filtered.jsonl"
            count_filt = m2j.convert_paths_to_jsonl([f1, f2], out_filtered, category_filter="work")
            self.assertEqual(count_filt, 1)
            line_data = json.loads(out_filtered.read_text(encoding="utf-8").strip())
            self.assertEqual(line_data["id"], "m-1")
            self.assertEqual(line_data["category"], "work")


if __name__ == "__main__":
    unittest.main()
