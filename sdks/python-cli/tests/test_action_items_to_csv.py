"""Tests for action items to CSV exporter (#17826).

Pins formula neutralization, overwrite refusal, UTF-8 BOM encoding,
header structure, and completion status coercion.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# Load action_items_to_csv example script dynamically
script_path = (
    Path(__file__).resolve().parent.parent / "examples" / "action_items_to_csv.py"
)
spec = importlib.util.spec_from_file_location("action_items_to_csv", script_path)
ai2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2csv)


class TestActionItemsToCsv(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "act_01",
                "description": "Send quarterly review report",
                "completed": False,
                "due_at": "2026-09-25T15:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-20T10:00:00Z",
                "conversation_id": "conv_101",
            },
            {
                "id": "act_02",
                "description": "=SUM(A1:A10)",  # Formula trigger
                "completed": True,
                "due_at": None,
                "created_at": "2026-09-21T09:00:00Z",
                "updated_at": "2026-09-21T09:30:00Z",
                "conversation_id": "conv_102",
            },
            {
                "id": "act_03",
                "description": "@admin -2+3 cmd injection",  # Formula trigger
                "completed": "true",
                "due_at": None,
                "created_at": None,
                "updated_at": None,
                "conversation_id": None,
            },
        ]

    def test_formula_neutralization(self):
        """Values starting with =, +, -, @ or leading whitespace/tabs must be escaped."""
        # Standard formulas
        self.assertEqual(ai2csv.spreadsheet_text("=1+1"), "'=1+1")
        self.assertEqual(ai2csv.spreadsheet_text("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(ai2csv.spreadsheet_text("-2+3|cmd"), "'-2+3|cmd")
        self.assertEqual(ai2csv.spreadsheet_text("@SUM(B1:B5)"), "'@SUM(B1:B5)")

        # Leading whitespace/control chars
        self.assertEqual(ai2csv.spreadsheet_text("  =SUM(A1)"), "'  =SUM(A1)")
        self.assertEqual(ai2csv.spreadsheet_text("\t=A1"), "'\t=A1")
        self.assertEqual(ai2csv.spreadsheet_text("\n-test"), "'\n-test")

        # Benign text remains unescaped
        self.assertEqual(ai2csv.spreadsheet_text("Normal task"), "Normal task")
        self.assertEqual(ai2csv.spreadsheet_text(""), "")
        self.assertEqual(ai2csv.spreadsheet_text(None), "")

    def test_completed_text_coercion(self):
        """Completion status is cleanly coerced to 'yes' or 'no'."""
        self.assertEqual(ai2csv.completed_text(True), "yes")
        self.assertEqual(ai2csv.completed_text(False), "no")
        self.assertEqual(ai2csv.completed_text("true"), "yes")
        self.assertEqual(ai2csv.completed_text("1"), "yes")
        self.assertEqual(ai2csv.completed_text("yes"), "yes")
        self.assertEqual(ai2csv.completed_text("false"), "no")
        self.assertEqual(ai2csv.completed_text("0"), "no")
        self.assertEqual(ai2csv.completed_text(None), "no")

    def test_overwrite_refusal(self):
        """Convert must refuse to overwrite existing files to prevent data loss."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            json_file = tmp / "items.json"
            csv_file = tmp / "output.csv"

            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            # First conversion succeeds
            ai2csv.convert(json_file, csv_file)
            self.assertTrue(csv_file.exists())
            original_content = csv_file.read_bytes()

            # Second conversion attempt must raise FileExistsError
            with self.assertRaises(FileExistsError) as ctx:
                ai2csv.convert(json_file, csv_file)
            self.assertIn("Refusing to overwrite existing", str(ctx.exception))

            # Prior export must be unmodified
            self.assertEqual(csv_file.read_bytes(), original_content)

    def test_convert_end_to_end_and_utf8_bom(self):
        """End-to-end export preserves UTF-8 BOM, exact header, and row contents."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            json_file = tmp / "items.json"
            csv_file = tmp / "output.csv"

            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            ai2csv.convert(json_file, csv_file)

            raw_bytes = csv_file.read_bytes()
            # Verify UTF-8 BOM prefix for Excel / spreadsheet compatibility
            self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

            decoded = raw_bytes.decode("utf-8-sig")
            reader = list(csv.reader(decoded.splitlines()))

            # Header validation
            self.assertEqual(reader[0], list(ai2csv.FIELDS))
            self.assertEqual(len(reader), 4)  # 1 header + 3 data rows

            # Row 1 (act_01)
            self.assertEqual(reader[1][0], "act_01")
            self.assertEqual(reader[1][1], "Send quarterly review report")
            self.assertEqual(reader[1][2], "no")

            # Row 2 (act_02 with formula)
            self.assertEqual(reader[2][0], "act_02")
            self.assertEqual(reader[2][1], "'=SUM(A1:A10)")
            self.assertEqual(reader[2][2], "yes")

            # Row 3 (act_03 with @admin formula)
            self.assertEqual(reader[3][0], "act_03")
            self.assertEqual(reader[3][1], "'@admin -2+3 cmd injection")
            self.assertEqual(reader[3][2], "yes")

    def test_wrapped_json_dictionary(self):
        """Handles payloads wrapped in an 'action_items' dictionary key."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            json_file = tmp / "wrapped.json"
            csv_file = tmp / "output.csv"

            json_file.write_text(
                json.dumps({"action_items": self.sample_items}), encoding="utf-8"
            )
            ai2csv.convert(json_file, csv_file)

            decoded = csv_file.read_bytes().decode("utf-8-sig")
            reader = list(csv.reader(decoded.splitlines()))
            self.assertEqual(len(reader), 4)

    def test_empty_and_invalid_payloads(self):
        """Empty payload produces header-only CSV; missing ID raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)

            # Empty list
            empty_json = tmp / "empty.json"
            empty_csv = tmp / "empty.csv"
            empty_json.write_text(json.dumps([]), encoding="utf-8")
            ai2csv.convert(empty_json, empty_csv)

            decoded = empty_csv.read_bytes().decode("utf-8-sig")
            reader = list(csv.reader(decoded.splitlines()))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0], list(ai2csv.FIELDS))

            # Missing ID
            invalid_json = tmp / "invalid.json"
            invalid_csv = tmp / "invalid.csv"
            invalid_json.write_text(
                json.dumps([{"description": "No ID item"}]), encoding="utf-8"
            )
            with self.assertRaises(ValueError) as ctx:
                ai2csv.convert(invalid_json, invalid_csv)
            self.assertIn("missing an id", str(ctx.exception))
            # No partial file left behind
            self.assertFalse(invalid_csv.exists())


if __name__ == "__main__":
    unittest.main()
