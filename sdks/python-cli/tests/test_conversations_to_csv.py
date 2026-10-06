import csv
import json
import os
import sys
import tempfile
import unittest

# Add examples folder to sys.path
examples_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "examples"))
if examples_dir not in sys.path:
    sys.path.insert(0, examples_dir)

from conversations_to_csv import (
    FIELDS,
    spreadsheet_text,
    convert,
    main,
)


class TestConversationsToCsv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spreadsheet_text_escaping(self):
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text("normal"), "normal")
        self.assertEqual(spreadsheet_text(123), "123")
        self.assertEqual(spreadsheet_text({"foo": "bar"}), '{"foo": "bar"}')

        # Formula prefix escaping
        self.assertEqual(spreadsheet_text("=SUM(A1:B1)"), "'=SUM(A1:B1)")
        self.assertEqual(spreadsheet_text("+12345"), "'+12345")
        self.assertEqual(spreadsheet_text("-command"), "'-command")
        self.assertEqual(spreadsheet_text("@eval"), "'@eval")
        self.assertEqual(spreadsheet_text("   =whitespace_formula"), "'   =whitespace_formula")
        self.assertEqual(spreadsheet_text("\tleading_tab"), "'\tleading_tab")

    def test_basic_conversion(self):
        data = [
            {
                "id": "conv-1",
                "started_at": "2026-09-14T10:00:00Z",
                "source": "omi",
                "structured": {
                    "title": "Weekly Planning",
                    "category": "work",
                },
            },
            {
                "id": "conv-2",
                "started_at": "2026-09-14T12:00:00Z",
                "source": "friend",
                "structured": {
                    "title": "=calc_title",
                    "category": "personal",
                },
            },
        ]

        input_path = os.path.join(self.temp_dir.name, "conversations.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        output_path = os.path.join(self.temp_dir.name, "conversations.csv")
        count = convert(input_path, output_path)
        self.assertEqual(count, 2)

        # Check BOM and encoding
        with open(output_path, "rb") as bf:
            raw_bytes = bf.read()
        self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

        # Read CSV
        with open(output_path, "r", encoding="utf-8-sig", newline="") as f:
            reader = list(csv.reader(f))

        self.assertEqual(len(reader), 3)  # Header + 2 rows
        self.assertEqual(tuple(reader[0]), FIELDS)
        self.assertEqual(reader[1], ["conv-1", "Weekly Planning", "work", "2026-09-14T10:00:00Z", "omi"])
        self.assertEqual(reader[2], ["conv-2", "'=calc_title", "personal", "2026-09-14T12:00:00Z", "friend"])

    def test_envelope_unwrapping(self):
        payload = {
            "conversations": [
                {
                    "id": "c1",
                    "started_at": "2026-09-14T10:00:00Z",
                    "structured": {"title": "Title 1", "category": "cat"},
                }
            ]
        }
        input_path = os.path.join(self.temp_dir.name, "envelope.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)

        output_path = os.path.join(self.temp_dir.name, "output.csv")
        count = convert(input_path, output_path)
        self.assertEqual(count, 1)

    def test_refuses_overwrite(self):
        input_path = os.path.join(self.temp_dir.name, "input.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump([], f)

        output_path = os.path.join(self.temp_dir.name, "existing.csv")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("content")

        with self.assertRaises(FileExistsError):
            convert(input_path, output_path)

    def test_invalid_input(self):
        input_path = os.path.join(self.temp_dir.name, "bad.json")
        with open(input_path, "w", encoding="utf-8") as f:
            json.dump({"not_a_valid_list": True}, f)

        output_path = os.path.join(self.temp_dir.name, "out.csv")
        with self.assertRaises(ValueError):
            convert(input_path, output_path)

    def test_cli_usage(self):
        with self.assertRaises(SystemExit):
            main([])


if __name__ == "__main__":
    unittest.main()
