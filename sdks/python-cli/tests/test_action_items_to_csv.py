import csv
import json
import os
import tempfile
import unittest
from pathlib import Path

# Add examples and tests directory to path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_csv import (
    FIELDS,
    convert_action_items_to_csv,
    load_input_json,
    parse_boolean,
    parse_timestamp,
    spreadsheet_safe,
    transform_item,
    validate_output_path,
)


class TestActionItemsToCsv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.output_csv = self.dir_path / "output.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spreadsheet_safe_normal(self):
        self.assertEqual(spreadsheet_safe("Buy groceries"), "Buy groceries")
        self.assertEqual(spreadsheet_safe(12345), "12345")
        self.assertEqual(spreadsheet_safe(None), "")

    def test_spreadsheet_safe_injection_prefixes(self):
        self.assertEqual(spreadsheet_safe("=1+1"), "'=1+1")
        self.assertEqual(spreadsheet_safe("+cmd"), "'+cmd")
        self.assertEqual(spreadsheet_safe("-calc"), "'-calc")
        self.assertEqual(spreadsheet_safe("@SUM(A1:A5)"), "'@SUM(A1:A5)")
        self.assertEqual(spreadsheet_safe("\talert"), "'\talert")

    def test_parse_timestamp_utc(self):
        self.assertEqual(parse_timestamp("2026-10-04T12:00:00Z"), "2026-10-04 12:00:00")
        self.assertEqual(parse_timestamp("2026-10-04T14:00:00+02:00"), "2026-10-04 12:00:00")
        self.assertIsNone(parse_timestamp(None))
        self.assertIsNone(parse_timestamp(""))
        self.assertIsNone(parse_timestamp("not-a-date"))

    def test_parse_boolean(self):
        self.assertEqual(parse_boolean(True), "true")
        self.assertEqual(parse_boolean(False), "false")
        self.assertEqual(parse_boolean(1), "true")
        self.assertEqual(parse_boolean(0), "false")
        self.assertEqual(parse_boolean("yes"), "true")
        self.assertEqual(parse_boolean("no"), "false")
        self.assertEqual(parse_boolean("True"), "true")

    def test_transform_item(self):
        raw = {
            "id": "item_01",
            "description": "=Check quarterly financial metrics",
            "completed": True,
            "due_at": "2026-10-15T18:00:00Z",
            "created_at": "2026-10-01T08:30:00Z",
            "updated_at": "2026-10-02T09:00:00Z",
            "conversation_id": "conv_99",
        }
        row = transform_item(raw)
        self.assertEqual(row["id"], "item_01")
        self.assertEqual(row["description"], "'=Check quarterly financial metrics")
        self.assertEqual(row["completed"], "true")
        self.assertEqual(row["due_at"], "2026-10-15 18:00:00")
        self.assertEqual(row["created_at"], "2026-10-01 08:30:00")
        self.assertEqual(row["updated_at"], "2026-10-02 09:00:00")
        self.assertEqual(row["conversation_id"], "conv_99")

    def test_validate_output_path(self):
        valid = self.dir_path / "valid.csv"
        self.assertEqual(validate_output_path(str(valid)), valid)
        with self.assertRaises(ValueError):
            validate_output_path("../forbidden.csv")

    def test_convert_action_items_to_csv_e2e(self):
        items = [
            {
                "id": "act_1",
                "description": "Send follow up email",
                "completed": False,
                "due_at": "2026-10-10T15:00:00Z",
                "created_at": "2026-10-04T10:00:00Z",
                "conversation_id": "conv_1",
            },
            {
                "id": "act_2",
                "description": "Review pull request #123",
                "completed": True,
                "due_at": None,
                "created_at": "2026-10-03T09:00:00Z",
                "conversation_id": "conv_2",
            },
        ]

        count = convert_action_items_to_csv(items, str(self.output_csv))
        self.assertEqual(count, 2)
        self.assertTrue(self.output_csv.exists())

        with open(self.output_csv, mode="r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "act_1")
        self.assertEqual(rows[0]["description"], "Send follow up email")
        self.assertEqual(rows[0]["completed"], "false")
        self.assertEqual(rows[0]["due_at"], "2026-10-10 15:00:00")

        self.assertEqual(rows[1]["id"], "act_2")
        self.assertEqual(rows[1]["description"], "Review pull request #123")
        self.assertEqual(rows[1]["completed"], "true")
        self.assertEqual(rows[1]["due_at"], "")

    def test_convert_action_items_with_bom(self):
        items = [{"id": "act_bom", "description": "Accented text: café, résumé", "completed": False}]
        convert_action_items_to_csv(items, str(self.output_csv), include_bom=True)

        raw_bytes = self.output_csv.read_bytes()
        self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))  # UTF-8 BOM

    def test_load_input_json_formats(self):
        # Raw array
        array_path = self.dir_path / "array.json"
        array_path.write_text('[{"id": "1", "description": "Test"}]', encoding="utf-8")
        loaded = load_input_json(str(array_path))
        self.assertEqual(len(loaded), 1)

        # Wrapped dictionary
        wrapped_path = self.dir_path / "wrapped.json"
        wrapped_path.write_text('{"action_items": [{"id": "2", "description": "Wrapped"}]}', encoding="utf-8")
        loaded_wrapped = load_input_json(str(wrapped_path))
        self.assertEqual(len(loaded_wrapped), 1)
        self.assertEqual(loaded_wrapped[0]["id"], "2")


if __name__ == "__main__":
    unittest.main()
