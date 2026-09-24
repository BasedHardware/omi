"""Tests for memories_to_csv recipe.

Covers:
- Header fields and row structure
- UTC timestamp normalization
- CSV formula injection protection
- Bare array vs wrapped JSON structure (memories, items, data)
- Multi-file aggregation
- Boolean coercion for manually_added
- ValueError on invalid or missing id fields
"""

from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load memories_to_csv example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_csv.py"
spec = importlib.util.spec_from_file_location("memories_to_csv", script_path)
m2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2c)

convert_paths_to_csv = m2c.convert_paths_to_csv
spreadsheet_text = m2c.spreadsheet_text
boolean_text = m2c.boolean_text
utc_stamp = m2c.utc_stamp
FIELDS = m2c.FIELDS


SAMPLE_MEMORIES = [
    {
        "id": "mem_1",
        "content": "User prefers dark mode and Python development.",
        "category": "preferences",
        "manually_added": True,
        "created_at": "2026-09-20T09:00:00Z",
        "updated_at": "2026-09-20T09:05:00Z",
    },
    {
        "id": "mem_2",
        "content": "=HYPERLINK(\"http://malicious.site\",\"Click\")",
        "category": "+finance",
        "manually_added": False,
        "created_at": "2026-09-20T14:00:00+02:00",
        "updated_at": "2026-09-20T14:05:00+02:00",
    },
]


class TestMemoriesToCsv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.csv_path = self.dir_path / "memories.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spreadsheet_text_sanitization(self):
        self.assertEqual(spreadsheet_text("clean memory"), "clean memory")
        self.assertEqual(spreadsheet_text("=SUM(1,2)"), "'=SUM(1,2)")
        self.assertEqual(spreadsheet_text("+export"), "'+export")
        self.assertEqual(spreadsheet_text("-flag"), "'-flag")
        self.assertEqual(spreadsheet_text("@include"), "'@include")
        self.assertEqual(spreadsheet_text(None), "")

    def test_boolean_text_formatting(self):
        self.assertEqual(boolean_text(True), "true")
        self.assertEqual(boolean_text(False), "false")
        self.assertEqual(boolean_text(1), "true")
        self.assertEqual(boolean_text(0), "false")
        self.assertEqual(boolean_text("yes"), "true")
        self.assertEqual(boolean_text("no"), "false")

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T11:00:00Z"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp("2026-09-20T13:00:00+02:00"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp(""), "")
        self.assertEqual(utc_stamp(None), "")

    def test_convert_bare_array(self):
        json_file = self.dir_path / "input.json"
        json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")

        count = convert_paths_to_csv([json_file], self.csv_path)
        self.assertEqual(count, 2)
        self.assertTrue(self.csv_path.exists())

        with open(self.csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))

        self.assertEqual(len(reader), 2)
        row1 = reader[0]
        self.assertEqual(row1["id"], "mem_1")
        self.assertEqual(row1["content"], "User prefers dark mode and Python development.")
        self.assertEqual(row1["category"], "preferences")
        self.assertEqual(row1["manually_added"], "true")
        self.assertEqual(row1["created_at"], "2026-09-20 09:00:00")

        # Row 2 with formula escaping and UTC conversion
        row2 = reader[1]
        self.assertEqual(row2["id"], "mem_2")
        self.assertEqual(row2["content"], "'=HYPERLINK(\"http://malicious.site\",\"Click\")")
        self.assertEqual(row2["category"], "'+finance")
        self.assertEqual(row2["manually_added"], "false")
        self.assertEqual(row2["created_at"], "2026-09-20 12:00:00")

    def test_convert_wrapped_dict(self):
        json_file = self.dir_path / "wrapped.json"
        wrapped = {"memories": SAMPLE_MEMORIES}
        json_file.write_text(json.dumps(wrapped), encoding="utf-8")

        count = convert_paths_to_csv([json_file], self.csv_path)
        self.assertEqual(count, 2)

        with open(self.csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
        self.assertEqual(len(reader), 2)

    def test_multi_file_aggregation(self):
        f1 = self.dir_path / "f1.json"
        f2 = self.dir_path / "f2.json"
        f1.write_text(json.dumps([SAMPLE_MEMORIES[0]]), encoding="utf-8")
        f2.write_text(json.dumps([SAMPLE_MEMORIES[1]]), encoding="utf-8")

        count = convert_paths_to_csv([f1, f2], self.csv_path)
        self.assertEqual(count, 2)

        with open(self.csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
        self.assertEqual(len(reader), 2)
        self.assertEqual([r["id"] for r in reader], ["mem_1", "mem_2"])

    def test_missing_id_raises_value_error(self):
        invalid = [{"content": "Memory without id"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_paths_to_csv([json_file], self.csv_path)
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
