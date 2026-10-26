"""Unit tests for conversation to TSV exporter (#19310).

Validates:
- Pure stdlib compliance (zero external dependencies).
- Envelope unwrapping for bare lists and wrapped structures ('conversations', 'items', 'data', 'results').
- Path traversal refusal with '..' in destination path.
- Strictly 1 line per record constraint with safe newline and tab escaping.
- File overwriting protection and force override.
- CLI argument parsing, stdin/stdout streaming, and exit code semantics.
"""

from __future__ import annotations

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

# Dynamically load examples/conversations_to_tsv.py module
_script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_tsv.py"
_spec = importlib.util.spec_from_file_location("conversations_to_tsv", _script_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load module from {_script_path}")
c2tsv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c2tsv)


class TestConversationsToTsv(unittest.TestCase):
    def setUp(self):
        self.sample_conv_1 = {
            "id": "c1111111-2222-3333-4444-555555555555",
            "started_at": "2026-09-27T10:00:00Z",
            "structured": {
                "title": "Weekly Standup",
                "category": "work",
                "overview": "First line of overview.\nSecond line of overview.\tWith a tab.",
            },
            "source": "omi_necklace",
            "transcript": "Speaker 1: Hello team.\r\nSpeaker 2: Morning everyone!",
        }
        self.sample_conv_2 = {
            "id": "c2222222-3333-4444-5555-666666666666",
            "started_at": "2026-09-27T14:30:00Z",
            "structured": {
                "title": "Coffee Chat",
                "category": "personal",
                "overview": "Casual catch-up.",
            },
            "source": "friend_v1",
            "segments": [
                {"speaker": "Alice", "text": "How is the bounty going?"},
                {"speaker": "Bob", "text": "Almost merged!"},
            ],
        }

    def test_empty_list_produces_only_header(self):
        tsv = c2tsv.conversations_to_tsv_string([])
        lines = tsv.strip().split("\n")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "\t".join(c2tsv.FIELDS))

    def test_bare_array_conversion(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "output.tsv"

            in_file.write_text(json.dumps([self.sample_conv_1, self.sample_conv_2]), encoding="utf-8")
            res = c2tsv.convert(str(in_file), str(out_file))

            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertEqual(res, content)
            lines = content.strip().split("\n")
            self.assertEqual(len(lines), 3)  # Header + 2 rows

    def test_envelope_unwrapping_conversations(self):
        data = {"conversations": [self.sample_conv_1]}
        items = c2tsv.unwrap_conversations(data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], self.sample_conv_1["id"])

    def test_envelope_unwrapping_items_data_results(self):
        for key in ("items", "data", "results"):
            data = {key: [self.sample_conv_2]}
            items = c2tsv.unwrap_conversations(data)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], self.sample_conv_2["id"])

    def test_strictly_one_line_per_record_with_newlines_and_tabs(self):
        conv_with_messy_controls = {
            "id": "conv-control-test",
            "started_at": "2026-09-27T00:00:00Z",
            "structured": {
                "title": "Title\nwith\r\nnewlines\tand\ttabs",
                "category": "misc",
                "overview": "Overview\rLine 1\r\nLine 2\tEnd",
            },
            "source": "manual",
            "transcript": "Line 1\nLine 2\r\nLine 3\tTabbed",
        }
        tsv = c2tsv.conversations_to_tsv_string([conv_with_messy_controls])
        lines = tsv.strip().split("\n")
        self.assertEqual(len(lines), 2)  # Strictly Header + 1 record

        record_line = lines[1]
        fields = record_line.split("\t")
        self.assertEqual(len(fields), 7)
        self.assertEqual(fields[0], "conv-control-test")
        self.assertEqual(fields[2], "Title\\nwith\\nnewlines\\tand\\ttabs")
        self.assertIn("Overview\\nLine 1\\nLine 2\\tEnd", fields[5])
        self.assertEqual(fields[6], "Line 1\\nLine 2\\nLine 3\\tTabbed")

    def test_segments_extraction_without_top_level_transcript(self):
        conv_segments = {
            "id": "c3",
            "segments": [
                {"speaker": "Speaker 0", "text": "Welcome to Omi."},
                {"speaker": "Speaker 1", "text": "Thank you."},
            ],
        }
        tsv = c2tsv.conversations_to_tsv_string([conv_segments])
        lines = tsv.strip().split("\n")
        self.assertIn("Speaker 0: Welcome to Omi. Speaker 1: Thank you.", lines[1])

    def test_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            in_file.write_text("[]", encoding="utf-8")
            invalid_dest = "../../../etc/passwd.tsv"
            with self.assertRaises(ValueError) as ctx:
                c2tsv.convert(str(in_file), invalid_dest)
            self.assertIn("contains '..'", str(ctx.exception))

    def test_file_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            in_file.write_text("[]", encoding="utf-8")
            out_file = Path(tmp_dir) / "existing.tsv"
            out_file.write_text("already exists", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                c2tsv.convert(str(in_file), str(out_file), force=False)

            # Test forced overwrite succeeds
            c2tsv.convert(str(in_file), str(out_file), force=True)
            self.assertEqual(out_file.read_text(encoding="utf-8").strip(), "\t".join(c2tsv.FIELDS))

    def test_malformed_json_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "bad.json"
            in_file.write_text("{this is not valid json", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                c2tsv.convert(str(in_file))
            self.assertIn("Malformed JSON", str(ctx.exception))

    def test_invalid_item_type_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "bad_array.json"
            in_file.write_text(json.dumps([{"id": "1"}, "not a dict"]), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                c2tsv.convert(str(in_file))
            self.assertIn("must be a JSON object", str(ctx.exception))

    def test_cli_end_to_end_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "out.tsv"
            in_file.write_text(json.dumps([self.sample_conv_1]), encoding="utf-8")

            exit_code = c2tsv.main([str(in_file), "-o", str(out_file)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())
            self.assertIn("Weekly Standup", out_file.read_text(encoding="utf-8"))

    def test_cli_stdin_to_stdout(self):
        saved_stdin = sys.stdin
        saved_stdout = sys.stdout
        try:
            sys.stdin = io.StringIO(json.dumps([self.sample_conv_2]))
            sys.stdout = io.StringIO()
            exit_code = c2tsv.main(["-"])
            self.assertEqual(exit_code, 0)
            output = sys.stdout.getvalue()
            self.assertIn("Coffee Chat", output)
            self.assertIn("c2222222-3333-4444-5555-666666666666", output)
        finally:
            sys.stdin = saved_stdin
            sys.stdout = saved_stdout

    def test_speaker_zero_and_alternate_speaker_keys_preserved(self):
        conv = {
            "id": "c-speaker-0",
            "segments": [
                {"speaker": 0, "text": "Speaking as zero"},
                {"speaker_id": "0", "text": "String zero id"},
                {"speaker_name": "Host", "text": "Speaking as host"},
                {"speaker": False, "text": "Boolean speaker ignored"},
            ],
        }
        tsv = c2tsv.conversations_to_tsv_string([conv])
        self.assertIn("0: Speaking as zero", tsv)
        self.assertIn("0: String zero id", tsv)
        self.assertIn("Host: Speaking as host", tsv)
        self.assertIn("Boolean speaker ignored", tsv)
        self.assertNotIn("False: Boolean speaker ignored", tsv)

    def test_lone_surrogates_stripped_without_encode_error(self):
        conv_with_surrogates = {
            "id": "c-surrogate",
            "structured": {
                "title": "Title with lone surrogate \ud800 in text",
                "overview": "Overview \ud83d\ude00 good and \ud800 bad",
            },
            "transcript": "Audio segment \ud800 clean \ud83d\ude0a",
        }
        # Escaped string should not contain unencodable lone surrogates
        tsv = c2tsv.conversations_to_tsv_string([conv_with_surrogates])
        # Verify writing to UTF-8 bytes succeeds without UnicodeEncodeError
        encoded = tsv.encode("utf-8")
        self.assertGreater(len(encoded), 0)
        self.assertIn("Title with lone surrogate", tsv)
        self.assertIn("Audio segment", tsv)

    def test_cli_stdin_with_utf8_bom(self):
        saved_stdin = sys.stdin
        saved_stdout = sys.stdout
        try:
            bom_json = "\ufeff" + json.dumps([self.sample_conv_1])
            sys.stdin = io.StringIO(bom_json)
            sys.stdout = io.StringIO()
            exit_code = c2tsv.main(["-"])
            self.assertEqual(exit_code, 0)
            self.assertIn("Weekly Standup", sys.stdout.getvalue())
        finally:
            sys.stdin = saved_stdin
            sys.stdout = saved_stdout

    def test_atomic_write_creates_valid_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "out.tsv"
            in_file.write_text(json.dumps([self.sample_conv_1]), encoding="utf-8")

            c2tsv.convert(str(in_file), str(out_file))
            self.assertTrue(out_file.exists())
            # Ensure no stray temp files remain in directory
            all_files = list(Path(tmp_dir).iterdir())
            self.assertEqual(len(all_files), 2)  # input.json and out.tsv

    def test_atomic_write_force_overwrite_replaces_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "out.tsv"
            out_file.write_text("old content", encoding="utf-8")
            in_file.write_text(json.dumps([self.sample_conv_1]), encoding="utf-8")

            # Default without force raises FileExistsError
            with self.assertRaises(FileExistsError):
                c2tsv.convert(str(in_file), str(out_file), force=False)

            # With force=True, atomically replaces existing file cleanly
            c2tsv.convert(str(in_file), str(out_file), force=True)
            self.assertIn("Weekly Standup", out_file.read_text(encoding="utf-8"))
            self.assertNotIn("old content", out_file.read_text(encoding="utf-8"))
            all_files = list(Path(tmp_dir).iterdir())
            self.assertEqual(len(all_files), 2)


if __name__ == "__main__":
    unittest.main()
