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

    def test_colliding_category_filenames_preserve_every_group(self):
        """#14927: two categories sanitizing to one slug must not overwrite each other."""
        items = [
            {"id": "first", "category": "work/life", "content": "First category memory"},
            {"id": "second", "category": "work?life", "content": "Second category memory"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            written = m2m.write_grouped_directory(items, output_dir)

            # Two groups -> two distinct files, and both groups survive on disk.
            self.assertEqual(len(written), 2)
            self.assertEqual(len(set(written)), 2)
            self.assertEqual(len(list(output_dir.glob("*.md"))), 2)
            for item in items:
                matching = [path for path in written if item["content"] in path.read_text(encoding="utf-8")]
                self.assertEqual(len(matching), 1, item["id"])

            # The first group keeps the natural filename, the second is suffixed.
            self.assertIn("First category memory", (output_dir / "work_life_memories.md").read_text(encoding="utf-8"))
            self.assertIn(
                "Second category memory", (output_dir / "work_life_2_memories.md").read_text(encoding="utf-8")
            )

    def test_disambiguated_name_does_not_steal_natural_category_name(self):
        items = [
            {"id": "a", "category": "work/life", "content": "Slash category"},
            {"id": "b", "category": "work?life", "content": "Question mark category"},
            {"id": "c", "category": "work_life_2", "content": "Literal suffix category"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            written = m2m.write_grouped_directory(items, output_dir)

            self.assertEqual(len(written), 3)
            self.assertEqual(len({path.name for path in written}), 3)
            self.assertIn(
                "Literal suffix category", (output_dir / "work_life_2_memories.md").read_text(encoding="utf-8")
            )
            for item in items:
                self.assertEqual(
                    sum(item["content"] in path.read_text(encoding="utf-8") for path in written),
                    1,
                    item["id"],
                )

    def test_collision_free_categories_keep_natural_filenames(self):
        """No collisions: filenames must stay exactly as before the fix."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            written = m2m.write_grouped_directory(self.sample_memories, output_dir)
            self.assertEqual(
                {path.name for path in written},
                {"work_memories.md", "skills_memories.md", "learnings_memories.md"},
            )

    def test_colliding_export_is_stable_across_repeated_runs(self):
        items = [
            {"id": "first", "category": "work/life", "content": "First category memory"},
            {"id": "second", "category": "work?life", "content": "Second category memory"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_dir = Path(tmp_dir)
            first_run = m2m.write_grouped_directory(items, output_dir)
            second_run = m2m.write_grouped_directory(list(reversed(items)), output_dir)

            self.assertEqual(first_run, second_run)
            self.assertEqual(len(list(output_dir.glob("*.md"))), 2)

    def test_extract_memories_bare_array(self):
        items = [{"id": "m1", "content": "note 1"}, "not-a-dict", {"id": "m2", "content": "note 2"}]
        extracted = m2m.extract_memories(items)
        self.assertEqual(len(extracted), 2)
        self.assertEqual(extracted[0]["id"], "m1")
        self.assertEqual(extracted[1]["id"], "m2")

    def test_extract_memories_wrapped_envelopes(self):
        self.assertEqual(len(m2m.extract_memories({"memories": [{"id": "m1"}]})), 1)
        self.assertEqual(len(m2m.extract_memories({"items": [{"id": "m2"}]})), 1)
        self.assertEqual(len(m2m.extract_memories({"data": [{"id": "m3"}]})), 1)

    def test_extract_memories_empty_envelopes_return_empty(self):
        self.assertEqual(m2m.extract_memories({"memories": []}), [])
        self.assertEqual(m2m.extract_memories({"items": []}), [])
        self.assertEqual(m2m.extract_memories({"data": []}), [])

    def test_extract_memories_single_object(self):
        single = {"id": "m_solo", "content": "Standalone thought", "category": "work"}
        extracted = m2m.extract_memories(single)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["id"], "m_solo")

    def test_extract_memories_unrelated_object_returns_empty(self):
        self.assertEqual(m2m.extract_memories({"status": "error", "code": 500}), [])
        self.assertEqual(m2m.extract_memories("invalid input"), [])

    def test_empty_memories_render_clean_markdown(self):
        extracted = m2m.extract_memories({"memories": []})
        md = m2m.memories_to_markdown(extracted)
        self.assertIn("total: 0", md)
        self.assertIn("categories_count: 0", md)
        self.assertIn("_No memories found matching criteria._", md)
        self.assertNotIn("_Untitled memory_", md)

    def test_empty_memories_grouped_directory_writes_zero_files(self):
        extracted = m2m.extract_memories({"memories": []})
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "vault"
            written = m2m.write_grouped_directory(extracted, out_dir)
            self.assertEqual(len(written), 0)
            self.assertEqual(list(out_dir.glob("*.md")), [])

    def test_strip_surrogates_keeps_valid_text(self):
        """Only unpaired surrogates are dropped; all other text is preserved."""
        self.assertEqual(m2m.strip_surrogates("plain"), "plain")
        self.assertEqual(m2m.strip_surrogates("中文 ok"), "中文 ok")
        self.assertEqual(m2m.strip_surrogates("emoji \U0001f600 ok"), "emoji \U0001f600 ok")
        self.assertEqual(m2m.strip_surrogates("a\ud800b"), "ab")
        self.assertEqual(m2m.strip_surrogates("\udfff"), "")

    def test_lone_surrogate_in_fields_does_not_abort_export(self):
        """Regression: a lone surrogate must not abort the memory export.

        json.loads accepts an escaped lone surrogate (e.g. "\\ud800") from a
        malformed export. It reached the rendered note verbatim, so
        `path.write_text(..., encoding="utf-8")` raised UnicodeEncodeError and the
        whole export was lost.
        """
        items = [
            {
                "id": "mem_1",
                "content": "User prefers \ud800 dark mode",
                "category": "cat\udfff",
                "created_at": "2026-09-20T10:00:00Z",
            }
        ]
        md = m2m.memories_to_markdown(items)
        # Must not raise: this is the exact call that failed before the fix.
        md.encode("utf-8")
        self.assertIn("User prefers  dark mode", md)

    def test_lone_surrogate_grouped_directory_still_writes(self):
        """The grouped writer must produce files rather than aborting."""
        items = [
            {"id": "mem_1", "content": "a \ud800 b", "category": "work", "created_at": "2026-09-20T10:00:00Z"},
            {"id": "mem_2", "content": "c \udfff d", "category": "work", "created_at": "2026-09-21T10:00:00Z"},
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "vault"
            written = m2m.write_grouped_directory(items, out_dir)
            self.assertEqual(len(written), 1)
            text = written[0].read_text(encoding="utf-8")
            self.assertIn("a  b", text)
            self.assertIn("c  d", text)


if __name__ == "__main__":
    unittest.main()
