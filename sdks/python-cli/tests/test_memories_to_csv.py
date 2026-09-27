import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

# Add parent directories to import path if needed
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from memories_to_csv import (
    CSV_HEADERS,
    spreadsheet_text,
    format_tags,
    parse_memories_payload,
    convert_to_csv,
    filter_memories,
    main,
)


class TestMemoriesToCsv(unittest.TestCase):
    def test_spreadsheet_text_sanitizes_formula_injection(self):
        self.assertEqual(spreadsheet_text("=1+1"), "'=1+1")
        self.assertEqual(spreadsheet_text("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(spreadsheet_text("-2+3"), "'-2+3")
        self.assertEqual(spreadsheet_text("@SUM(A1:A10)"), "'@SUM(A1:A10)")
        self.assertEqual(spreadsheet_text("Normal memory content"), "Normal memory content")
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text(""), "")

    def test_format_tags(self):
        self.assertEqual(format_tags(["work", "python"]), "work, python")
        self.assertEqual(format_tags("ai, prompt"), "ai, prompt")
        self.assertEqual(format_tags(None), "")
        self.assertEqual(format_tags([]), "")

    def test_parse_memories_payload(self):
        item = {"id": "mem_1", "content": "Test memory"}
        # Direct list
        self.assertEqual(parse_memories_payload([item]), [item])
        # Envelope with 'memories'
        self.assertEqual(parse_memories_payload({"memories": [item]}), [item])
        # Envelope with 'items'
        self.assertEqual(parse_memories_payload({"items": [item]}), [item])
        # Envelope with 'data'
        self.assertEqual(parse_memories_payload({"data": [item]}), [item])
        # Single object
        self.assertEqual(parse_memories_payload(item), [item])
        # Invalid payload
        self.assertEqual(parse_memories_payload("invalid string"), [])

    def test_convert_to_csv_output(self):
        memories = [
            {
                "id": "mem_1",
                "category": "work",
                "content": "Delivered Q3 roadmap",
                "tags": ["roadmap", "planning"],
                "visibility": "private",
                "is_user_created": True,
                "created_at": "2026-09-20T08:00:00Z",
                "updated_at": "2026-09-20T08:30:00Z",
            },
            {
                "id": "mem_2",
                "category": "learnings",
                "content": "=cmd|' /C calc'!A0",
                "tags": ["security"],
                "visibility": "public",
                "is_user_created": False,
                "created_at": "2026-09-21T09:00:00Z",
                "updated_at": "2026-09-21T09:00:00Z",
            },
        ]

        buf = io.StringIO()
        count = convert_to_csv(memories, buf)
        self.assertEqual(count, 2)

        buf.seek(0)
        reader = list(csv.DictReader(buf))
        self.assertEqual(len(reader), 2)

        row1 = reader[0]
        self.assertEqual(row1["id"], "mem_1")
        self.assertEqual(row1["category"], "work")
        self.assertEqual(row1["content"], "Delivered Q3 roadmap")
        self.assertEqual(row1["tags"], "roadmap, planning")
        self.assertEqual(row1["is_user_created"], "true")

        row2 = reader[1]
        self.assertEqual(row2["id"], "mem_2")
        # Assert formula injection was neutralized with leading quote
        self.assertEqual(row2["content"], "'=cmd|' /C calc'!A0")
        self.assertEqual(row2["is_user_created"], "false")

    def test_filter_memories(self):
        memories = [
            {"id": "m1", "category": "work", "tags": ["python", "ai"]},
            {"id": "m2", "category": "learnings", "tags": ["crypto"]},
            {"id": "m3", "category": "hobbies", "tags": ["music"]},
        ]

        # Category filter
        filtered_cat = filter_memories(memories, categories={"work", "learnings"})
        self.assertEqual([m["id"] for m in filtered_cat], ["m1", "m2"])

        # Tag filter
        filtered_tag = filter_memories(memories, tags={"crypto"})
        self.assertEqual([m["id"] for m in filtered_tag], ["m2"])

        # Both filters
        filtered_both = filter_memories(memories, categories={"work"}, tags={"python"})
        self.assertEqual([m["id"] for m in filtered_both], ["m1"])

    def test_main_cli_file_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dir_path = Path(tmp_dir)
            json_file = dir_path / "memories.json"
            csv_file = dir_path / "output.csv"

            sample_data = {
                "memories": [
                    {
                        "id": "mem_test",
                        "category": "workflow",
                        "content": "CLI testing in progress",
                        "tags": ["test"],
                    }
                ]
            }
            json_file.write_text(json.dumps(sample_data), encoding="utf-8")

            # Run CLI through main()
            exit_code = main([str(json_file), "-o", str(csv_file)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(csv_file.exists())

            # Verify UTF-8 BOM and content
            raw_bytes = csv_file.read_bytes()
            self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))  # UTF-8 BOM
            content = raw_bytes.decode("utf-8-sig")
            self.assertIn("CLI testing in progress", content)
            self.assertIn("workflow", content)


if __name__ == "__main__":
    unittest.main()
