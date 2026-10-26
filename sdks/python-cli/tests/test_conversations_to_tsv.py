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
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_numeric_speakers_and_segment_aliases(self):
        segments = [
            {"speaker": 0, "text": "zero"},
            {"speaker": "0", "text": "string zero"},
            {"speaker": False, "text": "unlabelled"},
            {"speaker_name": " Ada ", "text": "named"},
            {"speaker_label": "Host", "text": "labelled"},
            {"speaker_id": 0, "text": "id zero"},
        ]
        for key in ("transcript_segments", "segments", "transcripts"):
            with self.subTest(key=key):
                self.assertEqual(
                    c2tsv.extract_transcript({key: segments}),
                    "0: zero 0: string zero unlabelled Ada: named Host: labelled 0: id zero",
                )

    def test_lone_surrogates_are_removed_without_losing_valid_unicode(self):
        record = {
            "id": "id\ud800",
            "title": "café \ud83d\ude80\udfff",
            "overview": {"detail": "keep \ud800世界"},
            "transcript": "before\udc00 after 😀",
        }
        rendered = c2tsv.conversations_to_tsv_string([record])
        rendered.encode("utf-8")
        fields = rendered.splitlines()[1].split("\t")
        self.assertEqual(fields[0], "id")
        self.assertEqual(fields[2], "café 🚀")
        self.assertEqual(fields[5], '{"detail": "keep 世界"}')
        self.assertEqual(fields[6], "before after 😀")

    def test_cli_writes_valid_utf8_for_json_surrogate_escapes(self):
        payload = json.dumps([{"id": "one", "title": "bad\ud800 text 😀"}]).encode("utf-8")
        result = subprocess.run(
            [sys.executable, str(_script_path), "-"], input=payload, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("bad text 😀", result.stdout.decode("utf-8", errors="strict"))

    def test_stdin_bom_has_the_same_behavior_as_file_bom(self):
        payload = b"\xef\xbb\xbf" + json.dumps([self.sample_conv_1]).encode("utf-8")
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "input.json"
            source.write_bytes(payload)
            from_file = subprocess.run(
                [sys.executable, str(_script_path), str(source)], capture_output=True, check=False
            )
            from_stdin = subprocess.run(
                [sys.executable, str(_script_path), "-"], input=payload, capture_output=True, check=False
            )
        self.assertEqual(from_file.returncode, 0, from_file.stderr)
        self.assertEqual(from_stdin.returncode, 0, from_stdin.stderr)
        self.assertEqual(from_stdin.stdout, from_file.stdout)

    def test_publication_failure_preserves_existing_output_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            source = directory / "input.json"
            destination = directory / "output.tsv"
            source.write_text("[]", encoding="utf-8")
            destination.write_text("original output", encoding="utf-8")
            with patch.object(c2tsv.os, "replace", side_effect=OSError("simulated publication failure")):
                with self.assertRaisesRegex(OSError, "publication failure"):
                    c2tsv.convert(str(source), str(destination), force=True)
            self.assertEqual(destination.read_text(encoding="utf-8"), "original output")
            self.assertEqual({path.name for path in directory.iterdir()}, {"input.json", "output.tsv"})

    def test_exclusive_publication_preserves_a_concurrently_created_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            source = directory / "input.json"
            destination = directory / "output.tsv"
            source.write_text("[]", encoding="utf-8")
            validate = c2tsv.validate_destination_path

            def create_after_validation(value, force=False):
                result = validate(value, force=force)
                result.write_text("concurrent writer", encoding="utf-8")
                return result

            with patch.object(c2tsv, "validate_destination_path", side_effect=create_after_validation):
                with self.assertRaises(FileExistsError):
                    c2tsv.convert(str(source), str(destination))
            self.assertEqual(destination.read_text(encoding="utf-8"), "concurrent writer")
            self.assertEqual({path.name for path in directory.iterdir()}, {"input.json", "output.tsv"})

    @unittest.skipIf(os.name == "nt", "POSIX permission bits are not the Windows ACL contract")
    def test_forced_publication_preserves_existing_permissions(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            source = directory / "input.json"
            destination = directory / "output.tsv"
            source.write_text("[]", encoding="utf-8")
            destination.write_text("old", encoding="utf-8")
            destination.chmod(0o640)
            c2tsv.convert(str(source), str(destination), force=True)
            self.assertEqual(destination.stat().st_mode & 0o777, 0o640)
            self.assertEqual({path.name for path in directory.iterdir()}, {"input.json", "output.tsv"})

    @unittest.skipIf(os.name == "nt", "Creating symlinks requires additional Windows privileges")
    def test_forced_publication_keeps_existing_output_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            directory = Path(tmp_dir)
            source = directory / "input.json"
            target = directory / "target.tsv"
            destination = directory / "output.tsv"
            source.write_text("[]", encoding="utf-8")
            target.write_text("old", encoding="utf-8")
            destination.symlink_to(target.name)
            c2tsv.convert(str(source), str(destination), force=True)
            self.assertTrue(destination.is_symlink())
            self.assertEqual(target.read_text(encoding="utf-8"), "\t".join(c2tsv.FIELDS) + "\n")


if __name__ == "__main__":
    unittest.main()
