"""Hermetic tests for examples/memories_to_csv.py (#20285).

Covers: row coercion, spreadsheet formula guard, tags/timestamps, envelope
unwrapping + BOM, --category/--visibility filters, deterministic bytes, and
CLI exit codes.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import memories_to_csv as m  # noqa: E402

MEM = {
    "id": "m1",
    "content": "Prefers short standups",
    "category": "Work",
    "tags": ["style", "meetings"],
    "visibility": "public",
    "created_at": "2026-10-17T12:00:00+02:00",
    "updated_at": "2026-10-17T13:00:00Z",
    "app_id": "chatgpt",
}


class TestRowCoercion(unittest.TestCase):
    def test_columns_are_fixed_order(self):
        row = m.normalize_row(MEM)
        self.assertEqual(len(row), len(m.FIELDS))
        self.assertEqual(row[0], "m1")
        self.assertEqual(row[1], "Prefers short standups")
        self.assertEqual(row[2], "Work")

    def test_memory_id_and_source_app_fallbacks(self):
        row = m.normalize_row({"memory_id": "m9", "source_app": "cli"})
        self.assertEqual(row[0], "m9")
        self.assertEqual(row[7], "cli")

    def test_missing_fields_become_empty(self):
        row = m.normalize_row({"id": "x"})
        self.assertEqual(row[1:], ["", "", "", "", "", "", ""])

    def test_non_dict_row_dropped(self):
        self.assertIsNone(m.normalize_row(42))
        self.assertIsNone(m.normalize_row("odd"))


class TestFormulaGuard(unittest.TestCase):
    def test_formula_prefixes_get_apostrophe(self):
        for payload in ("=SUM(1)", "+cmd", "-1", "@x", "\tcell"):
            self.assertTrue(m.spreadsheet_text(payload).startswith("'"))

    def test_safe_text_untouched(self):
        self.assertEqual(m.spreadsheet_text("normal"), "normal")

    def test_non_string_coerced(self):
        self.assertEqual(m.spreadsheet_text(42), "42")
        self.assertEqual(m.spreadsheet_text({"a": 1}), '{"a": 1}')


class TestTagsTimestamps(unittest.TestCase):
    def test_tags_pipe_joined(self):
        row = m.normalize_row(MEM)
        self.assertEqual(row[3], "style|meetings")

    def test_scalar_tag_coerces(self):
        row = m.normalize_row({"tags": "solo"})
        self.assertEqual(row[3], "solo")

    def test_timestamps_to_utc(self):
        row = m.normalize_row(MEM)
        self.assertEqual(row[5], "2026-10-17T10:00:00Z")
        self.assertEqual(row[6], "2026-10-17T13:00:00Z")

    def test_overflow_timestamp_keeps_raw(self):
        row = m.normalize_row({"created_at": "9999-12-31T23:59:59.999999+99:99"})
        self.assertIn("9999-12-31", row[5])


class TestEnvelope(unittest.TestCase):
    def test_bare_list_and_envelopes(self):
        self.assertEqual(m.unwrap([MEM]), [MEM])
        for key in ("memories", "items", "data"):
            self.assertEqual(m.unwrap({key: [MEM]}), [MEM])

    def test_single_object(self):
        self.assertEqual(m.unwrap(MEM), [MEM])

    def test_error_payload_empty(self):
        self.assertEqual(m.unwrap({"error": "nope"}), [])


class TestFilters(unittest.TestCase):
    def test_category_case_insensitive(self):
        rows = m.convert({"memories": [MEM, {"id": "x", "category": "Personal"}]}, {"work"}, None)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "m1")

    def test_visibility_filter(self):
        rows = m.convert({"memories": [MEM, {"id": "x", "visibility": "private"}]}, None, {"private"})
        self.assertEqual(rows[0][0], "x")

    def test_no_filter_keeps_all(self):
        rows = m.convert({"memories": [MEM, {"id": "x"}]}, None, None)
        self.assertEqual(len(rows), 2)

    def test_filter_on_missing_field_skips(self):
        rows = m.convert({"memories": [MEM]}, {"zzz"}, None)
        self.assertEqual(rows, [])


class TestCsvBytes(unittest.TestCase):
    def test_utf8_bom_and_header(self):
        blob = m.emit_csv([["a", "b", "c", "d", "e", "f", "g", "h"]])
        self.assertTrue(blob.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b"id,content,category,tags,visibility,created_at,updated_at,app_id", blob)

    def test_deterministic_output(self):
        a = m.emit_csv([m.normalize_row(MEM)])
        b = m.emit_csv([m.normalize_row(MEM)])
        self.assertEqual(a, b)

    def test_crlf_terminator(self):
        self.assertIn(b"\r\n", m.emit_csv([["1"] * 8]))


class TestCli(unittest.TestCase):
    def _run(self, stdin_bytes, argv):
        buf, err = io.BytesIO(), io.StringIO()
        old = sys.stdin, sys.stdout, sys.stderr

        class _In:
            buffer = io.BytesIO(stdin_bytes)

        class _Out:
            def __init__(self, b):
                self.buffer = b

            def write(self, s):
                return self.buffer.write(s)

            def flush(self):
                pass

        sys.stdin, sys.stdout, sys.stderr = _In(), _Out(buf), err
        try:
            rc = m.main(argv)
        finally:
            sys.stdin, sys.stdout, sys.stderr = old[0], old[1], old[2]
        return rc, buf.getvalue(), err.getvalue()

    def test_stdin_to_stdout(self):
        rc, out, _ = self._run(json.dumps({"memories": [MEM]}).encode(), ["-"])
        self.assertEqual(rc, 0)
        self.assertIn(b"Prefers short standups", out)

    def test_invalid_json_exit_2(self):
        rc, _, err = self._run(b"{bad json", ["-"])
        self.assertEqual(rc, 2)
        self.assertIn("invalid JSON", err)

    def test_exclusive_output_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "m.csv"
            out.write_text("keep")
            rc, _, err = self._run(b"[]", ["-", "-o", str(out)])
            self.assertEqual(rc, 2)
            self.assertEqual(out.read_text(), "keep")

    def test_output_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "m.csv"
            rc, _, _ = self._run(json.dumps({"memories": [MEM]}).encode(), ["-", "-o", str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(out.read_bytes().startswith(b'\xef\xbb\xbf'))


if __name__ == "__main__":
    unittest.main()
