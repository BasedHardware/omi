"""Tests for action items to CSV exporter (#18892).

Pins column header order, loose-type coercion, formula injection defense,
exclusive creation semantics, and UTF-8-sig BOM handling.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_csv.py"
spec = importlib.util.spec_from_file_location("action_items_to_csv", script_path)
ai2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2c)


class TestActionItemsToCSV(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "act_01",
                "description": "Buy groceries",
                "completed": False,
                "due_at": "2026-09-30T18:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-20T10:00:00Z",
                "conversation_id": "conv_999",
            },
            {
                "id": "act_02",
                "description": "=cmd|' /C calc'!A0",
                "completed": True,
                "due_at": None,
                "created_at": "2026-09-21T12:00:00Z",
                "updated_at": None,
                "conversation_id": None,
            },
        ]

    def test_spreadsheet_text_coercion_and_formula_guard(self):
        self.assertEqual(ai2c.spreadsheet_text("Task"), "Task")
        self.assertEqual(ai2c.spreadsheet_text(None), "")
        self.assertEqual(ai2c.spreadsheet_text(True), "True")
        self.assertEqual(ai2c.spreadsheet_text(False), "False")
        self.assertEqual(ai2c.spreadsheet_text(100), "100")

        # Formula guards
        self.assertEqual(ai2c.spreadsheet_text("=SUM(A1:A5)"), "'=SUM(A1:A5)")
        self.assertEqual(ai2c.spreadsheet_text("+44123"), "'+44123")
        self.assertEqual(ai2c.spreadsheet_text("-10"), "'-10")
        self.assertEqual(ai2c.spreadsheet_text("@alert"), "'@alert")
        self.assertEqual(ai2c.spreadsheet_text("\ttab_val"), "'\ttab_val")

    def test_convert_happy_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "actions.json"
            dst = Path(tmpdir) / "actions.csv"

            src.write_text(json.dumps(self.sample_items), encoding="utf-8")
            ai2c.convert(src, dst)

            raw_bytes = dst.read_bytes()
            self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

            content = dst.read_text(encoding="utf-8-sig")
            lines = [l.strip() for l in content.splitlines() if l.strip()]

            self.assertEqual(lines[0], ",".join(ai2c.FIELDS))
            self.assertIn("act_01,Buy groceries,False,2026-09-30T18:00:00Z", lines[1])
            self.assertIn("act_02,'=cmd|' /C calc'!A0,True,", lines[2])

    def test_refuse_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "actions.json"
            dst = Path(tmpdir) / "actions.csv"

            src.write_text(json.dumps(self.sample_items), encoding="utf-8")
            dst.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                ai2c.convert(src, dst)

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "empty.json"
            dst = Path(tmpdir) / "empty.csv"

            src.write_text("[]", encoding="utf-8")
            ai2c.convert(src, dst)

            content = dst.read_text(encoding="utf-8-sig")
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0], ",".join(ai2c.FIELDS))


if __name__ == "__main__":
    unittest.main()
