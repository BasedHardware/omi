"""Unit tests for memories -> Org-mode exporter.

Pins envelope unwrapping, UTF-8 BOM handling, properties drawer,
category and date grouping, tag formatting, Org syntax escaping,
filtering, and single-file vs directory export modes.
"""

from __future__ import annotations

from datetime import timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_org.py"
spec = importlib.util.spec_from_file_location("memories_to_org", script_path)
m2org = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2org)

JST = timezone(timedelta(hours=9))
UTC = timezone.utc


class TestMemoriesToOrg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_extract_memories_envelopes(self):
        sample = {"id": "m1", "content": "Enjoys green tea", "category": "habits"}

        # Bare list
        self.assertEqual(len(m2org.extract_memories([sample])), 1)

        # Envelopes
        self.assertEqual(len(m2org.extract_memories({"memories": [sample]})), 1)
        self.assertEqual(len(m2org.extract_memories({"items": [sample]})), 1)
        self.assertEqual(len(m2org.extract_memories({"data": [sample]})), 1)

        # Single dict
        self.assertEqual(len(m2org.extract_memories(sample)), 1)

        # Empty envelopes (Must return 0 without creating phantom records)
        self.assertEqual(len(m2org.extract_memories({"memories": []})), 0)
        self.assertEqual(len(m2org.extract_memories({"items": []})), 0)
        self.assertEqual(len(m2org.extract_memories({"data": []})), 0)
        self.assertEqual(len(m2org.extract_memories({})), 0)
        self.assertEqual(len(m2org.extract_memories([])), 0)

    def test_utf8_bom_handling(self):
        sample = [{"id": "m1", "content": "BOM Test Memory", "category": "work"}]
        bom_payload = "\ufeff" + json.dumps(sample)
        source = self.tmp / "bom.json"
        source.write_bytes(bom_payload.encode("utf-8"))

        dest = self.tmp / "bom.org"
        count = m2org.convert(source, dest, UTC)
        self.assertEqual(count, 1)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("BOM Test Memory", content)
        self.assertIn(":CATEGORY: work", content)

    def test_properties_drawer_and_metadata(self):
        sample = [{
            "id": "mem-uuid-9999",
            "content": "Specializes in distributed systems and consensus protocols.",
            "category": "skills",
            "visibility": "public",
            "tags": ["distributed-systems", "algorithms", "raft"],
            "created_at": "2026-09-28T09:30:00Z",
            "updated_at": "2026-09-28T10:00:00Z",
        }]
        source = self.tmp / "skills.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "skills.org"
        m2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* 🎯 Skills :skills:", content)
        self.assertIn("** Specializes in distributed systems", content)
        self.assertIn(":PROPERTIES:", content)
        self.assertIn(":OMI_ID: mem-uuid-9999", content)
        self.assertIn(":CATEGORY: skills", content)
        self.assertIn(":DATE: [2026-09-28 Mon 09:30]", content)
        self.assertIn(":CREATED: [2026-09-28 Mon 09:30]", content)
        self.assertIn(":UPDATED: [2026-09-28 Mon 10:00]", content)
        self.assertIn(":VISIBILITY: public", content)
        self.assertIn(":TAGS: distributed_systems algorithms raft", content)
        self.assertIn(":END:", content)

    def test_syntax_escaping_zwsp(self):
        # Priority cookies [#A], stray timestamps, stray tags
        sample = [
            {"id": "m1", "content": "[#A] High priority insight", "category": "work"},
            {"id": "m2", "content": "Meeting scheduled on [2026-09-28 Mon]", "category": "work"},
            {"id": "m3", "content": "Note ending with a colon tag :urgent:", "category": "work"},
        ]
        source = self.tmp / "escape.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "escape.org"
        m2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        # Ensure ZWSP is injected before [#A]
        self.assertIn(f"\u200b[#A]", content)
        # Ensure ZWSP is injected inside timestamp
        self.assertIn(f"[\u200b2026-09-28", content)
        # Ensure ZWSP is injected after trailing tag
        self.assertIn(f":urgent:\u200b", content)

    def test_group_by_category(self):
        sample = [
            {"id": "m1", "content": "Refactored payment gateway", "category": "work"},
            {"id": "m2", "content": "Run 5k every morning", "category": "habits"},
        ]
        source = self.tmp / "cats.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "cats.org"
        m2org.convert(source, dest, UTC, group_by="category")

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* 💼 Work :work:", content)
        self.assertIn("** Refactored payment gateway", content)
        self.assertIn("* ⚡ Habits :habits:", content)
        self.assertIn("** Run 5k every morning", content)

    def test_group_by_date(self):
        sample = [
            {"id": "m1", "content": "Today note", "created_at": "2026-09-28T08:00:00Z"},
            {"id": "m2", "content": "Yesterday note", "created_at": "2026-09-27T08:00:00Z"},
        ]
        source = self.tmp / "dates.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "dates.org"
        m2org.convert(source, dest, UTC, group_by="date")

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* 📅 2026-09-28", content)
        self.assertIn("** Today note", content)
        self.assertIn("* 📅 2026-09-27", content)
        self.assertIn("** Yesterday note", content)

    def test_group_by_none(self):
        sample = [
            {"id": "m1", "content": "Flat note 1", "category": "other"},
            {"id": "m2", "content": "Flat note 2", "category": "work"},
        ]
        source = self.tmp / "flat.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "flat.org"
        m2org.convert(source, dest, UTC, group_by="none")

        content = dest.read_text(encoding="utf-8")
        # In flat mode, memories are top-level headings
        self.assertIn("* Flat note 1", content)
        self.assertIn("* Flat note 2", content)
        self.assertNotIn("** Flat note 1", content)

    def test_filter_category_and_visibility(self):
        sample = [
            {"id": "m1", "content": "Work memory", "category": "work", "visibility": "public"},
            {"id": "m2", "content": "Private skill", "category": "skills", "visibility": "private"},
            {"id": "m3", "content": "Public skill", "category": "skills", "visibility": "public"},
            {"id": "m4", "content": "Other note", "category": "other", "visibility": "public"},
        ]
        source = self.tmp / "filter.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        # Filter category
        dest_cat = self.tmp / "filter_cat.org"
        m2org.convert(source, dest_cat, UTC, category_filter="work,skills")
        content_cat = dest_cat.read_text(encoding="utf-8")
        self.assertIn("Work memory", content_cat)
        self.assertIn("Private skill", content_cat)
        self.assertIn("Public skill", content_cat)
        self.assertNotIn("Other note", content_cat)

        # Filter visibility
        dest_vis = self.tmp / "filter_vis.org"
        m2org.convert(source, dest_vis, UTC, visibility_filter="private")
        content_vis = dest_vis.read_text(encoding="utf-8")
        self.assertIn("Private skill", content_vis)
        self.assertNotIn("Work memory", content_vis)
        self.assertNotIn("Public skill", content_vis)

    def test_multiline_and_long_content(self):
        long_content = "This is a very detailed memory that spans across multiple sentences.\nLine 2 contains implementation details.\nLine 3 contains notes."
        sample = [{"id": "m1", "content": long_content, "category": "learnings"}]
        source = self.tmp / "multi.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "multi.org"
        m2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("** This is a very detailed memory", content)
        self.assertIn(":END:\nThis is a very detailed memory", content)
        self.assertIn("Line 2 contains implementation details.", content)

    def test_directory_export_mode(self):
        sample = [
            {"id": "m1", "content": "Work project update", "category": "work"},
            {"id": "m2", "content": "Reading list item", "category": "learnings"},
            {"id": "m3", "content": "Coffee recipe", "category": "lifestyle"},
        ]
        source = self.tmp / "dir_sample.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        out_dir = self.tmp / "org_dir"
        count = m2org.convert(source, self.tmp / "dummy.org", UTC, output_dir=out_dir)
        self.assertEqual(count, 3)

        files = list(out_dir.glob("*.org"))
        filenames = [f.name for f in files]
        self.assertIn("work_memories.org", filenames)
        self.assertIn("learnings_memories.org", filenames)
        self.assertIn("lifestyle_memories.org", filenames)

    def test_overwrite_protection(self):
        sample = [{"id": "m1", "content": "Test item"}]
        source = self.tmp / "ow.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "existing.org"
        dest.write_text("Existing data", encoding="utf-8")

        # Without force -> raises FileExistsError
        with self.assertRaises(FileExistsError):
            m2org.convert(source, dest, UTC, overwrite=False)

        # With force -> succeeds
        m2org.convert(source, dest, UTC, overwrite=True)
        self.assertIn("Test item", dest.read_text(encoding="utf-8"))

    def test_stdin_input_support(self):
        sample = [{"id": "m1", "content": "Stdin memory", "category": "core"}]
        payload_str = json.dumps(sample)
        dest = self.tmp / "stdin.org"

        with patch("sys.stdin", io.StringIO(payload_str)):
            count = m2org.convert("-", dest, UTC)
            self.assertEqual(count, 1)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("Stdin memory", content)
        self.assertIn(":CATEGORY: core", content)


if __name__ == "__main__":
    unittest.main()
