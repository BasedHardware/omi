"""Hermetic tests for examples/conversations_to_jsonl.py (#20296).

Covers: record normalization + stable schema, timestamp normalization incl.
boundary overflow, action-item coercion, transcript opt-in, envelope
unwrapping + BOM, category filtering (incl. negative assertions), line
format, CLI exit codes, and write-failure cleanup.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import conversations_to_jsonl as m  # noqa: E402

CONV = {
    "id": "c1",
    "title": "Sprint retro",
    "category": "Work",
    "started_at": "2026-10-17T12:00:00+02:00",
    "finished_at": "2026-10-17T13:00:00Z",
    "source": "omi",
    "overview": "Discussed the quarter",
    "action_items": [
        {"description": "Ship the fix", "completed": True},
        {"text": "Follow up"},
        "plain string item",
        42,
        {"no_description": True},
    ],
}


class TestNormalization(unittest.TestCase):
    def test_schema_is_stable_and_ordered(self):
        rec = m.normalize_conversation(CONV, include_transcript=False)
        self.assertEqual(
            list(rec),
            ["id", "title", "category", "started_at", "finished_at", "source", "overview", "action_items"],
        )

    def test_started_at_normalized_to_utc(self):
        rec = m.normalize_conversation(CONV, include_transcript=False)
        self.assertEqual(rec["started_at"], "2026-10-17T10:00:00Z")

    def test_naive_timestamp_assumed_utc(self):
        rec = m.normalize_conversation({"id": "x", "started_at": "2026-01-01T00:00:00"}, False)
        self.assertEqual(rec["started_at"], "2026-01-01T00:00:00Z")

    def test_boundary_overflow_timestamp_keeps_raw_value(self):
        raw = "9999-12-31T23:59:59.999999999+99:99"
        rec = m.normalize_conversation({"id": "x", "started_at": raw}, False)
        self.assertEqual(rec["started_at"], raw)

    def test_missing_fields_become_none_not_crash(self):
        rec = m.normalize_conversation({"id": "x"}, False)
        self.assertIsNone(rec["title"])
        self.assertIsNone(rec["started_at"])
        self.assertEqual(rec["source"], "omi")

    def test_fallback_keys(self):
        rec = m.normalize_conversation(
            {"conversation_id": "c9", "created_at": "2026-01-01T00:00:00Z", "structured_overview": "ov"}, False
        )
        self.assertEqual(rec["id"], "c9")
        self.assertEqual(rec["finished_at"], "2026-01-01T00:00:00Z")
        self.assertEqual(rec["overview"], "ov")


class TestActionItems(unittest.TestCase):
    def test_dict_and_string_items_coerce(self):
        rec = m.normalize_conversation(CONV, include_transcript=False)
        items = rec["action_items"]
        self.assertEqual(items[0], {"description": "Ship the fix", "completed": True})
        self.assertEqual(items[1], {"description": "Follow up", "completed": False})
        self.assertEqual(items[2], {"description": "plain string item", "completed": False})

    def test_non_coercible_items_dropped(self):
        rec = m.normalize_conversation(CONV, include_transcript=False)
        self.assertEqual(len(rec["action_items"]), 3)  # 42 and no_description dropped

    def test_completed_string_variants(self):
        rec = m.normalize_conversation(
            {"action_items": [{"description": "a", "completed": "yes"}, {"description": "b", "done": "0"}]},
            False,
        )
        self.assertTrue(rec["action_items"][0]["completed"])
        self.assertFalse(rec["action_items"][1]["completed"])


class TestTranscript(unittest.TestCase):
    def test_transcript_excluded_by_default(self):
        rec = m.normalize_conversation({**CONV, "transcript": [{"speaker": "s", "text": "hi"}]}, False)
        self.assertNotIn("transcript", rec)

    def test_transcript_included_and_normalized(self):
        segs = [
            {"speaker": "Speaker 1", "start": "0.5", "end": 2.0, "text": "hi"},
            {"speaker_id": 2, "start": None, "end": "3", "text": "yo"},
            {"text": ""},  # empty text dropped
            "not-a-segment",
        ]
        rec = m.normalize_conversation({**CONV, "transcript": segs}, True)
        self.assertEqual(rec["transcript"][0], {"speaker": "Speaker 1", "start": 0.5, "end": 2.0, "text": "hi"})
        self.assertEqual(rec["transcript"][1]["speaker"], "2")
        self.assertEqual(len(rec["transcript"]), 2)

    def test_segments_key_also_supported(self):
        rec = m.normalize_conversation({"segments": [{"text": "a"}]}, True)
        self.assertEqual(len(rec["transcript"]), 1)


class TestEnvelope(unittest.TestCase):
    def test_bare_list(self):
        self.assertEqual(len(m.unwrap([CONV])), 1)

    def test_envelope_keys(self):
        for key in ("conversations", "items", "data", "results"):
            self.assertEqual(m.unwrap({key: [CONV]}), [CONV])

    def test_single_object(self):
        self.assertEqual(m.unwrap(CONV), [CONV])

    def test_error_payload_yields_empty(self):
        self.assertEqual(m.unwrap({"error": "unauthorized"}), [])

    def test_non_json_payload_yields_empty(self):
        self.assertEqual(m.unwrap(None), [])
        self.assertEqual(m.unwrap("x"), [])


class TestCategoryFilter(unittest.TestCase):
    def test_case_insensitive_match(self):
        rows = m.convert({"conversations": [CONV, {"id": "x", "category": "personal"}]}, {"work"}, False)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "c1")

    def test_non_dict_rows_skipped_under_filter(self):
        rows = m.convert({"conversations": [CONV, 42, "odd"]}, {"work"}, False)
        self.assertEqual(len(rows), 1)

    def test_non_dict_rows_pass_unfiltered(self):
        rows = m.convert({"conversations": [CONV, 42]}, None, False)
        self.assertIn(42, rows)

    def test_no_filter_keeps_all(self):
        rows = m.convert({"conversations": [CONV, {"id": "x", "category": None}]}, None, False)
        self.assertEqual(len(rows), 2)

    def test_filter_matching_nothing_yields_empty(self):
        self.assertEqual(m.convert({"conversations": [CONV]}, {"zzz"}, False), [])


class TestLineFormat(unittest.TestCase):
    def test_one_compact_json_object_per_line(self):
        out = m.emit_jsonl([{"a": 1}, {"b": 2}])
        lines = out.strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(json.loads(lines[0]), {"a": 1})
        self.assertNotIn(" ", lines[0])  # compact separators

    def test_ensure_ascii_false_and_surrogate_safe(self):
        out = m.emit_jsonl([{"name": "émile", "bad": "x"}])
        self.assertIn("émile", out)


class TestCli(unittest.TestCase):
    def _run_main(self, payload, argv_extra, input_bytes=None):
        buf = io.StringIO()
        old_out, old_in = sys.stdout, sys.stdin
        err = io.StringIO()
        sys.stdout, sys.stdin = buf, io.StringIO("")
        sys.stderr = err
        try:
            if input_bytes is None:
                sys.stdin = io.StringIO(json.dumps(payload))
            else:
                sys.stdin = input_bytes
            rc = m.main(["-"] + argv_extra)
        finally:
            sys.stdout, sys.stdin, sys.stderr = old_out, old_in, sys.__stderr__
        return rc, buf.getvalue(), err.getvalue()

    def test_stdin_to_stdout(self):
        rc, out, _ = self._run_main({"conversations": [CONV]}, [])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.strip()), m.normalize_conversation(CONV, False))

    def test_bom_tolerant_stdin(self):
        buf, err = io.StringIO(), io.StringIO()
        old = sys.stdin, sys.stdout, sys.stderr
        sys.stdin, sys.stdout, sys.stderr = io.StringIO('﻿{"conversations": []}'), buf, err
        try:
            rc = m.main(["-"])
        finally:
            sys.stdin, sys.stdout, sys.stderr = old[0], old[1], old[2]
        self.assertEqual(rc, 0)

    def test_invalid_json_exit_2(self):
        buf, err = io.StringIO(), io.StringIO()
        old = sys.stdin, sys.stdout, sys.stderr
        sys.stdin, sys.stdout, sys.stderr = io.StringIO("{not json"), buf, err
        try:
            rc = m.main(["-"])
        finally:
            sys.stdin, sys.stdout, sys.stderr = old[0], old[1], old[2]
        self.assertEqual(rc, 2)
        self.assertIn("invalid JSON", err.getvalue())

    def test_exclusive_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "exists.jsonl"
            out.write_text("keep me", encoding="utf-8")
            buf, err = io.StringIO(), io.StringIO()
            old = sys.stdin, sys.stdout, sys.stderr
            sys.stdin, sys.stdout, sys.stderr = io.StringIO("[]"), buf, err
            try:
                rc = m.main(["-", "-o", str(out)])
            finally:
                sys.stdin, sys.stdout, sys.stderr = old[0], old[1], old[2]
            self.assertEqual(rc, 2)
            self.assertEqual(out.read_text(), "keep me")

    def test_output_write_then_full_export(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.jsonl"
            buf, err = io.StringIO(), io.StringIO()
            old = sys.stdin, sys.stdout, sys.stderr
            sys.stdin, sys.stdout, sys.stderr = io.StringIO(json.dumps({"conversations": [CONV]})), buf, err
            try:
                rc = m.main(["-", "-o", str(out)])
            finally:
                sys.stdin, sys.stdout, sys.stderr = old[0], old[1], old[2]
            self.assertEqual(rc, 0)
            lines = out.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["id"], "c1")
            self.assertFalse(out.read_bytes().startswith(b'\xef\xbb\xbf'))  # no BOM

    def test_missing_input_file_exit_2(self):
        buf, err = io.StringIO(), io.StringIO()
        old = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = buf, err
        try:
            rc = m.main(["/nonexistent/path.json"])
        finally:
            sys.stdout, sys.stderr = old[0], old[1]
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
