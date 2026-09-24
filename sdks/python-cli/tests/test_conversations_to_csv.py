"""Tests for conversations_to_csv recipe.

Covers:
- Header fields and row structure
- UTC timestamp normalization
- CSV formula injection protection
- Bare array vs wrapped JSON structure (conversations, items, data)
- Multi-file aggregation
- Graceful handling of missing optional fields
- ValueError on invalid or missing id fields
"""

from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load conversations_to_csv example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_csv.py"
spec = importlib.util.spec_from_file_location("conversations_to_csv", script_path)
c2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2c)

convert_paths_to_csv = c2c.convert_paths_to_csv
spreadsheet_text = c2c.spreadsheet_text
utc_stamp = c2c.utc_stamp
FIELDS = c2c.FIELDS


SAMPLE_CONVERSATIONS = [
    {
        "id": "conv_1",
        "source": "phone_microphone",
        "started_at": "2026-09-20T09:00:00Z",
        "created_at": "2026-09-20T09:01:00Z",
        "updated_at": "2026-09-20T09:05:00Z",
        "structured": {
            "title": "Team sync",
            "category": "work",
            "overview": "Quarterly planning and sprint reviews.",
            "action_items": [
                {"description": "Send meeting notes"},
                {"description": "Update roadmap"}
            ],
        },
        "transcript_segments": [
            {"speaker": "Alice", "text": "Good morning everyone."},
            {"speaker": "Bob", "text": "Morning! Let's get started."}
        ],
    },
    {
        "id": "conv_2",
        "source": "web_mic",
        "started_at": "2026-09-20T14:00:00+02:00",
        "created_at": "2026-09-20T14:01:00+02:00",
        "updated_at": "2026-09-20T14:05:00+02:00",
        "structured": {
            "title": "=SUM(1+1)",  # Formula injection attempt
            "category": "finance",
            "overview": "+calc() formula test",
        },
        "transcript": "Direct transcript body.",
    },
]


class TestConversationsToCsv(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.csv_path = self.dir_path / "conversations.csv"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_spreadsheet_text_sanitization(self):
        self.assertEqual(spreadsheet_text("normal text"), "normal text")
        self.assertEqual(spreadsheet_text("=cmd|'/C calc'!A0"), "'=cmd|'/C calc'!A0")
        self.assertEqual(spreadsheet_text("+12345"), "'+12345")
        self.assertEqual(spreadsheet_text("-discount"), "'-discount")
        self.assertEqual(spreadsheet_text("@eval"), "'@eval")
        self.assertEqual(spreadsheet_text(None), "")

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T11:00:00Z"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp("2026-09-20T13:00:00+02:00"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp(""), "")
        self.assertEqual(utc_stamp(None), "")

    def test_convert_bare_array(self):
        json_file = self.dir_path / "input.json"
        json_file.write_text(json.dumps(SAMPLE_CONVERSATIONS), encoding="utf-8")

        count = convert_paths_to_csv([json_file], self.csv_path)
        self.assertEqual(count, 2)
        self.assertTrue(self.csv_path.exists())

        with open(self.csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))

        self.assertEqual(len(reader), 2)
        row1 = reader[0]
        self.assertEqual(row1["id"], "conv_1")
        self.assertEqual(row1["title"], "Team sync")
        self.assertEqual(row1["category"], "work")
        self.assertEqual(row1["overview"], "Quarterly planning and sprint reviews.")
        self.assertEqual(row1["source"], "phone_microphone")
        self.assertEqual(row1["action_items_count"], "2")
        self.assertEqual(row1["turns_count"], "2")
        self.assertIn("Alice: Good morning everyone.", row1["transcript"])
        self.assertEqual(row1["started_at"], "2026-09-20 09:00:00")

        # Verify formula escaping on row2
        row2 = reader[1]
        self.assertEqual(row2["id"], "conv_2")
        self.assertEqual(row2["title"], "'=SUM(1+1)")
        self.assertEqual(row2["overview"], "'+calc() formula test")
        self.assertEqual(row2["transcript"], "Direct transcript body.")
        # UTC normalisation: 14:00+02:00 -> 12:00:00 UTC
        self.assertEqual(row2["started_at"], "2026-09-20 12:00:00")

    def test_convert_wrapped_dict(self):
        json_file = self.dir_path / "wrapped.json"
        wrapped = {"conversations": SAMPLE_CONVERSATIONS}
        json_file.write_text(json.dumps(wrapped), encoding="utf-8")

        count = convert_paths_to_csv([json_file], self.csv_path)
        self.assertEqual(count, 2)

        with open(self.csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
        self.assertEqual(len(reader), 2)

    def test_multi_file_aggregation(self):
        f1 = self.dir_path / "f1.json"
        f2 = self.dir_path / "f2.json"
        f1.write_text(json.dumps([SAMPLE_CONVERSATIONS[0]]), encoding="utf-8")
        f2.write_text(json.dumps([SAMPLE_CONVERSATIONS[1]]), encoding="utf-8")

        count = convert_paths_to_csv([f1, f2], self.csv_path)
        self.assertEqual(count, 2)

        with open(self.csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = list(csv.DictReader(f))
        self.assertEqual(len(reader), 2)
        self.assertEqual([r["id"] for r in reader], ["conv_1", "conv_2"])

    def test_missing_id_raises_value_error(self):
        invalid = [{"title": "No ID here"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_paths_to_csv([json_file], self.csv_path)
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
