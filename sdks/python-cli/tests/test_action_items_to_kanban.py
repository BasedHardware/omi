"""Tests for Omi action items to Markdown Kanban export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_kanban.py"
spec = importlib.util.spec_from_file_location("action_items_to_kanban", script_path)
a2k = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2k)


class TestActionItemsToKanban(unittest.TestCase):
    def test_format_due_date(self):
        self.assertEqual(a2k.format_due_date("2026-09-30T15:00:00Z"), "2026-09-30")
        self.assertIsNone(a2k.format_due_date(None))

    def test_extract_action_items(self):
        raw_list = '[{"id": "act-1", "description": "Review PR"}]'
        raw_wrapped = '{"action_items": [{"id": "act-2", "description": "Fix bug"}]}'

        res1 = a2k.extract_action_items(raw_list)
        res2 = a2k.extract_action_items(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "act-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "act-2")

    def test_render_kanban_columns(self):
        items = [
            {"id": "act-1", "description": "Backlog item", "completed": False},
            {"id": "act-2", "description": "Scheduled item", "completed": False, "due_at": "2026-10-01T09:00:00Z"},
            {"id": "act-3", "description": "Finished item", "completed": True},
        ]
        board = a2k.render_kanban(items, title="Sprint Board")

        self.assertIn("kanban-plugin: basic", board)
        self.assertIn("# Sprint Board", board)
        self.assertIn("## 📅 Due / Scheduled", board)
        self.assertIn("- [ ] Scheduled item @2026-10-01", board)
        self.assertIn("## 📋 To Do", board)
        self.assertIn("- [ ] Backlog item", board)
        self.assertIn("## ✅ Done", board)
        self.assertIn("- [x] Finished item", board)

    def test_convert_to_kanban_file_output(self):
        item = {"id": "act-10", "description": "Single task"}
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "data.json"
            out = tmp / "Kanban.md"

            f.write_text(json.dumps([item]), encoding="utf-8")
            count = a2k.convert_to_kanban([f], out)

            self.assertEqual(count, 1)
            content = out.read_text(encoding="utf-8")
            self.assertIn("- [ ] Single task", content)


if __name__ == "__main__":
    unittest.main()
