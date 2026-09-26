"""Tests for conversations to Logseq-format Markdown converter.

Pins block content from `structured`, category hashtag selection, escaping
of untrusted `[[`/`]]`/`#` in title/overview, missing-structured fallback,
and atomic-write / overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_logseq.py"
spec = importlib.util.spec_from_file_location("conversations_to_logseq", script_path)
c2l = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2l)


class TestConversationsToLogseq(unittest.TestCase):
    def setUp(self):
        self.sample_conversations = [
            {
                "id": "c1",
                "started_at": "2026-09-18T10:00:00Z",
                "structured": {
                    "title": "Sprint #planning [[Q4]]",
                    "category": "work",
                    "overview": "Discussed roadmap",
                },
            },
            {"id": "c2", "started_at": "2026-09-19T00:00:00Z", "structured": {}},
        ]

    def test_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_conversations), encoding="utf-8")

            c2l.convert(json_file, md_file)
            content = md_file.read_text(encoding="utf-8")

            self.assertIn("type:: omi-conversations", content)
            self.assertIn("count:: 2", content)
            self.assertIn("#work", content)
            self.assertIn("date:: 2026-09-18T10:00:00Z", content)
            self.assertIn("omi-id:: c1", content)
            self.assertIn("  - Discussed roadmap", content)
            # Untrusted title content must be escaped.
            self.assertIn("\\#planning \\[\\[Q4\\]\\]", content)

    def test_missing_structured_falls_back(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_conversations), encoding="utf-8")

            c2l.convert(json_file, md_file)
            content = md_file.read_text(encoding="utf-8")
            self.assertIn("Untitled conversation", content)

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps({"conversations": self.sample_conversations}), encoding="utf-8")

            c2l.convert(json_file, md_file)
            self.assertIn("count:: 2", md_file.read_text(encoding="utf-8"))

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(["nope"]), encoding="utf-8")

            with self.assertRaises(ValueError):
                c2l.convert(json_file, md_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_conversations), encoding="utf-8")
            md_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                c2l.convert(json_file, md_file)


if __name__ == "__main__":
    unittest.main()
