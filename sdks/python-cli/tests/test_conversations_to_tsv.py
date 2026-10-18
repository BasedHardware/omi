"""Hermetic tests for examples/conversations_to_tsv.py (#19310).

Covers: empty-array handling, envelope extraction, path-traversal refusal,
multi-line escaping (strictly 1 line per record), and CLI execution.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import conversations_to_tsv as m  # noqa: E402

CONV = {
    "id": "c1",
    "title": "Multi-line\nsummary\ttabbed",
    "category": "Work",
    "started_at": "2026-10-17T10:00:00Z",
    "finished_at": "2026-10-17T11:00:00Z",
    "source": "omi",
    "overview": "line1\r\nline2",
    "action_items": [{"description": "a"}, {"description": "b"}],
}


class TestTsvEscaping(unittest.TestCase):
    def test_newlines_and_tabs_escaped(self):
        row = m.normalize_row(CONV)
        self.assertNotIn("\n", row[1])
        self.assertNotIn("\t", row[1])
        self.assertIn("\\n", row[1])
        self.assertIn("\\t", row[1])

    def test_backslash_escaped_first(self):
        self.assertEqual(m.tsv_cell("a\\b\nc"), "a\\\\b\\nc")

    def test_one_line_per_record(self):
        out = m.emit_tsv([m.normalize_row(CONV), m.normalize_row({"id": "x"})])
        # header + 2 rows, regardless of embedded newlines in fields
        self.assertEqual(len(out.strip().split("\n")), 3)


class TestEnvelope(unittest.TestCase):
    def test_bare_list_and_envelopes(self):
        self.assertEqual(m.unwrap([CONV]), [CONV])
        for key in ("conversations", "items", "data", "results"):
            self.assertEqual(m.unwrap({key: [CONV]}), [CONV])

    def test_single_object_and_error(self):
        self.assertEqual(m.unwrap(CONV), [CONV])
        self.assertEqual(m.unwrap({"error": "nope"}), [])


class TestConvert(unittest.TestCase):
    def test_empty_array(self):
        self.assertEqual(m.convert([]), [])
        self.assertEqual(m.convert({"conversations": []}), [])

    def test_action_items_count(self):
        row = m.normalize_row(CONV)
        self.assertEqual(row[7], "2")

    def test_non_dict_dropped(self):
        self.assertEqual(len(m.convert({"conversations": [CONV, 42]})), 1)

    def test_structured_fallback(self):
        row = m.normalize_row({"id": "x", "structured": {"title": "st", "category": "sc", "overview": "so"}})
        self.assertEqual(row[1], "st")
        self.assertEqual(row[6], "so")


class TestCli(unittest.TestCase):
    def _run(self, stdin_text, argv):
        buf, err = io.StringIO(), io.StringIO()
        old = sys.stdin, sys.stdout, sys.stderr
        sys.stdin, sys.stdout, sys.stderr = io.StringIO(stdin_text), buf, err
        try:
            rc = m.main(argv)
        finally:
            sys.stdin, sys.stdout, sys.stderr = old
        return rc, buf.getvalue(), err.getvalue()

    def test_stdin_to_stdout(self):
        rc, out, _ = self._run(json.dumps({"conversations": [CONV]}), ["-"])
        self.assertEqual(rc, 0)
        self.assertIn("id\ttitle\tcategory", out)
        self.assertEqual(len(out.strip().split("\n")), 2)

    def test_invalid_json_exit_2(self):
        rc, _, err = self._run("{bad", ["-"])
        self.assertEqual(rc, 2)
        self.assertIn("invalid JSON", err)

    def test_path_traversal_refused(self):
        rc, _, err = self._run("[]", ["-", "-o", "../escape.tsv"])
        self.assertEqual(rc, 2)
        self.assertIn("..", err)

    def test_missing_input_exit_2(self):
        buf, err = io.StringIO(), io.StringIO()
        old = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = buf, err
        try:
            rc = m.main(["/nonexistent.json"])
        finally:
            sys.stdout, sys.stderr = old
        self.assertEqual(rc, 2)

    def test_output_writes_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "c.tsv"
            rc, _, _ = self._run(json.dumps({"conversations": [CONV]}), ["-", "-o", str(out)])
            self.assertEqual(rc, 0)
            self.assertEqual(len(out.read_text().strip().split("\n")), 2)


if __name__ == "__main__":
    unittest.main()
