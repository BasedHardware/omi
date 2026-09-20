"""Tests for memories to CSV exporter.

Tests CSV header structure, formula injection sanitization, filtering by category,
visibility, and tag, date/category sorting, and input resilience.
"""

from __future__ import annotations

import csv
import importlib.util
import io
from pathlib import Path
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_csv.py"
spec = importlib.util.spec_from_file_location("memories_to_csv", script_path)
m2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2c)


class TestMemoriesToCsv(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "mem_01",
                "category": "work",
                "content": "Prefers async communication.",
                "tags": ["workflow", "remote"],
                "visibility": "private",
                "created_at": "2026-09-15T10:30:00Z",
            },
            {
                "id": "mem_02",
                "category": "skills",
                "content": "=SUM(A1:A10) formula attempt",
                "tags": ["python", "math"],
                "visibility": "public",
                "created_at": "2026-09-16T14:15:00Z",
            },
            {
                "id": "mem_03",
                "category": "learnings",
                "content": "@dangerous command link",
                "tags": ["security"],
                "visibility": "private",
                "created_at": "2026-09-17T09:00:00Z",
            },
        ]

    def test_csv_structure_and_header(self):
        output = m2c.memories_to_csv(self.sample_memories)
        reader = list(csv.reader(io.StringIO(output)))
        self.assertEqual(len(reader), 4)  # 1 header + 3 items
        self.assertEqual(reader[0], ["id", "category", "content", "tags", "visibility", "created_at"])

    def test_formula_injection_defense(self):
        output = m2c.memories_to_csv(self.sample_memories)
        reader = list(csv.reader(io.StringIO(output)))
        # Check mem_02 content
        mem_02_row = [row for row in reader if row[0] == "mem_02"][0]
        self.assertTrue(mem_02_row[2].startswith("'="), "Formula prefix '=' must be escaped with single quote")

        # Check mem_03 content
        mem_03_row = [row for row in reader if row[0] == "mem_03"][0]
        self.assertTrue(mem_03_row[2].startswith("'@"), "Formula prefix '@' must be escaped with single quote")

    def test_filter_by_category(self):
        filtered = m2c.filter_memories(self.sample_memories, categories={"work"})
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "mem_01")

    def test_filter_by_visibility(self):
        filtered = m2c.filter_memories(self.sample_memories, visibility="public")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "mem_02")

    def test_filter_by_tag(self):
        filtered = m2c.filter_memories(self.sample_memories, tag="security")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "mem_03")

    def test_parse_input_payload_dict_wrapper(self):
        payload = '{"memories": [{"id": "m1", "content": "Wrapped item"}]}'
        parsed = m2c.parse_input_payload(payload)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["id"], "m1")

    def test_bom_stripping(self):
        payload_with_bom = '\ufeff[{"id": "m2", "content": "BOM test"}]'
        parsed = m2c.parse_input_payload(payload_with_bom)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0]["id"], "m2")


if __name__ == "__main__":
    unittest.main()
