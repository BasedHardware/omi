"""Tests for memories to CSV exporter.

memories_to_csv.py turns ``omi --json memory list`` exports into a
spreadsheet-ready CSV: fixed columns, RFC-4180 quoting, formula-injection-safe
cells (the established ``spreadsheet_text`` idiom from the conversations CSV
recipe), pipe-joined tags, UTC-normalized timestamps, UTF-8 BOM, loose row
coercion, and exclusive-creation writes. These tests cover the converter API
and the CLI contract (exit codes, stdin, filters) hermetically — no network,
no services.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_csv.py"
spec = importlib.util.spec_from_file_location("memories_to_csv", script_path)
m2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2csv)

EXAMPLE_SCRIPT = script_path


def make_memory(**overrides) -> dict:
    memory = {
        "id": "mem-1",
        "content": "Prefers morning deep work",
        "category": "habits",
        "tags": ["focus", "q4"],
        "visibility": "private",
        "created_at": "2026-09-30T10:00:00Z",
        "updated_at": "2026-09-30T11:00:00Z",
        "app_id": "app-1",
    }
    memory.update(overrides)
    return memory


def rows_from(csv_text: str) -> list:
    reader = csv.reader(io.StringIO(csv_text))
    return list(reader)


def convert_rows(payload) -> list:
    raw = json.dumps(payload)
    return rows_from(m2csv.convert(raw).decode("utf-8-sig"))


class TestRowCoercion(unittest.TestCase):
    def test_row_has_every_field_in_order(self):
        rows = convert_rows([make_memory()])
        self.assertEqual(
            rows[0], ["id", "content", "category", "tags", "visibility", "created_at", "updated_at", "app_id"]
        )
        self.assertEqual(
            rows[1],
            [
                "mem-1",
                "Prefers morning deep work",
                "habits",
                "focus|q4",
                "private",
                "2026-09-30T10:00:00+00:00",
                "2026-09-30T11:00:00+00:00",
                "app-1",
            ],
        )

    def test_missing_fields_render_empty_cells(self):
        rows = convert_rows([{"id": "m", "content": "c"}])
        self.assertEqual(rows[1], ["m", "c", "", "", "", "", "", ""])

    def test_non_dict_rows_are_skipped(self):
        rows = convert_rows([make_memory(), "junk", 42, None])
        self.assertEqual(len(rows), 2)

    def test_non_string_content_is_json_coerced(self):
        rows = convert_rows([{"id": "m", "content": {"a": 1}}])
        self.assertEqual(rows[1][1], '{"a": 1}')

    def test_numeric_id_is_coerced_to_string(self):
        rows = convert_rows([{"id": 123, "content": "c"}])
        self.assertEqual(rows[1][0], "123")

    def test_source_app_fallback_for_app_id(self):
        rows = convert_rows([{"id": "m", "content": "c", "source_app": "plugin"}])
        self.assertEqual(rows[1][7], "plugin")


class TestFormulaInjectionGuard(unittest.TestCase):
    def test_equals_prefix_is_neutralized(self):
        rows = convert_rows([{"id": "m", "content": "=cmd|calc!A0"}])
        self.assertEqual(rows[1][1], "'=cmd|calc!A0")

    def test_plus_minus_at_prefixes_are_neutralized(self):
        for dangerous in ("+1", "-2", "@SUM(A1)"):
            with self.subTest(dangerous=dangerous):
                rows = convert_rows([{"id": "m", "content": dangerous}])
                self.assertEqual(rows[1][1], "'" + dangerous)

    def test_leading_whitespace_then_formula_is_still_neutralized(self):
        rows = convert_rows([{"id": "m", "content": "  =danger"}])
        self.assertTrue(rows[1][1].startswith("'"))

    def test_leading_tab_is_neutralized(self):
        rows = convert_rows([{"id": "m", "content": "\tdanger"}])
        self.assertEqual(rows[1][1], "'\tdanger")

    def test_normal_text_is_not_touched(self):
        rows = convert_rows([{"id": "m", "content": "minus two is -2 inside"}])
        self.assertEqual(rows[1][1], "minus two is -2 inside")


class TestTagsAndTimestamps(unittest.TestCase):
    def test_tags_are_pipe_joined(self):
        rows = convert_rows([{"id": "m", "content": "c", "tags": ["a", "b c", "d"]}])
        self.assertEqual(rows[1][3], "a|b c|d")

    def test_tags_string_passes_through(self):
        rows = convert_rows([{"id": "m", "content": "c", "tags": "solo"}])
        self.assertEqual(rows[1][3], "solo")

    def test_tags_none_and_garbage_render_empty(self):
        rows = convert_rows([{"id": "m", "content": "c", "tags": None}, {"id": "n", "content": "c", "tags": 7}])
        self.assertEqual(rows[1][3], "")
        self.assertEqual(rows[2][3], "")

    def test_z_timestamps_are_normalized_to_utc_iso(self):
        rows = convert_rows([make_memory(created_at="2026-09-30T12:30:00+02:00")])
        self.assertEqual(rows[1][5], "2026-09-30T10:30:00+00:00")

    def test_naive_timestamp_becomes_utc(self):
        rows = convert_rows([make_memory(created_at="2026-09-30T10:00:00")])
        self.assertEqual(rows[1][5], "2026-09-30T10:00:00+00:00")

    def test_unusable_timestamp_is_kept_raw_not_crashing(self):
        rows = convert_rows([make_memory(created_at="soon", updated_at=None)])
        self.assertEqual(rows[1][5], "soon")
        self.assertEqual(rows[1][6], "")

    def test_datetime_objects_are_accepted(self):
        from datetime import datetime, timezone

        # In-process callers may hand a real datetime straight to memory_row.
        row = m2csv.memory_row(make_memory(created_at=datetime(2026, 9, 30, 10, tzinfo=timezone.utc)))
        self.assertEqual(row[5], "2026-09-30T10:00:00+00:00")


class TestEnvelopeUnwrapping(unittest.TestCase):
    def test_bare_array(self):
        rows = convert_rows([make_memory()])
        self.assertEqual(len(rows), 2)

    def test_memories_envelope(self):
        rows = convert_rows({"memories": [make_memory()]})
        self.assertEqual(len(rows), 2)

    def test_items_envelope(self):
        rows = convert_rows({"items": [make_memory()]})
        self.assertEqual(len(rows), 2)

    def test_data_envelope(self):
        rows = convert_rows({"data": [make_memory()]})
        self.assertEqual(len(rows), 2)

    def test_single_object(self):
        rows = convert_rows({"id": "m", "content": "c", "category": "work"})
        self.assertEqual(len(rows), 2)

    def test_error_payload_yields_header_only(self):
        rows = convert_rows({"detail": "Not authenticated"})
        self.assertEqual(len(rows), 1)

    def test_scalar_input_raises_value_error(self):
        with self.assertRaises(ValueError):
            m2csv.convert('"just a string"')

    def test_invalid_json_raises_json_decode_error(self):
        with self.assertRaises(json.JSONDecodeError):
            m2csv.convert("{nope")


class TestFilters(unittest.TestCase):
    def test_category_filter_keeps_matching_rows(self):
        rows = convert_rows([make_memory(category="work"), make_memory(category="other")])
        # unfiltered: both rows
        self.assertEqual(len(rows), 3)

    def test_convert_filtered_category(self):
        raw = json.dumps([make_memory(category="work"), make_memory(category="other")])
        rows = rows_from(m2csv.convert_filtered(raw, category="work").decode("utf-8-sig"))
        self.assertEqual([r[0] for r in rows[1:]], ["mem-1"])

    def test_convert_filtered_category_is_case_insensitive(self):
        raw = json.dumps([make_memory(category="Work"), make_memory(category="other")])
        rows = rows_from(m2csv.convert_filtered(raw, category="work").decode("utf-8-sig"))
        self.assertEqual([r[0] for r in rows[1:]], ["mem-1"])

    def test_convert_filtered_visibility(self):
        raw = json.dumps([make_memory(visibility="private"), make_memory(visibility="public")])
        rows = rows_from(m2csv.convert_filtered(raw, visibility="private").decode("utf-8-sig"))
        self.assertEqual([r[0] for r in rows[1:]], ["mem-1"])

    def test_convert_filtered_ignores_invalid_visibility_choice(self):
        raw = json.dumps([make_memory(visibility="private")])
        rows = rows_from(m2csv.convert_filtered(raw, visibility="INTERNAL_ONLY").decode("utf-8-sig"))
        self.assertEqual([r[0] for r in rows[1:]], ["mem-1"])

    def test_filter_with_non_dict_rows_does_not_crash(self):
        raw = json.dumps([make_memory(category="work"), "junk", 42])
        rows = rows_from(m2csv.convert_filtered(raw, category="work").decode("utf-8-sig"))
        self.assertEqual([r[0] for r in rows[1:]], ["mem-1"])


class TestOutputBytes(unittest.TestCase):
    def test_output_starts_with_utf8_bom(self):
        payload = m2csv.convert(json.dumps([make_memory()]))
        self.assertTrue(payload.startswith(b"\xef\xbb\xbf"))

    def test_multiline_content_is_quoted_not_broken(self):
        payload = m2csv.convert(json.dumps([make_memory(content="line one\nline two")])).decode("utf-8-sig")
        rows = rows_from(payload)
        self.assertEqual(rows[1][1], "line one\nline two")

    def test_comma_content_is_quoted(self):
        payload = m2csv.convert(json.dumps([make_memory(content="a,b")])).decode("utf-8-sig")
        rows = rows_from(payload)
        self.assertEqual(rows[1][1], "a,b")

    def test_unicode_survives_round_trip(self):
        payload = m2csv.convert(json.dumps([make_memory(content="Nhớ uống cà phê ☕")])).decode("utf-8-sig")
        self.assertIn("Nhớ uống cà phê ☕", payload)

    def test_deterministic_bytes(self):
        raw = json.dumps([make_memory()])
        self.assertEqual(m2csv.convert(raw), m2csv.convert(raw))

    def test_empty_selection_renders_header_only(self):
        rows = convert_rows([])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "id")


class TestCliExitCodes(unittest.TestCase):
    @staticmethod
    def run_cli(*cli_args, stdin_bytes=None):
        return subprocess.run(
            [sys.executable, str(EXAMPLE_SCRIPT), *cli_args],
            input=stdin_bytes,
            capture_output=True,
            timeout=60,
        )

    def test_file_input_output_exits_zero_and_writes_bom(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_memory()]), encoding="utf-8")
            out = Path(td) / "m.csv"
            result = self.run_cli(str(src), "-o", str(out))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertTrue(out.read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_stdin_pipe_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "m.csv"
            result = self.run_cli("-", "-o", str(out), stdin_bytes=json.dumps([make_memory()]).encode("utf-8"))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertTrue(out.exists())

    def test_existing_output_refuses_overwrite_and_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_memory()]), encoding="utf-8")
            out = Path(td) / "m.csv"
            out.write_bytes(b"keep me")
            result = self.run_cli(str(src), "-o", str(out))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"already exists", result.stderr)
            self.assertEqual(out.read_bytes(), b"keep me")

    def test_missing_input_file_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            result = self.run_cli(str(Path(td) / "nope.json"), "-o", str(Path(td) / "m.csv"))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"does not exist", result.stderr)

    def test_empty_payload_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text("   ", encoding="utf-8")
            result = self.run_cli(str(src), "-o", str(Path(td) / "m.csv"))
            self.assertEqual(result.returncode, 1)

    def test_invalid_json_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "bad.json"
            src.write_text("{nope", encoding="utf-8")
            result = self.run_cli(str(src), "-o", str(Path(td) / "m.csv"))
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"Invalid JSON", result.stderr)

    def test_scalar_payload_exits_one(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text("42", encoding="utf-8")
            result = self.run_cli(str(src), "-o", str(Path(td) / "m.csv"))
            self.assertEqual(result.returncode, 1)

    def test_category_filter_flag_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_memory(category="work")]), encoding="utf-8")
            out = Path(td) / "m.csv"
            result = self.run_cli(str(src), "--category", "work", "-o", str(out))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertIn(b"work", out.read_bytes())

    def test_visibility_filter_flag_exits_zero(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_memory(visibility="public")]), encoding="utf-8")
            out = Path(td) / "m.csv"
            result = self.run_cli(str(src), "--visibility", "public", "-o", str(out))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertIn(b"public", out.read_bytes())

    def test_no_output_flag_prints_csv_to_stdout(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([make_memory()]), encoding="utf-8")
            result = self.run_cli(str(src))
            self.assertEqual(result.returncode, 0)
            self.assertTrue(result.stdout.startswith(b"\xef\xbb\xbf"))

    def test_bom_prefixed_input_is_tolerated(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_bytes(b"\xef\xbb\xbf" + json.dumps([make_memory()]).encode("utf-8"))
            out = Path(td) / "m.csv"
            result = self.run_cli(str(src), "-o", str(out))
            self.assertEqual(result.returncode, 0, result.stderr.decode("utf-8", "replace"))
            self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
