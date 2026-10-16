"""Tests for conversation to CSV export recipe.

Hermetic test suite validating formula injection mitigation, UTF-8 BOM encoding,
path safety, loose typing resilience, and CLI handling.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

# Load conversations_to_csv example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_csv.py"
spec = importlib.util.spec_from_file_location("conversations_to_csv", script_path)
c2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2csv)


class TestSpreadsheetText(unittest.TestCase):
    def test_none_returns_empty_string(self):
        self.assertEqual(c2csv.spreadsheet_text(None), "")

    def test_plain_text_unmodified(self):
        self.assertEqual(c2csv.spreadsheet_text("Quarterly Sync"), "Quarterly Sync")
        self.assertEqual(c2csv.spreadsheet_text("Engineering"), "Engineering")

    def test_non_string_coercion(self):
        self.assertEqual(c2csv.spreadsheet_text(42), "42")
        self.assertEqual(c2csv.spreadsheet_text(True), "True")
        self.assertEqual(c2csv.spreadsheet_text({"key": "val"}), '{"key": "val"}')
        self.assertEqual(c2csv.spreadsheet_text([1, 2, 3]), "[1, 2, 3]")

    def test_formula_prefixes_escaped_with_apostrophe(self):
        prefixes = ["=SUM(A1:B2)", "+12345", "-cmd|' /C calc'!A0", "@SUM(1, 2)"]
        for p in prefixes:
            self.assertEqual(c2csv.spreadsheet_text(p), "'" + p)

    def test_whitespace_padded_formula_prefixes_escaped(self):
        self.assertEqual(c2csv.spreadsheet_text("   =1+1"), "'   =1+1")
        self.assertEqual(c2csv.spreadsheet_text("  +cmd"), "'  +cmd")

    def test_leading_whitespace_characters_escaped(self):
        self.assertEqual(c2csv.spreadsheet_text("\ttab_leading"), "'\ttab_leading")
        self.assertEqual(c2csv.spreadsheet_text("\rreturn_leading"), "'\rreturn_leading")
        self.assertEqual(c2csv.spreadsheet_text("\nnewline_leading"), "'\nnewline_leading")


class TestExtractConversations(unittest.TestCase):
    def test_bare_list(self):
        payload = json.dumps([{"id": "c1", "structured": {"title": "Test 1"}}])
        items = c2csv.extract_conversations(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "c1")

    def test_wrapped_conversations_dict(self):
        payload = json.dumps({"conversations": [{"id": "c1"}, {"id": "c2"}]})
        items = c2csv.extract_conversations(payload)
        self.assertEqual(len(items), 2)

    def test_wrapped_items_dict(self):
        payload = json.dumps({"items": [{"id": "c1"}]})
        items = c2csv.extract_conversations(payload)
        self.assertEqual(len(items), 1)

    def test_wrapped_data_dict(self):
        payload = json.dumps({"data": [{"id": "c1"}]})
        items = c2csv.extract_conversations(payload)
        self.assertEqual(len(items), 1)

    def test_wrapped_results_dict(self):
        payload = json.dumps({"results": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]})
        items = c2csv.extract_conversations(payload)
        self.assertEqual([item["id"] for item in items], ["c1", "c2", "c3"])

    def test_single_object(self):
        payload = json.dumps({"id": "c1", "structured": {"title": "Solo"}})
        items = c2csv.extract_conversations(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "c1")

    def test_utf8_bom_bytes(self):
        payload = b"\xef\xbb\xbf" + json.dumps([{"id": "c1"}]).encode("utf-8")
        items = c2csv.extract_conversations(payload)
        self.assertEqual(len(items), 1)

    def test_invalid_json_raises_value_error(self):
        with self.assertRaises(ValueError):
            c2csv.extract_conversations("not json")

    def test_non_dict_element_raises_value_error(self):
        with self.assertRaises(ValueError):
            c2csv.extract_conversations(json.dumps(["string_instead_of_object"]))


class TestValidateDestination(unittest.TestCase):
    def test_path_traversal_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            c2csv.validate_destination("../outside.csv")
        self.assertIn("..", str(ctx.exception))

    def test_refuse_overwrite_when_not_allowed(self):
        with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
            with self.assertRaises(FileExistsError):
                c2csv.validate_destination(tmp.name, overwrite=False)

    def test_allow_overwrite_when_requested(self):
        with tempfile.NamedTemporaryFile(suffix=".csv") as tmp:
            p = c2csv.validate_destination(tmp.name, overwrite=True)
            self.assertEqual(p, Path(tmp.name))


class TestConvertConversationsToCsv(unittest.TestCase):
    def test_conversion_produces_utf8_bom_and_expected_rows(self):
        data = [
            {
                "id": "conv-101",
                "structured": {"title": "Product Strategy", "category": "Work"},
                "started_at": "2026-10-01T15:00:00Z",
                "source": "omi-device",
            },
            {
                "id": "conv-102",
                "structured": {"title": "=DANGEROUS_FORMULA()", "category": None},
                "started_at": "2026-10-01T16:00:00Z",
                "source": "ios",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "conversations.json"
            out_file = Path(tmp_dir) / "output.csv"
            in_file.write_text(json.dumps(data), encoding="utf-8")

            count = c2csv.convert(in_file, out_file)
            self.assertEqual(count, 2)
            self.assertTrue(out_file.exists())

            raw_bytes = out_file.read_bytes()
            self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

            decoded_text = raw_bytes.decode("utf-8-sig")
            reader = list(csv.reader(io.StringIO(decoded_text)))

            # Header verification
            self.assertEqual(reader[0], ["id", "title", "category", "started_at", "source"])
            # Row 1
            self.assertEqual(reader[1], ["conv-101", "Product Strategy", "Work", "2026-10-01T15:00:00Z", "omi-device"])
            # Row 2 with formula neutralization
            self.assertEqual(reader[2], ["conv-102", "'=DANGEROUS_FORMULA()", "", "2026-10-01T16:00:00Z", "ios"])

    def test_empty_conversations_produces_header_only(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "empty.json"
            out_file = Path(tmp_dir) / "output.csv"
            in_file.write_text("[]", encoding="utf-8")

            count = c2csv.convert(in_file, out_file)
            self.assertEqual(count, 0)

            reader = list(csv.reader(io.StringIO(out_file.read_text(encoding="utf-8-sig"))))
            self.assertEqual(len(reader), 1)
            self.assertEqual(reader[0], ["id", "title", "category", "started_at", "source"])

    def test_nested_directory_creation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "nested" / "sub" / "output.csv"
            in_file.write_text('[{"id": "1"}]', encoding="utf-8")

            c2csv.convert(in_file, out_file)
            self.assertTrue(out_file.exists())

    def test_missing_input_file_raises_filenotfound(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            with self.assertRaises(FileNotFoundError):
                c2csv.convert(Path(tmp_dir) / "nonexistent.json", Path(tmp_dir) / "out.csv")


    def test_stdin_source(self):
        stdin = mock.Mock()
        stdin.buffer = io.BytesIO(b'\xef\xbb\xbf{"results": [{"id": "s1", "structured": {"title": "Piped"}}]}')
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "out.csv"
            with mock.patch.object(c2csv.sys, "stdin", stdin):
                count = c2csv.convert("-", out_file)
            self.assertEqual(count, 1)
            rows = list(csv.reader(io.StringIO(out_file.read_text(encoding="utf-8-sig"))))
            self.assertEqual(rows[1][:2], ["s1", "Piped"])

    def test_overwrite_failure_keeps_previous_export_intact(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "out.csv"
            in_file.write_text('[{"id": "new"}]', encoding="utf-8")
            out_file.write_text("previous export", encoding="utf-8")

            with mock.patch.object(c2csv.os, "fsync", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    c2csv.convert(in_file, out_file, overwrite=True)

            self.assertEqual(out_file.read_text(encoding="utf-8"), "previous export")
            self.assertEqual(sorted(p.name for p in Path(tmp_dir).iterdir()), ["input.json", "out.csv"])

    def test_overwrite_replaces_existing_export(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "out.csv"
            in_file.write_text('[{"id": "new"}]', encoding="utf-8")
            out_file.write_text("previous export", encoding="utf-8")

            c2csv.convert(in_file, out_file, overwrite=True)

            rows = list(csv.reader(io.StringIO(out_file.read_text(encoding="utf-8-sig"))))
            self.assertEqual(rows[1][0], "new")


class TestCli(unittest.TestCase):
    def test_cli_success(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "conv.json"
            out_file = Path(tmp_dir) / "conv.csv"
            in_file.write_text('[{"id": "c1", "structured": {"title": "Sync"}}]', encoding="utf-8")

            with mock.patch("sys.stdout", new_callable=io.StringIO):
                code = c2csv.main([str(in_file), str(out_file)])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())

    def test_cli_with_output_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "conv.json"
            out_file = Path(tmp_dir) / "conv.csv"
            in_file.write_text('[{"id": "c1"}]', encoding="utf-8")

            with mock.patch("sys.stdout", new_callable=io.StringIO):
                code = c2csv.main([str(in_file), "-o", str(out_file)])
            self.assertEqual(code, 0)
            self.assertTrue(out_file.exists())

    def test_cli_rejects_both_destination_forms(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "conv.json"
            in_file.write_text('[{"id": "c1"}]', encoding="utf-8")
            positional, flagged = Path(tmp_dir) / "a.csv", Path(tmp_dir) / "b.csv"

            with mock.patch("sys.stderr", new_callable=io.StringIO):
                with self.assertRaises(SystemExit) as ctx:
                    c2csv.main([str(in_file), str(positional), "-o", str(flagged)])
            self.assertEqual(ctx.exception.code, 2)
            self.assertFalse(positional.exists())
            self.assertFalse(flagged.exists())

    def test_cli_overwrite_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "conv.json"
            out_file = Path(tmp_dir) / "conv.csv"
            in_file.write_text('[{"id": "c1"}]', encoding="utf-8")
            out_file.write_text("existing", encoding="utf-8")

            # Without overwrite -> fails (returns 1)
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                code_fail = c2csv.main([str(in_file), str(out_file)])
            self.assertEqual(code_fail, 1)

            # With overwrite -> succeeds (returns 0)
            with mock.patch("sys.stdout", new_callable=io.StringIO):
                code_ok = c2csv.main([str(in_file), str(out_file), "--overwrite"])
            self.assertEqual(code_ok, 0)


if __name__ == "__main__":
    unittest.main()
