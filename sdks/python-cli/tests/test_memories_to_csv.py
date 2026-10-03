"""Tests for memories -> CSV exporter.

Pins header shape, row content, category/visibility filtering, empty-input
behavior, BOM stdin resilience, formula-injection safeguarding, and envelope
unwrapping parity with memories_to_markdown.py.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
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
                "id": "mem_01_work",
                "category": "work",
                "visibility": "private",
                "content": "Prefers asynchronous communication for architecture proposals.",
                "tags": ["workflow", "management"],
                "created_at": "2026-09-15T10:30:00Z",
            },
            {
                "id": "mem_02_skills",
                "category": "skills",
                "visibility": "public",
                "content": "Proficient in Python standard library.",
                "tags": ["python"],
                "created_at": "2026-09-16T14:15:00Z",
            },
        ]

    def _rows(self, csv_text: str):
        reader = csv.DictReader(io.StringIO(csv_text))
        return list(reader)

    def test_header_shape(self):
        csv_text = m2c.memories_to_csv(self.sample_memories)
        reader = csv.reader(io.StringIO(csv_text))
        header = next(reader)
        self.assertEqual(header, ["id", "content", "category", "visibility", "tags", "created_at"])

    def test_row_content(self):
        rows = self._rows(m2c.memories_to_csv(self.sample_memories))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "mem_01_work")
        self.assertEqual(rows[0]["category"], "work")
        self.assertEqual(rows[0]["visibility"], "private")
        self.assertIn("Prefers asynchronous", rows[0]["content"])
        self.assertEqual(rows[0]["tags"], "workflow;management")
        self.assertEqual(rows[0]["created_at"], "2026-09-15T10:30:00Z")

    def test_category_filtering(self):
        filtered = m2c.filter_memories(self.sample_memories, category_filter="work")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["id"], "mem_01_work")

    def test_visibility_filtering(self):
        priv = m2c.filter_memories(self.sample_memories, visibility_filter="private")
        self.assertEqual(len(priv), 1)
        pub = m2c.filter_memories(self.sample_memories, visibility_filter="public")
        self.assertEqual(len(pub), 1)
        self.assertEqual(pub[0]["id"], "mem_02_skills")

    def test_empty_memories_render_header_only(self):
        csv_text = m2c.memories_to_csv([])
        rows = self._rows(csv_text)
        self.assertEqual(len(rows), 0)
        self.assertIn("id,content,category,visibility,tags,created_at", csv_text)

    def test_formula_injection_guard(self):
        hostile = [
            {
                "id": "m1",
                "content": "=HYPERLINK(\"http://evil\",\"x\")",
                "category": "work",
                "visibility": "public",
                "tags": [],
                "created_at": "2026-09-15T10:30:00Z",
            },
            {
                "id": "m2",
                "content": "+SUM(1,2)",
                "category": "work",
                "visibility": "public",
                "tags": [],
                "created_at": "2026-09-15T10:30:00Z",
            },
            {
                "id": "m3",
                "content": "@cmd",
                "category": "work",
                "visibility": "public",
                "tags": [],
                "created_at": "2026-09-15T10:30:00Z",
            },
            {
                "id": "m4",
                "content": "-negative",
                "category": "work",
                "visibility": "public",
                "tags": [],
                "created_at": "2026-09-15T10:30:00Z",
            },
        ]
        rows = self._rows(m2c.memories_to_csv(hostile))
        self.assertEqual(rows[0]["content"], "'=HYPERLINK(\"http://evil\",\"x\")")
        self.assertEqual(rows[1]["content"], "'+SUM(1,2)")
        self.assertEqual(rows[2]["content"], "'@cmd")
        self.assertEqual(rows[3]["content"], "'-negative")

    def test_benign_cell_not_quoted(self):
        rows = self._rows(m2c.memories_to_csv(self.sample_memories))
        self.assertEqual(rows[0]["content"], "Prefers asynchronous communication for architecture proposals.")

    def test_extract_memories_bare_array(self):
        items = [{"id": "m1", "content": "note 1"}, "not-a-dict", {"id": "m2", "content": "note 2"}]
        extracted = m2c.extract_memories(items)
        self.assertEqual(len(extracted), 2)

    def test_extract_memories_wrapped_envelopes(self):
        self.assertEqual(len(m2c.extract_memories({"memories": [{"id": "m1"}]})), 1)
        self.assertEqual(len(m2c.extract_memories({"items": [{"id": "m2"}]})), 1)
        self.assertEqual(len(m2c.extract_memories({"data": [{"id": "m3"}]})), 1)

    def test_extract_memories_empty_envelopes_return_empty(self):
        self.assertEqual(m2c.extract_memories({"memories": []}), [])
        self.assertEqual(m2c.extract_memories({"items": []}), [])
        self.assertEqual(m2c.extract_memories({"data": []}), [])

    def test_extract_memories_single_object(self):
        single = {"id": "m_solo", "content": "Standalone thought", "category": "work"}
        extracted = m2c.extract_memories(single)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["id"], "m_solo")

    def test_extract_memories_unrelated_object_returns_empty(self):
        self.assertEqual(m2c.extract_memories({"status": "error", "code": 500}), [])
        self.assertEqual(m2c.extract_memories("invalid input"), [])

    def test_undated_memory_empty_created_at(self):
        undated = [{"id": "mem_none", "content": "Undated fact", "category": "other"}]
        rows = self._rows(m2c.memories_to_csv(undated))
        self.assertEqual(rows[0]["created_at"], "")


if __name__ == "__main__":
    unittest.main()
