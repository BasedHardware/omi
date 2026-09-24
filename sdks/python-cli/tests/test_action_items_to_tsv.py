"""Tests for Omi action items to TSV export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_tsv.py"
spec = importlib.util.spec_from_file_location("action_items_to_tsv", script_path)
a2t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2t)


class TestActionItemsToTsv(unittest.TestCase):
    def test_utc_stamp_and_boolean(self):
        self.assertEqual(a2t.utc_stamp("2026-09-24T12:00:00Z"), "2026-09-24 12:00:00")
        self.assertEqual(a2t.utc_stamp(None), "")
        self.assertTrue(a2t.parse_boolean(True))
        self.assertTrue(a2t.parse_boolean("true"))
        self.assertFalse(a2t.parse_boolean(False))

    def test_spreadsheet_tsv_text_escaping(self):
        # Formula injection prevention
        self.assertEqual(a2t.spreadsheet_tsv_text("=SUM(A1:B1)"), "'=SUM(A1:B1)")
        self.assertEqual(a2t.spreadsheet_tsv_text("+123"), "'+123")
        self.assertEqual(a2t.spreadsheet_tsv_text("-100"), "'-100")
        self.assertEqual(a2t.spreadsheet_tsv_text("@mention"), "'@mention")

        # Tab and newline stripping
        self.assertEqual(a2t.spreadsheet_tsv_text("Col1\tCol2\r\nCol3"), "Col1 Col2 Col3")

    def test_extract_action_items(self):
        raw_list = '[{"id": "act-1", "description": "Review code"}]'
        raw_wrapped = '{"action_items": [{"id": "act-2", "description": "Deploy app"}]}'

        res1 = a2t.extract_action_items(raw_list)
        res2 = a2t.extract_action_items(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "act-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "act-2")

    def test_convert_to_tsv_tab_delimitation_and_filtering(self):
        item1 = {"id": "act-1", "description": "Task 1", "completed": False, "due_at": "2026-09-25T10:00:00Z"}
        item2 = {"id": "act-2", "description": "Task 2", "completed": True}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "tasks.json"
            out = tmp / "tasks.tsv"

            f.write_text(json.dumps([item1, item2]), encoding="utf-8")

            # All items
            count = a2t.convert_to_tsv([f], out, status_filter="all")
            self.assertEqual(count, 2)
            lines = out.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 3)  # header + 2 rows

            header = lines[0].split("\t")
            self.assertEqual(header, list(a2t.FIELDS))

            row1 = lines[1].split("\t")
            self.assertEqual(row1[0], "act-1")
            self.assertEqual(row1[1], "Task 1")
            self.assertEqual(row1[2], "FALSE")

            # Open items only
            out_open = tmp / "open.tsv"
            count_open = a2t.convert_to_tsv([f], out_open, status_filter="open")
            self.assertEqual(count_open, 1)
            open_lines = out_open.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(open_lines), 2)  # header + 1 row


if __name__ == "__main__":
    unittest.main()
