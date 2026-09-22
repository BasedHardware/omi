"""Tests for action items to Logseq-format Markdown converter.

Pins TODO/DONE marker selection, DEADLINE emission only for open items,
escaping of untrusted `[[`/`]]`/`#` in the description, and atomic-write /
overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_logseq.py"
spec = importlib.util.spec_from_file_location("action_items_to_logseq", script_path)
a2l = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2l)


class TestActionItemsToLogseq(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "a1",
                "description": "Send #report to [[Team]]",
                "completed": False,
                "due_at": "2026-09-25T10:00:00Z",
            },
            {"id": "a2", "description": "Old task", "completed": True, "due_at": "2020-01-01T00:00:00Z"},
        ]

    def test_escape_block_text(self):
        escaped = a2l.escape_block_text("see [[Page]] and #tag")
        self.assertIn("\\[\\[Page\\]\\]", escaped)
        self.assertIn("\\#tag", escaped)

    def test_conversion_markers_and_deadline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            a2l.convert(json_file, md_file)
            content = md_file.read_text(encoding="utf-8")

            self.assertIn("type:: omi-action-items", content)
            self.assertIn("count:: 2", content)
            self.assertIn("- TODO Send \\#report to \\[\\[Team\\]\\]", content)
            self.assertIn("DEADLINE: <2026-09-25>", content)
            self.assertIn("- DONE Old task", content)
            self.assertIn("omi-id:: a1", content)

    def test_completed_item_has_no_deadline(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            a2l.convert(json_file, md_file)
            content = md_file.read_text(encoding="utf-8")
            done_section = content.split("- DONE Old task")[1]
            self.assertNotIn("DEADLINE", done_section)

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps({"action_items": self.sample_items}), encoding="utf-8")

            a2l.convert(json_file, md_file)
            self.assertIn("count:: 2", md_file.read_text(encoding="utf-8"))

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(["nope"]), encoding="utf-8")

            with self.assertRaises(ValueError):
                a2l.convert(json_file, md_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            md_file = Path(tmpdir) / "output.md"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            md_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                a2l.convert(json_file, md_file)


if __name__ == "__main__":
    unittest.main()
