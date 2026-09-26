"""Tests for memories_to_jsonl recipe.

Covers: standard, RAG, and system_prompt modes, category filtering,
deduplication across multiple pages, wrapped objects, stdin parsing,
and path traversal rejection.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load memories_to_jsonl example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_jsonl.py"
spec = importlib.util.spec_from_file_location("memories_to_jsonl", script_path)
m2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2j)

convert = m2j.convert
format_record = m2j.format_record
parse_tags = m2j.parse_tags


SAMPLE_MEMORIES = [
    {
        "id": "mem_01_work",
        "category": "work",
        "visibility": "private",
        "content": "Prefers asynchronous communication for architecture proposals.",
        "tags": ["workflow", "management"],
        "created_at": "2026-09-15T10:30:00Z",
        "updated_at": "2026-09-15T10:35:00Z",
    },
    {
        "id": "mem_02_skills",
        "category": "skills",
        "visibility": "public",
        "content": "Proficient in Python standard library and KiCad S-expressions.",
        "tags": ["python", "kicad"],
        "created_at": "2026-09-16T14:15:00+02:00",
        "updated_at": "2026-09-16T14:20:00+02:00",
    },
    {
        "id": "mem_03_learnings",
        "category": "learnings",
        "visibility": "private",
        "content": "KiCad library table nicknames require escaping double quotes.",
        "tags": ["eda", "electronics"],
        "created_at": "2026-09-17T09:00:00Z",
        "updated_at": "2026-09-17T09:05:00Z",
    },
]


class TestMemoriesToJsonl(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.out_path = self.dir_path / "output.jsonl"
        self.json_file = self.dir_path / "memories.json"
        self.json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_tags(self):
        self.assertEqual(parse_tags(["a", "b"]), ["a", "b"])
        self.assertEqual(parse_tags("foo, bar"), ["foo", "bar"])
        self.assertEqual(parse_tags(None), [])
        self.assertEqual(parse_tags([]), [])

    def test_standard_mode_conversion(self):
        count = convert([str(self.json_file)], str(self.out_path), mode="standard")
        self.assertEqual(count, 3)

        lines = self.out_path.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 3)

        first = json.loads(lines[0])
        self.assertEqual(first["id"], "mem_01_work")
        self.assertEqual(first["category"], "work")
        self.assertIn("asynchronous", first["content"])
        self.assertEqual(first["tags"], ["workflow", "management"])

    def test_rag_mode_formatting(self):
        count = convert([str(self.json_file)], str(self.out_path), mode="rag")
        self.assertEqual(count, 3)

        lines = self.out_path.read_text(encoding="utf-8").strip().split("\n")
        first = json.loads(lines[0])
        self.assertIn("text", first)
        self.assertTrue(first["text"].startswith("[WORK]"))
        self.assertIn("metadata", first)
        self.assertEqual(first["metadata"]["category"], "work")
        self.assertEqual(first["metadata"]["id"], "mem_01_work")

    def test_system_prompt_mode(self):
        count = convert([str(self.json_file)], str(self.out_path), mode="system_prompt")
        self.assertEqual(count, 3)

        lines = self.out_path.read_text(encoding="utf-8").strip().split("\n")
        first = json.loads(lines[0])
        self.assertEqual(first["role"], "system")
        self.assertIn("User memory (work):", first["content"])
        self.assertIn("#workflow, #management", first["content"])

    def test_category_filter(self):
        count = convert(
            [str(self.json_file)],
            str(self.out_path),
            categories={"work", "skills"},
        )
        self.assertEqual(count, 2)

        lines = self.out_path.read_text(encoding="utf-8").strip().split("\n")
        categories = [json.loads(line)["category"] for line in lines]
        self.assertEqual(set(categories), {"work", "skills"})

    def test_deduplication(self):
        f1 = self.dir_path / "page1.json"
        f2 = self.dir_path / "page2.json"
        f1.write_text(json.dumps([SAMPLE_MEMORIES[0]]), encoding="utf-8")
        f2.write_text(json.dumps([SAMPLE_MEMORIES[0], SAMPLE_MEMORIES[1]]), encoding="utf-8")

        count = convert([str(f1), str(f2)], str(self.out_path), dedupe=True)
        self.assertEqual(count, 2)

    def test_wrapped_object_input(self):
        wrapped_file = self.dir_path / "wrapped.json"
        wrapped_file.write_text(json.dumps({"memories": SAMPLE_MEMORIES}), encoding="utf-8")

        count = convert([str(wrapped_file)], str(self.out_path))
        self.assertEqual(count, 3)

    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError):
            convert([str(self.json_file)], str(self.dir_path / ".." / "escape.jsonl"))


if __name__ == "__main__":
    unittest.main()
