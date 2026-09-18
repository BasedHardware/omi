"""Tests for memories to markdown exporter (#14458).

Pins frontmatter structure, category and date grouping, visibility and category filtering,
BOM stdin resilience, and directory path traversal containment.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# Load memories_to_markdown example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_markdown.py"
spec = importlib.util.spec_from_file_location("memories_to_markdown", script_path)
m2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2m)


class TestMemoriesToMarkdown(unittest.TestCase):
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
                "content": "Proficient in Python standard library and KiCad S-expressions.",
                "tags": ["python", "kicad"],
                "created_at": "2026-09-16T14:15:00Z",
            },
            {
                "id": "mem_03_learnings",
                "category": "learnings",
                "visibility": "private",
                "content": "KiCad library table nicknames require escaping double quotes.",
                "tags": ["eda", "electronics"],
                "created_at": "2026-09-17T09:00:00Z",
            },
        ]

    def test_frontmatter_shape(self):
        md = m2m.memories_to_markdown(self.sample_memories, title="Personal Knowledge Base")
        self.assertIn("---", md)
        self.assertIn("type: omi-memories", md)
        self.assertIn("total: 3", md)
        self.assertIn("categories_count: 3", md)
        self.assertIn("categories:", md)
        self.assertIn("  - learnings", md)
        self.assertIn("  - skills", md)
        self.assertIn("  - work", md)
        self.assertIn("  - omi", md)
        self.assertIn("  - second-brain", md)
        self.assertIn("# Personal Knowledge Base", md)

    def test_category_grouping_and_emojis(self):
        md = m2m.memories_to_markdown(self.sample_memories, group_by="category")
        self.assertIn("## 💼 Work", md)
        self.assertIn("## 🎯 Skills", md)
        self.assertIn("## 🧠 Learnings", md)
        self.assertIn("Prefers asynchronous communication", md)
        self.assertIn("Proficient in Python standard library", md)
        self.assertIn("KiCad library table nicknames", md)
        self.assertIn("🔒 `private`", md)
        self.assertIn("`#mem_01_work`", md)

    def test_date_grouping(self):
        md = m2m.memories_to_markdown(self.sample_memories, group_by="date")
        self.assertIn("## 📅 2026-09-15", md)
        self.assertIn("## 📅 2026-09-16", md)
        self.assertIn("## 📅 2026-09-17", md)
        self.assertIn("Prefers asynchronous communication", md)

    def test_undated_memory_date_grouping(self):
        undated = [{"id": "mem_none", "content": "Undated fact", "category": "other"}]
        md = m2m.memories_to_markdown(undated, group_by="date")
        self.assertIn("## 📅 Undated", md)
        self.assertIn("Undated fact", md)

    def test_category_filtering(self):
        filtered = m2m.filter_memories(self.sample_memories, category_filter="work,learnings")
        self.assertEqual(len(filtered), 2)
        categories = {m["category"] for m in filtered}
        self.assertEqual(categories, {"work", "learnings"})

    def test_visibility_filtering(self):
        priv = m2m.filter_memories(self.sample_memories, visibility_filter="private")
        self.assertEqual(len(priv), 2)
        pub = m2m.filter_memories(self.sample_memories, visibility_filter="public")
        self.assertEqual(len(pub), 1)
        self.assertEqual(pub[0]["id"], "mem_02_skills")

    def test_traversal_containment_in_write_grouped_directory(self):
        hostile_memories = [
            {
                "id": "mem_hostile",
                "category": "../../evil/traversal",
                "visibility": "public",
                "content": "Hostile traversal attempt in category name",
                "created_at": "2026-09-15T10:00:00Z",
            },
            {
                "id": "mem_normal",
                "category": "work",
                "visibility": "private",
                "content": "Normal work memory",
                "created_at": "2026-09-15T10:00:00Z",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "vault"
            written = m2m.write_grouped_directory(hostile_memories, out_dir, group_by="category")

            self.assertEqual(len(written), 2)
            resolved_out = out_dir.resolve()
            for file_path in written:
                self.assertTrue(file_path.resolve().is_relative_to(resolved_out))
                self.assertTrue(file_path.exists())

            expected_hostile = out_dir / "evil_traversal_memories.md"
            self.assertTrue(expected_hostile.exists())
            self.assertIn("Hostile traversal attempt", expected_hostile.read_text(encoding="utf-8"))

    def test_bom_handling_and_normalization(self):
        payload_with_bom = "\ufeff" + json.dumps({"memories": self.sample_memories})
        decoded = payload_with_bom.encode("utf-8").decode("utf-8-sig")
        data = json.loads(decoded)
        items = data.get("memories")
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["id"], "mem_01_work")


if __name__ == "__main__":
    unittest.main()
