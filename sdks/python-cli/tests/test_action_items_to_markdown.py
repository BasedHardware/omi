"""Tests for action items to markdown exporter (#13960).

Pins frontmatter structure, status and date grouping, multiline flattening,
metadata formatting, traversal protection in date grouping, and UTF-8 BOM handling.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# Load action_items_to_markdown example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_markdown.py"
spec = importlib.util.spec_from_file_location("action_items_to_markdown", script_path)
ai2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2m)


class TestActionItemsToMarkdown(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "act_01_review",
                "description": "Review architecture proposal for Second Brain CLI export",
                "completed": False,
                "due_at": "2026-09-25T15:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "conversation_id": "conv_12345",
            },
            {
                "id": "act_02_kicad",
                "description": "Fix KiCad schematic pin alignment clipping",
                "completed": True,
                "due_at": "2026-09-21T18:30:00Z",
                "created_at": "2026-09-19T08:00:00Z",
                "conversation_id": "conv_67890",
            },
            {
                "id": "act_03_undated",
                "description": "Verify Python CLI unit tests pass on all platforms",
                "completed": False,
                "due_at": None,
                "created_at": None,
                "conversation_id": None,
            },
        ]

    def test_frontmatter_and_summary(self):
        md = ai2m.items_to_markdown(self.sample_items, title="Sprint Action Items")
        self.assertIn("---", md)
        self.assertIn("type: action-items", md)
        self.assertIn("total: 3", md)
        self.assertIn("open: 2", md)
        self.assertIn("completed: 1", md)
        self.assertIn("tags:", md)
        self.assertIn("  - omi", md)
        self.assertIn("  - action-items", md)
        self.assertIn("  - tasks", md)
        self.assertIn("# Sprint Action Items", md)
        self.assertIn("> **Summary:** 2 open, 1 completed (3 total). Exported from Omi CLI.", md)

    def test_status_grouping_and_checkboxes(self):
        md = ai2m.items_to_markdown(self.sample_items, group_by="status")
        self.assertIn("## 📌 Pending Tasks", md)
        self.assertIn("## ✅ Completed Tasks", md)
        self.assertIn("- [ ] Review architecture proposal", md)
        self.assertIn("- [x] Fix KiCad schematic pin alignment clipping", md)
        self.assertIn("📅 Due: 2026-09-25 15:00 UTC", md)
        self.assertIn("🔗 [[conv_12345]]", md)
        self.assertIn("`#act_01_review`", md)
        self.assertIn("- [ ] Verify Python CLI unit tests pass on all platforms", md)

    def test_date_grouping(self):
        md = ai2m.items_to_markdown(self.sample_items, group_by="date")
        self.assertIn("## 📅 2026-09-25 (Due)", md)
        self.assertIn("## 📅 2026-09-21 (Due)", md)
        self.assertIn("## 📅 Undated", md)
        self.assertIn("- [ ] Review architecture proposal", md)
        self.assertIn("- [x] Fix KiCad schematic pin alignment clipping", md)
        self.assertIn("- [ ] Verify Python CLI unit tests pass", md)

    def test_flat_grouping(self):
        md = ai2m.items_to_markdown(self.sample_items, group_by="none")
        self.assertNotIn("## 📌 Pending Tasks", md)
        self.assertNotIn("## 📅", md)
        self.assertIn("- [ ] Review architecture proposal", md)
        self.assertIn("- [x] Fix KiCad schematic pin alignment clipping", md)

    def test_format_action_item_multiline_flattening(self):
        multiline_item = {
            "id": "act_multi",
            "description": "First line of task\nSecond line of details\r\nThird line of notes",
            "completed": False,
        }
        line = ai2m.format_action_item(multiline_item)
        self.assertIn("- [ ] First line of task Second line of details Third line of notes", line)

    def test_format_action_item_untitled_fallback(self):
        empty_item = {"id": "act_empty", "description": "", "completed": False}
        none_item = {"id": "act_none", "description": None, "completed": True}
        line_empty = ai2m.format_action_item(empty_item)
        line_none = ai2m.format_action_item(none_item)
        self.assertIn("- [ ] Untitled action item", line_empty)
        self.assertIn("- [x] Untitled action item", line_none)

    def test_load_input_data_formats(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 1. Plain list
            f1 = Path(tmp_dir) / "list.json"
            f1.write_text(json.dumps(self.sample_items), encoding="utf-8")
            items1 = ai2m.load_input_data(str(f1))
            self.assertEqual(len(items1), 3)

            # 2. Dict with "items"
            f2 = Path(tmp_dir) / "dict_items.json"
            f2.write_text(json.dumps({"items": self.sample_items}), encoding="utf-8")
            items2 = ai2m.load_input_data(str(f2))
            self.assertEqual(len(items2), 3)

            # 3. Dict with "action_items"
            f3 = Path(tmp_dir) / "dict_action_items.json"
            f3.write_text(json.dumps({"action_items": self.sample_items}), encoding="utf-8")
            items3 = ai2m.load_input_data(str(f3))
            self.assertEqual(len(items3), 3)

            # 4. Single dict
            f4 = Path(tmp_dir) / "single.json"
            f4.write_text(json.dumps(self.sample_items[0]), encoding="utf-8")
            items4 = ai2m.load_input_data(str(f4))
            self.assertEqual(len(items4), 1)
            self.assertEqual(items4[0]["id"], "act_01_review")

            # 5. Empty file
            f5 = Path(tmp_dir) / "empty.json"
            f5.write_text("", encoding="utf-8")
            items5 = ai2m.load_input_data(str(f5))
            self.assertEqual(items5, [])

    def test_traversal_containment_in_date_grouping(self):
        hostile_items = [
            {
                "id": "act_hostile",
                "description": "Hostile traversal attempt in due_at",
                "completed": False,
                "due_at": "../../etc/passwd",
                "created_at": None,
            },
            {
                "id": "act_normal",
                "description": "Normal action item",
                "completed": True,
                "due_at": "2026-09-20T12:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
            },
        ]
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir) / "vault" / "tasks"
            out_dir.mkdir(parents=True, exist_ok=True)

            # Simulate output-dir date grouping logic
            groups = {}
            for it in hostile_items:
                due_dt = ai2m.parse_datetime(it.get("due_at"))
                created_dt = ai2m.parse_datetime(it.get("created_at"))
                dt = due_dt or created_dt
                date_str = dt.strftime("%Y-%m-%d") if dt else "undated"
                import re
                date_prefix = date_str if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str) else "undated"
                groups.setdefault(date_prefix, []).append(it)

            for date_key, g_items in groups.items():
                filename = f"{date_key}_action_items.md"
                filepath = out_dir / filename
                content = ai2m.items_to_markdown(
                    g_items,
                    title=f"Omi Action Items — {date_key}",
                    group_by="status",
                )
                filepath.write_text(content, encoding="utf-8")

            resolved_out = out_dir.resolve()
            created_files = list(out_dir.glob("*.md"))
            self.assertEqual(len(created_files), 2)
            for f in created_files:
                self.assertTrue(f.resolve().is_relative_to(resolved_out))

            # The hostile item should have fallen back to undated_action_items.md
            undated_file = out_dir / "undated_action_items.md"
            self.assertTrue(undated_file.exists())
            self.assertIn("Hostile traversal attempt", undated_file.read_text(encoding="utf-8"))

    def test_bom_handling(self):
        payload_with_bom = b"\xef\xbb\xbf" + json.dumps({"action_items": self.sample_items}).encode("utf-8")
        with tempfile.NamedTemporaryFile("wb", delete=False) as tf:
            tf.write(payload_with_bom)
            temp_name = tf.name

        try:
            items = ai2m.load_input_data(temp_name)
            self.assertEqual(len(items), 3)
            self.assertEqual(items[0]["id"], "act_01_review")
        finally:
            Path(temp_name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
