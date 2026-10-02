"""Tests for conversations to JSONL exporter.

conversations_to_jsonl.py turns ``omi --json conversation list`` exports into
JSON Lines: one normalized, self-contained JSON object per line (no BOM,
compact, ``ensure_ascii=False``) with envelope unwrapping, loose row coercion,
category filtering, optional transcript embedding, and exclusive-creation
writes. These tests cover the converter API and the CLI contract hermetically —
no network, no services.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_jsonl.py"
spec = importlib.util.spec_from_file_location("conversations_to_jsonl", script_path)
c2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2j)

EXAMPLE_SCRIPT = script_path


def make_conversation(**overrides) -> dict:
    conv = {
        "id": "conv-1",
        "started_at": "2026-09-30T10:00:00Z",
        "finished_at": "2026-09-30T11:00:00Z",
        "source": "omi",
        "structured": {
            "title": "Weekly Sync",
            "category": "work",
            "overview": "Discussed the roadmap.",
            "action_items": [
                {"description": "Send the report", "completed": True},
                {"title": "Call Alice"},
                "plain string item",
            ],
        },
        "transcript_segments": [
            {"speaker": 0, "start": 0.0, "end": 3.5, "text": "Hello team"},
            {"speaker": "Alice", "start": 3.5, "end": 10.25, "text": "All good"},
        ],
    }
    conv.update(overrides)
    return conv


def lines_from(payload, **kwargs) -> list:
    raw = json.dumps(payload) if not isinstance(payload, str) else payload
    text = c2j.convert(raw, **kwargs).decode("utf-8")
    return text.splitlines()


def records_from(payload, **kwargs) -> list:
    return [json.loads(line) for line in lines_from(payload, **kwargs)]


class TestRecordNormalization(unittest.TestCase):
    def test_record_has_stable_key_order_and_shape(self):
        records = records_from([make_conversation()])
        self.assertEqual(
            list(records[0].keys()),
            ["id", "title", "category", "started_at", "finished_at", "source", "overview", "action_items"],
        )

    def test_transcript_excluded_by_default(self):
        self.assertNotIn("transcript_segments", records_from([make_conversation()])[0])

    def test_include_transcript_flag_embeds_segments(self):
        records = records_from([make_conversation()], include_transcript=True)
        self.assertEqual(
            records[0]["transcript_segments"],
            [
                {"speaker": "Speaker 0", "start": 0.0, "end": 3.5, "text": "Hello team"},
                {"speaker": "Alice", "start": 3.5, "end": 10.25, "text": "All good"},
            ],
        )

    def test_include_transcript_normalizes_segments(self):
        conv = make_conversation(transcript_segments=[{"speaker": {"weird": 1}, "start": "soon", "text": None}, "junk"])
        records = records_from([conv], include_transcript=True)
        self.assertEqual(
            records[0]["transcript_segments"],
            [{"speaker": "Speaker", "start": 0.0, "end": 0.0, "text": ""}],
        )

    def test_non_dict_transcript_rows_dropped_in_include_mode(self):
        conv = make_conversation(transcript_segments=["junk", {"speaker": 1, "text": "ok"}])
        records = records_from([conv], include_transcript=True)
        self.assertEqual(
            records[0]["transcript_segments"], [{"speaker": "Speaker 1", "start": 0.0, "end": 0.0, "text": "ok"}]
        )

    def test_missing_title_becomes_untitled(self):
        records = records_from([{"id": "c", "started_at": "2026-09-30T10:00:00Z"}])
        self.assertEqual(records[0]["title"], "Untitled Conversation")
        self.assertEqual(records[0]["category"], "general")

    def test_non_string_speaker_falls_back(self):
        self.assertEqual(c2j.speaker_label({"a": 1}), "Speaker")
        self.assertEqual(c2j.speaker_label(True), "Speaker")
        self.assertEqual(c2j.speaker_label(3), "Speaker 3")
        self.assertEqual(c2j.speaker_label(" Bob "), "Bob")

    def test_action_items_coerced_to_plain_dicts(self):
        records = records_from([make_conversation()])
        self.assertEqual(
            records[0]["action_items"],
            [
                {"description": "Send the report", "completed": True},
                {"description": "Call Alice", "completed": False},
                {"description": "plain string item", "completed": False},
            ],
        )

    def test_action_items_non_list_renders_empty(self):
        records = records_from([make_conversation(structured={"action_items": "nope"})])
        self.assertEqual(records[0]["action_items"], [])

    def test_overview_none_when_missing(self):
        records = records_from([{"id": "c", "structured": {}}])
        self.assertIsNone(records[0]["overview"])


class TestTimestamps(unittest.TestCase):
    def test_z_timestamps_normalized_to_utc_iso(self):
        records = records_from([make_conversation()])
        self.assertEqual(records[0]["started_at"], "2026-09-30T10:00:00+00:00")
        self.assertEqual(records[0]["finished_at"], "2026-09-30T11:00:00+00:00")

    def test_offset_timestamps_normalized(self):
        records = records_from([make_conversation(started_at="2026-09-30T12:30:00+02:00")])
        self.assertEqual(records[0]["started_at"], "2026-09-30T10:30:00+00:00")

    def test_naive_timestamp_becomes_utc(self):
        records = records_from([make_conversation(started_at="2026-09-30T10:00:00")])
        self.assertEqual(records[0]["started_at"], "2026-09-30T10:00:00+00:00")

    def test_unusable_timestamp_becomes_none(self):
        records = records_from([make_conversation(started_at="soon")])
        self.assertIsNone(records[0]["started_at"])

    def test_boundary_overflow_timestamp_kept_raw(self):
        # Structurally valid but out-of-range-for-UTC timestamps must not abort
        # the export; the raw value is preserved instead.
        records = records_from([make_conversation(started_at="0001-01-01T00:00:00+01:00")])
        self.assertEqual(records[0]["started_at"], "0001-01-01T00:00:00+01:00")

    def test_datetime_objects_accepted_in_process(self):
        row = c2j.conversation_record(make_conversation(started_at=datetime(2026, 9, 30, 10, tzinfo=timezone.utc)))
        self.assertEqual(row["started_at"], "2026-09-30T10:00:00+00:00")


class TestRowCoercion(unittest.TestCase):
    def test_non_dict_rows_are_skipped(self):
        records = records_from([make_conversation(), "junk", 42, None])
        self.assertEqual([r["id"] for r in records], ["conv-1"])

    def test_missing_id_becomes_none(self):
        records = records_from([{"structured": {"title": "T"}}])
        self.assertIsNone(records[0]["id"])

    def test_non_dict_structured_treated_as_empty(self):
        records = records_from([make_conversation(structured="oops")])
        self.assertEqual(records[0]["title"], "Untitled Conversation")

    def test_non_string_source_coerced(self):
        records = records_from([make_conversation(source=7)])
        self.assertEqual(records[0]["source"], "7")


class TestEnvelopeUnwrapping(unittest.TestCase):
    def test_bare_array(self):
        self.assertEqual(len(records_from([make_conversation()])), 1)

    def test_conversations_envelope(self):
        self.assertEqual(len(records_from({"conversations": [make_conversation()]})), 1)

    def test_items_envelope(self):
        self.assertEqual(len(records_from({"items": [make_conversation()]})), 1)

    def test_data_envelope(self):
        self.assertEqual(len(records_from({"data": [make_conversation()]})), 1)

    def test_results_envelope(self):
        self.assertEqual(len(records_from({"results": [make_conversation()]})), 1)

    def test_single_object(self):
        self.assertEqual(len(records_from({"id": "c", "structured": {}})), 1)

    def test_error_payload_yields_no_lines(self):
        self.assertEqual(records_from({"detail": "Not authenticated"}), [])

    def test_scalar_payload_raises_value_error(self):
        with self.assertRaises(ValueError):
            c2j.convert("42")

    def test_invalid_json_raises_json_decode_error(self):
        with self.assertRaises(json.JSONDecodeError):
            c2j.convert("{nope")


class TestCategoryFilter(unittest.TestCase):
    def test_convert_filtered_keeps_matching_rows(self):
        raw = json.dumps(
            [
                make_conversation(id="conv-work", structured={"category": "work"}),
                make_conversation(id="conv-personal", structured={"category": "personal"}),
            ]
        )
        records = [json.loads(line) for line in c2j.convert_filtered(raw, category="work").decode("utf-8").splitlines()]
        self.assertEqual([r["id"] for r in records], ["conv-work"])
        self.assertEqual([r["category"] for r in records], ["work"])

    def test_convert_filtered_multi_category(self):
        raw = json.dumps(
            [
                make_conversation(id="a", structured={"category": "work"}),
                make_conversation(id="b", structured={"category": "personal"}),
                make_conversation(id="c", structured={"category": "other"}),
            ]
        )
        records = [
            json.loads(line)
            for line in c2j.convert_filtered(raw, category="work,personal").decode("utf-8").splitlines()
        ]
        self.assertEqual([r["id"] for r in records], ["a", "b"])

    def test_convert_filtered_is_case_insensitive(self):
        raw = json.dumps([make_conversation(id="a", structured={"category": "Work"})])
        records = [json.loads(line) for line in c2j.convert_filtered(raw, category="WORK").decode("utf-8").splitlines()]
        self.assertEqual([r["id"] for r in records], ["a"])

    def test_filter_with_non_dict_rows_does_not_crash(self):
        raw = json.dumps([make_conversation(id="a", structured={"category": "work"}), "junk", 42])
        records = [json.loads(line) for line in c2j.convert_filtered(raw, category="work").decode("utf-8").splitlines()]
        self.assertEqual([r["id"] for r in records], ["a"])


class TestOutputBytes(unittest.TestCase):
    def test_one_line_per_record_with_trailing_newline(self):
        payload = c2j.convert(json.dumps([make_conversation(), make_conversation(id="conv-2")]))
        lines = payload.decode("utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertTrue(payload.endswith(b"\n"))

    def test_empty_selection_renders_empty_bytes(self):
        self.assertEqual(c2j.convert(json.dumps({"detail": "nope"})), b"")

    def test_no_bom_in_output(self):
        payload = c2j.convert(json.dumps([make_conversation()]))
        self.assertFalse(payload.startswith(b"\xef\xbb\xbf"))

    def test_unicode_stays_human_readable(self):
        payload = c2j.convert(json.dumps([make_conversation(structured={"title": "Họp Sprint 🎯"})]))
        self.assertIn("Họp Sprint 🎯".encode("utf-8"), payload)
        self.assertNotIn(b"\\u", payload)

    def test_every_line_is_valid_json(self):
        payload = c2j.convert(
            json.dumps([make_conversation(), make_conversation(id="conv-2"), make_conversation(id="conv-3")])
        )
        for line in payload.decode("utf-8").splitlines():
            json.loads(line)

    def test_deterministic_bytes(self):
        raw = json.dumps([make_conversation()])
        self.assertEqual(c2j.convert(raw), c2j.convert(raw))

    def test_convert_delegates_to_convert_filtered(self):
        raw = json.dumps([make_conversation()])
        self.assertEqual(c2j.convert(raw), c2j.convert_filtered(raw))
        raw2 = json.dumps([make_conversation(id="conv-x")])
        self.assertEqual(c2j.convert(raw2), c2j.convert_filtered(raw2))


class TestCliExitCodes(unittest.TestCase):
    @staticmethod
    def run_cli(*cli_args, stdin_bytes=None):
        return subprocess.run(
            [sys.executable, str(EXAMPLE_SCRIPT), *cli_args],
            input=stdin_bytes,
            capture_output=True,
            timeout=60,
        )

    def test_file_input_output_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_conversation()]), encoding="utf-8")
            out = Path(td) / "c.jsonl"
            result = self.run_cli(str(src), "-o", str(out))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertTrue(out.read_bytes().endswith(b"\n"))

    def test_stdin_pipe_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.jsonl"
            result = self.run_cli("-", "-o", str(out), stdin_bytes=json.dumps([make_conversation()]).encode("utf-8"))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertTrue(out.exists())

    def test_existing_output_refuses_overwrite_and_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_conversation()]), encoding="utf-8")
            out = Path(td) / "c.jsonl"
            out.write_bytes(b"keep me")
            result = self.run_cli(str(src), "-o", str(out))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"already exists", result.stderr)
            self.assertEqual(out.read_bytes(), b"keep me")

    def test_missing_input_file_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_cli(str(Path(td) / "nope.json"), "-o", str(Path(td) / "c.jsonl"))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"does not exist", result.stderr)

    def test_empty_payload_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text("   ", encoding="utf-8")
            result = self.run_cli(str(src), "-o", str(Path(td) / "c.jsonl"))
            self.assertEqual(result.returncode, 1)

    def test_invalid_json_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "bad.json"
            src.write_text("{nope", encoding="utf-8")
            result = self.run_cli(str(src), "-o", str(Path(td) / "c.jsonl"))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"Invalid JSON", result.stderr)

    def test_scalar_payload_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text("3.14", encoding="utf-8")
            result = self.run_cli(str(src), "-o", str(Path(td) / "c.jsonl"))
            self.assertEqual(result.returncode, 1)

    def test_category_filter_flag_excludes_non_matching(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(
                json.dumps(
                    [
                        make_conversation(id="conv-work", structured={"category": "work"}),
                        make_conversation(id="conv-other", structured={"category": "other"}),
                    ]
                ),
                encoding="utf-8",
            )
            out = Path(td) / "c.jsonl"
            result = self.run_cli(str(src), "--category", "work", "-o", str(out))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            exported = out.read_bytes()
            self.assertIn(b"conv-work", exported)
            self.assertNotIn(b"conv-other", exported)

    def test_include_transcript_flag_embeds_segments(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_conversation()]), encoding="utf-8")
            out = Path(td) / "c.jsonl"
            result = self.run_cli(str(src), "--include-transcript", "-o", str(out))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            record = json.loads(out.read_text(encoding="utf-8").strip())
            self.assertIn("transcript_segments", record)

    def test_no_output_flag_prints_jsonl_without_bom(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_conversation(structured={"title": "Tiếng Việt ☕"})]), encoding="utf-8")
            result = self.run_cli(str(src))
            self.assertEqual(result.returncode, 0)
            self.assertFalse(result.stdout.startswith(b"\xef\xbb\xbf"))
            self.assertIn("Tiếng Việt ☕".encode("utf-8"), result.stdout)

    def test_bom_prefixed_input_is_tolerated(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_bytes(b"\xef\xbb\xbf" + json.dumps([make_conversation()]).encode("utf-8"))
            out = Path(td) / "c.jsonl"
            result = self.run_cli(str(src), "-o", str(out))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertTrue(out.exists())

    def test_write_failure_cleans_partial_file_and_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_conversation()]), encoding="utf-8")
            # Writing into a directory-as-file path forces an OSError mid-open.
            blocker = Path(td) / "blocker"
            blocker.write_bytes(b"not a directory")
            target = blocker / "c.jsonl"
            result = self.run_cli(str(src), "-o", str(target))
            self.assertEqual(result.returncode == 1, True, result.stderr.decode("utf-8", "replace"))
            self.assertIn(b"failed to write", result.stderr)
            self.assertNotIn(b"Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
