"""Tests for conversation to JSONL exporter (#20296).

Includes two complete rounds of Red-Blue adversarial stress tests:
  - Round 1: Extreme data distortion, corrupted payloads, and boundary attacks.
  - Round 2: I/O failure recovery, exclusive write safety, and atomicity guarantees.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Dynamically import conversations_to_jsonl from examples
script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_jsonl.py"
spec = importlib.util.spec_from_file_location("conversations_to_jsonl", script_path)
c2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2j)


class TestConversationsToJsonlCore(unittest.TestCase):
    """Core functionality and schema stability tests."""

    def test_single_conversation_record_schema(self):
        conv = {
            "id": "conv-001",
            "source": "omi",
            "started_at": "2026-10-16T12:00:00Z",
            "finished_at": "2026-10-16T12:30:00Z",
            "structured": {
                "title": "Roadmap Sync",
                "category": "work",
                "overview": "Quarterly planning session.",
                "action_items": [
                    {"description": "Send meeting notes", "completed": True},
                    {"description": "Update roadmap", "completed": False},
                ],
            },
        }

        rec = c2j.conversation_to_jsonl_record(conv, include_transcript=False)
        self.assertEqual(rec["id"], "conv-001")
        self.assertEqual(rec["title"], "Roadmap Sync")
        self.assertEqual(rec["category"], "work")
        self.assertEqual(rec["started_at"], "2026-10-16T12:00:00Z")
        self.assertEqual(rec["finished_at"], "2026-10-16T12:30:00Z")
        self.assertEqual(rec["source"], "omi")
        self.assertEqual(rec["overview"], "Quarterly planning session.")
        self.assertEqual(len(rec["action_items"]), 2)
        self.assertTrue(rec["action_items"][0]["completed"])
        self.assertFalse(rec["action_items"][1]["completed"])
        self.assertNotIn("transcript_segments", rec)

    def test_include_transcript_flag_embeds_segments(self):
        conv = {
            "id": "conv-002",
            "transcript_segments": [
                {"speaker": "Alice", "start": 0.0, "end": 2.5, "text": "Hello world."},
                {"speaker": "Bob", "start": 2.6, "end": 5.0, "text": "Hi Alice."},
            ],
        }
        rec = c2j.conversation_to_jsonl_record(conv, include_transcript=True)
        self.assertIn("transcript_segments", rec)
        segs = rec["transcript_segments"]
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0]["speaker"], "Alice")
        self.assertEqual(segs[0]["start"], 0.0)
        self.assertEqual(segs[0]["end"], 2.5)
        self.assertEqual(segs[0]["text"], "Hello world.")

    def test_default_does_not_include_transcript_segments(self):
        conv = {
            "id": "conv-003",
            "transcript_segments": [{"speaker": "Alice", "text": "Ignored by default"}],
        }
        rec = c2j.conversation_to_jsonl_record(conv, include_transcript=False)
        self.assertNotIn("transcript_segments", rec)

    def test_compact_json_formatting_without_extra_spaces(self):
        conv = {"id": "c1", "structured": {"title": "Test"}}
        lines = c2j.convert_conversations_to_jsonl([conv])
        self.assertEqual(len(lines), 1)
        line = lines[0]
        # Compact separators=(',', ':') means no '": "' or '", "' spaces
        self.assertIn('{"id":"c1"', line)
        self.assertIn('"title":"Test"', line)
        # Verify valid JSON round-trip
        decoded = json.loads(line)
        self.assertEqual(decoded["id"], "c1")


class TestRedTeamRound1DataAdversarial(unittest.TestCase):
    """Red Team Round 1: Extreme data distortion, corrupted payloads, and boundary attacks."""

    def test_utf8_bom_input_tolerance(self):
        data = [{"id": "c_bom", "structured": {"title": "BOM Test"}}]
        raw_json = json.dumps(data)
        bom_str = "\ufeff" + raw_json
        parsed = c2j.parse_json_safely(bom_str)
        lines = c2j.convert_conversations_to_jsonl(parsed)
        self.assertEqual(len(lines), 1)
        self.assertEqual(json.loads(lines[0])["id"], "c_bom")

    def test_timestamp_overflow_boundary_year_10000(self):
        # Year > 9999 triggers OverflowError in datetime
        raw_stamp = "10000-01-01T00:00:00Z"
        res = c2j.normalize_iso_utc(raw_stamp)
        self.assertEqual(res, raw_stamp)

    def test_timestamp_invalid_string_preserved(self):
        raw_stamp = "not-a-valid-timestamp"
        res = c2j.normalize_iso_utc(raw_stamp)
        self.assertEqual(res, "not-a-valid-timestamp")

    def test_timestamp_with_positive_offset(self):
        res = c2j.normalize_iso_utc("2026-10-16T20:00:00+08:00")
        self.assertEqual(res, "2026-10-16T12:00:00Z")

    def test_timestamp_with_negative_offset(self):
        res = c2j.normalize_iso_utc("2026-10-16T07:00:00-05:00")
        self.assertEqual(res, "2026-10-16T12:00:00Z")

    def test_timestamp_without_tz_treated_as_utc(self):
        res = c2j.normalize_iso_utc("2026-10-16T12:00:00")
        self.assertEqual(res, "2026-10-16T12:00:00Z")

    def test_timestamp_with_microseconds(self):
        res = c2j.normalize_iso_utc("2026-10-16T12:00:00.123456Z")
        self.assertEqual(res, "2026-10-16T12:00:00Z")

    def test_timestamp_none_and_empty(self):
        self.assertIsNone(c2j.normalize_iso_utc(None))
        self.assertIsNone(c2j.normalize_iso_utc(""))
        self.assertIsNone(c2j.normalize_iso_utc("   "))

    def test_action_item_string_coercion(self):
        raw_items = ["Deploy cluster", "Run smoke tests"]
        conv = {"id": "c_ai", "structured": {"action_items": raw_items}}
        rec = c2j.conversation_to_jsonl_record(conv)
        self.assertEqual(len(rec["action_items"]), 2)
        self.assertEqual(rec["action_items"][0], {"description": "Deploy cluster", "completed": False})
        self.assertEqual(rec["action_items"][1], {"description": "Run smoke tests", "completed": False})

    def test_action_item_completed_truthy_values(self):
        for truthy in [True, 1, 1.0, "true", "True", "YES", "1", "done", "completed"]:
            item = {"description": "Task", "completed": truthy}
            norm = c2j.normalize_action_item(item)
            self.assertTrue(norm["completed"], f"Failed for truthy value: {truthy}")

    def test_action_item_completed_falsy_values(self):
        for falsy in [False, 0, 0.0, "false", "no", "0", "", None, {}]:
            item = {"description": "Task", "completed": falsy}
            norm = c2j.normalize_action_item(item)
            self.assertFalse(norm["completed"], f"Failed for falsy value: {falsy}")

    def test_action_item_alternative_keys(self):
        item1 = {"text": "Alternative text key", "completed": True}
        item2 = {"content": "Alternative content key", "completed": False}
        self.assertEqual(c2j.normalize_action_item(item1)["description"], "Alternative text key")
        self.assertEqual(c2j.normalize_action_item(item2)["description"], "Alternative content key")

    def test_action_item_malformed_objects(self):
        self.assertEqual(c2j.normalize_action_item(12345), {"description": "12345", "completed": False})
        self.assertEqual(c2j.normalize_action_item(None), {"description": "", "completed": False})
        self.assertEqual(c2j.normalize_action_item({}), {"description": "", "completed": False})

    def test_api_error_payload_detail_drops_cleanly(self):
        error_payload = {"detail": "Conversation not found", "status_code": 404}
        convs = c2j.extract_conversations(error_payload)
        self.assertEqual(convs, [])

    def test_api_error_payload_error_drops_cleanly(self):
        error_payload = {"error": "Unauthorized access"}
        convs = c2j.extract_conversations(error_payload)
        self.assertEqual(convs, [])

    def test_envelope_unwrapping_conversations_key(self):
        payload = {"conversations": [{"id": "c1"}, {"id": "c2"}]}
        self.assertEqual(len(c2j.extract_conversations(payload)), 2)

    def test_envelope_unwrapping_items_key(self):
        payload = {"items": [{"id": "c1"}, {"id": "c2"}]}
        self.assertEqual(len(c2j.extract_conversations(payload)), 2)

    def test_envelope_unwrapping_data_key(self):
        payload = {"data": [{"id": "c1"}, {"id": "c2"}]}
        self.assertEqual(len(c2j.extract_conversations(payload)), 2)

    def test_envelope_unwrapping_results_key(self):
        payload = {"results": [{"id": "c1"}, {"id": "c2"}]}
        self.assertEqual(len(c2j.extract_conversations(payload)), 2)

    def test_envelope_unwrapping_with_dirty_elements(self):
        payload = {"data": [{"id": "c1"}, "dirty_string", None, 123, {"id": "c2"}]}
        extracted = c2j.extract_conversations(payload)
        self.assertEqual(len(extracted), 2)
        self.assertEqual([e["id"] for e in extracted], ["c1", "c2"])

    def test_bare_list_unwrapping(self):
        payload = [{"id": "c1"}, {"id": "c2"}]
        self.assertEqual(len(c2j.extract_conversations(payload)), 2)

    def test_single_conversation_dict_detection(self):
        payload = {"id": "c_single", "structured": {"title": "Standalone"}}
        extracted = c2j.extract_conversations(payload)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["id"], "c_single")

    def test_lone_surrogates_sanitization(self):
        dirty_str = "Title with surrogate \ud800 test"
        clean = c2j.strip_surrogates(dirty_str)
        self.assertNotIn("\ud800", clean)
        # Test serialization of surrogate-bearing record
        conv = {
            "id": "c_surr\ud800",
            "structured": {
                "title": "Title \ud800",
                "overview": "Overview \ud800",
                "action_items": [{"description": "Action \ud800", "completed": True}],
            },
            "transcript_segments": [{"speaker": "Speaker\ud800", "text": "Text\ud800"}],
        }
        rec = c2j.conversation_to_jsonl_record(conv, include_transcript=True)
        encoded = json.dumps(rec, ensure_ascii=False)
        self.assertNotIn("\ud800", encoded)

    def test_transcript_segment_float_coercion_and_fallbacks(self):
        seg1 = {"speaker": "A", "start": "1.5", "end": "3.5", "text": "Hello"}
        norm1 = c2j.normalize_transcript_segment(seg1)
        self.assertEqual(norm1["start"], 1.5)
        self.assertEqual(norm1["end"], 3.5)

        seg2 = {"speaker": "B", "start": "bad_float", "end": None, "text": "Test"}
        norm2 = c2j.normalize_transcript_segment(seg2)
        self.assertEqual(norm2["start"], 0.0)
        self.assertEqual(norm2["end"], 0.0)

    def test_transcript_segment_non_dict(self):
        norm = c2j.normalize_transcript_segment("String raw segment")
        self.assertEqual(norm["text"], "String raw segment")
        self.assertEqual(norm["speaker"], "")
        self.assertEqual(norm["start"], 0.0)

    def test_ensure_ascii_false_preserves_multilingual_characters(self):
        conv = {
            "id": "c_multi",
            "structured": {
                "title": "会议记录 - 日常同步",
                "overview": "Café with naïve résumé & 日本語テスト",
                "action_items": ["完成报告", "Send emails"],
            },
        }
        lines = c2j.convert_conversations_to_jsonl([conv])
        self.assertEqual(len(lines), 1)
        line = lines[0]
        self.assertIn("会议记录 - 日常同步", line)
        self.assertIn("Café with naïve résumé & 日本語テスト", line)
        self.assertIn("完成报告", line)


class TestRedTeamRound2IOAdversarial(unittest.TestCase):
    """Red Team Round 2: I/O failure recovery, exclusive write safety, and atomicity."""

    def test_exclusive_write_prevents_accidental_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "output.jsonl"
            out_file.write_text("pre-existing content\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                c2j.write_jsonl_exclusive(out_file, ['{"id":"new"}'])

            # Verify existing content is completely untouched
            self.assertEqual(out_file.read_text(encoding="utf-8"), "pre-existing content\n")

    def test_write_failure_cleans_up_temporary_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "sub" / "output.jsonl"

            # Simulate exception during writing
            with patch("builtins.open", side_effect=OSError("Disk full simulation")):
                with self.assertRaises(OSError):
                    c2j.write_jsonl_exclusive(out_file, ['{"id":"c1"}'])

            # Verify no partial files or temp files left
            self.assertFalse(out_file.exists())
            temp_files = list(Path(tmp_dir).glob(".*.tmp.*"))
            self.assertEqual(temp_files, [])

    def test_successful_exclusive_write_creates_valid_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "data.jsonl"
            lines = ['{"id":"1","title":"One"}', '{"id":"2","title":"Two"}']
            c2j.write_jsonl_exclusive(out_file, lines)

            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertEqual(content, '{"id":"1","title":"One"}\n{"id":"2","title":"Two"}\n')

    def test_empty_input_produces_empty_output_without_blank_lines(self):
        lines = c2j.convert_conversations_to_jsonl([])
        self.assertEqual(lines, [])

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "empty.jsonl"
            c2j.write_jsonl_exclusive(out_file, lines)
            self.assertEqual(out_file.read_text(encoding="utf-8"), "")

    def test_category_filter_matching(self):
        convs = [
            {"id": "1", "structured": {"category": "work"}},
            {"id": "2", "structured": {"category": "personal"}},
            {"id": "3", "structured": {"category": "Meeting"}},
        ]
        cats = {"work", "meeting"}
        filtered = c2j.filter_by_category(convs, cats)
        self.assertEqual(len(filtered), 2)
        self.assertEqual({c["id"] for c in filtered}, {"1", "3"})

    def test_category_filter_case_insensitivity(self):
        convs = [{"id": "1", "structured": {"category": "WORK"}}]
        cats = {"work"}
        filtered = c2j.filter_by_category(convs, cats)
        self.assertEqual(len(filtered), 1)

    def test_category_filter_passes_non_dict_or_missing_category_untouched(self):
        convs = [
            {"id": "1", "structured": {"category": "work"}},
            {"id": "2", "structured": {}},  # Missing category
            {"id": "3"},  # No structured dict at all
        ]
        cats = {"work"}
        filtered = c2j.filter_by_category(convs, cats)
        # Record 1 matches; records 2 and 3 have empty categories and pass untouched
        self.assertEqual(len(filtered), 3)

    def test_parse_category_arg(self):
        self.assertIsNone(c2j.parse_category_arg(None))
        self.assertIsNone(c2j.parse_category_arg(""))
        self.assertIsNone(c2j.parse_category_arg(" , "))
        self.assertEqual(c2j.parse_category_arg("work, MEETING, notes"), {"work", "meeting", "notes"})

    def test_cli_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "output.jsonl"
            in_file.write_text(json.dumps([{"id": "cli_1", "structured": {"title": "CLI Test"}}]), encoding="utf-8")

            exit_code = c2j.main([str(in_file), "-o", str(out_file)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())
            decoded = json.loads(out_file.read_text(encoding="utf-8").strip())
            self.assertEqual(decoded["id"], "cli_1")

    def test_cli_stdin_to_stdout(self):
        payload = json.dumps([{"id": "cli_pipe", "structured": {"title": "Pipe Test"}}])
        stdout_buf = io.StringIO()

        with patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", stdout_buf):
            exit_code = c2j.main(["-"])
            self.assertEqual(exit_code, 0)

        out_lines = stdout_buf.getvalue().strip().split("\n")
        self.assertEqual(len(out_lines), 1)
        self.assertEqual(json.loads(out_lines[0])["id"], "cli_pipe")

    def test_cli_stdin_with_utf8_bom(self):
        payload = "\ufeff" + json.dumps([{"id": "cli_bom_pipe", "structured": {"title": "BOM Pipe"}}])
        stdout_buf = io.StringIO()

        with patch("sys.stdin", io.StringIO(payload)), patch("sys.stdout", stdout_buf):
            exit_code = c2j.main(["-"])
            self.assertEqual(exit_code, 0)

        out_lines = stdout_buf.getvalue().strip().split("\n")
        self.assertEqual(len(out_lines), 1)
        self.assertEqual(json.loads(out_lines[0])["id"], "cli_bom_pipe")

    def test_cli_file_with_utf8_bom(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "bom_input.json"
            out_file = Path(tmp_dir) / "bom_output.jsonl"
            # Write with explicit BOM
            in_file.write_text(
                "\ufeff" + json.dumps([{"id": "cli_bom_file", "structured": {"title": "BOM File"}}]), encoding="utf-8"
            )

            exit_code = c2j.main([str(in_file), "-o", str(out_file)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.exists())
            decoded = json.loads(out_file.read_text(encoding="utf-8").strip())
            self.assertEqual(decoded["id"], "cli_bom_file")

    def test_cli_non_existent_input_file_returns_error(self):
        stderr_buf = io.StringIO()
        with patch("sys.stderr", stderr_buf):
            exit_code = c2j.main(["non_existent_file.json"])
            self.assertEqual(exit_code, 1)
        self.assertIn("does not exist", stderr_buf.getvalue())

    def test_cli_invalid_json_returns_error(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            bad_file = Path(tmp_dir) / "bad.json"
            bad_file.write_text("invalid json {", encoding="utf-8")

            stderr_buf = io.StringIO()
            with patch("sys.stderr", stderr_buf):
                exit_code = c2j.main([str(bad_file)])
                self.assertEqual(exit_code, 1)
            self.assertIn("Invalid JSON input", stderr_buf.getvalue())

    def test_large_dataset_scalability_stress(self):
        # Stress test with 1,000 synthesized records
        large_batch = [
            {
                "id": f"c_{i:04d}",
                "started_at": f"2026-10-{(i % 28) + 1:02d}T10:00:00Z",
                "structured": {
                    "title": f"Meeting {i}",
                    "category": "work" if i % 2 == 0 else "personal",
                    "overview": f"Overview content for session {i}",
                    "action_items": [f"Followup {i}"],
                },
                "transcript_segments": [{"speaker": "Speaker", "start": 0.0, "end": 10.0, "text": f"Audio for {i}"}],
            }
            for i in range(1000)
        ]

        lines = c2j.convert_conversations_to_jsonl(large_batch, include_transcript=True)
        self.assertEqual(len(lines), 1000)

        # Verify all lines parse as valid JSON
        for idx, line in enumerate(lines):
            parsed = json.loads(line)
            self.assertEqual(parsed["id"], f"c_{idx:04d}")
            self.assertEqual(len(parsed["action_items"]), 1)
            self.assertEqual(len(parsed["transcript_segments"]), 1)


if __name__ == "__main__":
    unittest.main()
