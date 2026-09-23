"""Tests for memories to Logseq-format Markdown converter.

Pins hashtag slugification, escaping of untrusted `[[`/`]]`/`#` in memory
content (so only script-generated hashtags become real Logseq tags), block
properties, and atomic-write / overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_logseq.py"
spec = importlib.util.spec_from_file_location("memories_to_logseq", script_path)
m2l = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2l)


class TestMemoriesToLogseq(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "m1",
                "category": "personal growth",
                "content": "Wants to learn [[hacking]] & #cooking",
                "tags": ["deep work", "focus"],
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "m2",
                "category": "work",
                "content": "Simple note",
                "tags": [],
                "created_at": "2026-02-01T00:00:00Z",
            },
        ]

    def test_logseq_tag_slugification(self):
        self.assertEqual(m2l.logseq_tag("personal growth"), "#personal-growth")
        self.assertEqual(m2l.logseq_tag("work"), "#work")
        self.assertIsNone(m2l.logseq_tag("   "))

    def test_escape_block_text_neutralizes_links_and_tags(self):
        escaped = m2l.escape_block_text("see [[Page]] and #tag")
        self.assertNotIn("[[Page]]", escaped)
        self.assertIn("\\[\\[Page\\]\\]", escaped)
        self.assertIn("\\#tag", escaped)
        self.assertNotIn("#tag", escaped.replace("\\#tag", ""))

    def test_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2l.convert(json_file, md_file)
            content = md_file.read_text(encoding="utf-8")

            self.assertIn("type:: omi-memories", content)
            self.assertIn("count:: 2", content)
            self.assertIn("#personal-growth", content)
            self.assertIn("#deep-work", content)
            self.assertIn("#focus", content)
            self.assertIn("omi-id:: m1", content)
            # The literal tag/link inside the memory content must be escaped.
            self.assertIn("\\#cooking", content)
            self.assertIn("\\[\\[hacking\\]\\]", content)

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps({"memories": self.sample_memories}), encoding="utf-8")

            m2l.convert(json_file, md_file)
            self.assertIn("count:: 2", md_file.read_text(encoding="utf-8"))

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(["nope"]), encoding="utf-8")

            with self.assertRaises(ValueError):
                m2l.convert(json_file, md_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")
            md_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                m2l.convert(json_file, md_file)


if __name__ == "__main__":
    unittest.main()
