"""Tests for conversations_to_csv recipe.

Covers:
- Formula injection protection (leading =, +, -, @, tabs, newlines)
- Data type coercion and handling of loosely typed dev-API fields
- Header and row correctness in exported CSV
- UTF-8 BOM encoding for Excel compatibility
- File existence protection (refusing to overwrite existing destinations)
- Schema validation (arrays, objects, structured fields)
- CLI entrypoint invocation and return codes
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

# Load conversations_to_csv example script dynamically to match project convention
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_csv.py"
spec = importlib.util.spec_from_file_location("conversations_to_csv", script_path)
c2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2c)

convert = c2c.convert
spreadsheet_text = c2c.spreadsheet_text
FIELDS = c2c.FIELDS
main = c2c.main


SAMPLE_CONVERSATIONS = [
    {
        "id": "conv_001",
        "source": "phone_microphone",
        "started_at": "2026-09-20T09:00:00Z",
        "structured": {
            "title": "Team Standup & Sprint Planning",
            "category": "work",
        },
    },
    {
        "id": "conv_002",
        "source": "wearable_omi",
        "started_at": "2026-09-20T14:30:00Z",
        "structured": {
            "title": "Coffee with Martin",
            "category": "personal",
        },
    },
]


class TestConversationsToCsv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.source_file = self.dir_path / "conversations.json"
        self.dest_file = self.dir_path / "conversations.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spreadsheet_text_formula_protection(self):
        """Formula injection attempts must be prepended with an apostrophe."""
        self.assertEqual(spreadsheet_text("=1+1"), "'=1+1")
        self.assertEqual(spreadsheet_text("+44123456"), "'+44123456")
        self.assertEqual(spreadsheet_text("-50.00"), "'-50.00")
        self.assertEqual(spreadsheet_text("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(spreadsheet_text("  =HYPERLINK()"), "'  =HYPERLINK()")
        self.assertEqual(spreadsheet_text("\tindented"), "'\tindented")
        self.assertEqual(spreadsheet_text("\nmultiline"), "'\nmultiline")

    def test_spreadsheet_text_safe_strings_and_types(self):
        """Normal strings and coerced types must render without alteration."""
        self.assertEqual(spreadsheet_text("Regular Title"), "Regular Title")
        self.assertEqual(spreadsheet_text(""), "")
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text(12345), "12345")
        self.assertEqual(spreadsheet_text(True), "True")
        self.assertEqual(spreadsheet_text({"tag": "ai"}), '{"tag": "ai"}')

    def test_convert_empty_list(self):
        """Converting an empty list must write only the header row."""
        self.source_file.write_text("[]", encoding="utf-8")
        count = convert(self.source_file, self.dest_file)
        self.assertEqual(count, 0)
        self.assertTrue(self.dest_file.exists())

        raw_bytes = self.dest_file.read_bytes()
        self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))  # UTF-8 BOM

        content = raw_bytes.decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(content)))
        self.assertEqual(len(reader), 1)
        self.assertEqual(tuple(reader[0]), FIELDS)

    def test_convert_valid_records(self):
        """Converting valid items must write header and data rows matching FIELDS."""
        self.source_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")
        count = convert(self.source_file, self.dest_file)
        self.assertEqual(count, 2)

        content = self.dest_file.read_bytes().decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(content)))
        self.assertEqual(len(reader), 3)  # Header + 2 data rows
        self.assertEqual(tuple(reader[0]), FIELDS)

        row1 = reader[1]
        self.assertEqual(row1[0], "conv_001")
        self.assertEqual(row1[1], "Team Standup & Sprint Planning")
        self.assertEqual(row1[2], "work")
        self.assertEqual(row1[3], "2026-09-20T09:00:00Z")
        self.assertEqual(row1[4], "phone_microphone")

        row2 = reader[2]
        self.assertEqual(row2[0], "conv_002")
        self.assertEqual(row2[1], "Coffee with Martin")
        self.assertEqual(row2[2], "personal")
        self.assertEqual(row2[3], "2026-09-20T14:30:00Z")
        self.assertEqual(row2[4], "wearable_omi")

    def test_convert_formula_injection_escaping(self):
        """Formula-prefixed values in conversation exports must be escaped in the output CSV."""
        items_with_formulas = [
            {
                "id": "conv_calc",
                "structured": {
                    "title": "=SUM(1,2)",
                    "category": "+finance",
                },
                "started_at": "-2026-10-04",
                "source": "@smart_mic",
            }
        ]
        self.source_file.write_text(json.dumps(items_with_formulas), encoding="utf-8")
        count = convert(self.source_file, self.dest_file)
        self.assertEqual(count, 1)

        content = self.dest_file.read_bytes().decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(content)))
        self.assertEqual(len(reader), 2)
        row = reader[1]
        self.assertEqual(row[0], "conv_calc")
        self.assertEqual(row[1], "'=SUM(1,2)")
        self.assertEqual(row[2], "'+finance")
        self.assertEqual(row[3], "'-2026-10-04")
        self.assertEqual(row[4], "'@smart_mic")

    def test_convert_missing_and_loose_fields(self):
        """Items with null structured field or missing keys must convert gracefully."""
        loose_items = [
            {"id": "conv_minimal"},
            {"id": "conv_null_struct", "structured": None},
            {"id": "conv_partial", "structured": {"title": "Only Title"}},
        ]
        self.source_file.write_text(json.dumps(loose_items), encoding="utf-8")
        count = convert(self.source_file, self.dest_file)
        self.assertEqual(count, 3)

        content = self.dest_file.read_bytes().decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(content)))
        self.assertEqual(len(reader), 4)

        # conv_minimal
        self.assertEqual(reader[1], ["conv_minimal", "", "", "", ""])
        # conv_null_struct
        self.assertEqual(reader[2], ["conv_null_struct", "", "", "", ""])
        # conv_partial
        self.assertEqual(reader[3], ["conv_partial", "Only Title", "", "", ""])

    def test_convert_unicode_and_special_chars(self):
        """Accents, non-ASCII characters, and quotes must be preserved faithfully."""
        unicode_items = [
            {
                "id": "conv_es_01",
                "source": "micrófono",
                "started_at": "2026-10-04T12:00:00Z",
                "structured": {
                    "title": "Reunión de diseño: arquitectura y métricas",
                    "category": "ingeniería",
                },
            }
        ]
        self.source_file.write_text(json.dumps(unicode_items, ensure_ascii=False), encoding="utf-8")
        convert(self.source_file, self.dest_file)

        content = self.dest_file.read_bytes().decode("utf-8-sig")
        reader = list(csv.reader(io.StringIO(content)))
        self.assertEqual(reader[1][1], "Reunión de diseño: arquitectura y métricas")
        self.assertEqual(reader[1][2], "ingeniería")
        self.assertEqual(reader[1][4], "micrófono")

    def test_convert_refuses_to_overwrite_existing(self):
        """Must raise FileExistsError if the target file already exists."""
        self.source_file.write_text("[]", encoding="utf-8")
        self.dest_file.write_text("pre-existing content", encoding="utf-8")

        with self.assertRaises(FileExistsError) as ctx:
            convert(self.source_file, self.dest_file)
        self.assertIn("Refusing to overwrite", str(ctx.exception))
        # Ensure pre-existing file content wasn't corrupted
        self.assertEqual(self.dest_file.read_text(encoding="utf-8"), "pre-existing content")

    def test_convert_invalid_inputs(self):
        """Corrupt JSON, non-list roots, or non-object items must raise ValueError."""
        # Non-JSON
        self.source_file.write_text("not json at all", encoding="utf-8")
        with self.assertRaises(ValueError):
            convert(self.source_file, self.dest_file)

        # JSON Object instead of list
        self.source_file.write_text('{"conversations": []}', encoding="utf-8")
        with self.assertRaises(ValueError):
            convert(self.source_file, self.dest_file)

        # List with non-dict items
        self.source_file.write_text('["string_item"]', encoding="utf-8")
        with self.assertRaises(ValueError):
            convert(self.source_file, self.dest_file)

        # List with invalid structured type
        self.source_file.write_text('[{"id": "1", "structured": "invalid"}]', encoding="utf-8")
        with self.assertRaises(ValueError):
            convert(self.source_file, self.dest_file)

    def test_main_cli_arguments(self):
        """CLI main function must validate arguments and exit codes appropriately."""
        # Missing arguments -> code 1
        self.assertEqual(main([]), 1)
        self.assertEqual(main(["only_one_arg"]), 1)

        # Valid arguments -> code 0
        self.source_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")
        code = main([str(self.source_file), str(self.dest_file)])
        self.assertEqual(code, 0)
        self.assertTrue(self.dest_file.exists())

        # Calling again on existing destination -> code 1 (fails due to overwrite protection)
        fail_code = main([str(self.source_file), str(self.dest_file)])
        self.assertEqual(fail_code, 1)


if __name__ == "__main__":
    unittest.main()
