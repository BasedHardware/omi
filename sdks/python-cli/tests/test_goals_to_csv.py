"""Hermetic tests for examples/goals_to_csv.py (#19371).

Covers: progress_pct calculation, formula-injection guard, envelope
unwrapping, --type/--status filters, and CLI output paths.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import goals_to_csv as m  # noqa: E402

GOAL = {
    "id": "g1",
    "title": "Drink water",
    "category": "health",
    "goal_type": "numeric",
    "current_value": 1.0,
    "target_value": 4.0,
    "unit": "liters",
    "is_active": True,
    "created_at": "2026-10-17T12:00:00+02:00",
}


class TestRow(unittest.TestCase):
    def test_fixed_columns(self):
        row = m.normalize_row(GOAL)
        self.assertEqual(len(row), len(m.FIELDS))
        self.assertEqual(row[0], "g1")
        self.assertEqual(row[6], "25.0")  # progress_pct: 1/4
        self.assertEqual(row[7], "1")  # is_active

    def test_inactive_flag(self):
        self.assertEqual(m.normalize_row({**GOAL, "is_active": False})[7], "0")

    def test_qualitative_no_pct(self):
        row = m.normalize_row({"id": "g", "title": "be kind", "goal_type": None})
        self.assertEqual(row[6], "")

    def test_zero_target_no_divide(self):
        row = m.normalize_row({"id": "g", "current_value": 1, "target_value": 0})
        self.assertEqual(row[6], "")

    def test_formula_guard(self):
        row = m.normalize_row({"id": "g", "title": "=SUM(1,2)"})
        self.assertTrue(row[1].startswith("'"))

    def test_non_dict_dropped(self):
        self.assertIsNone(m.normalize_row(42))


class TestFilters(unittest.TestCase):
    def test_type_filter(self):
        rows = m.convert({"goals": [GOAL, {"id": "x", "goal_type": "scale"}]}, {"numeric"}, None)
        self.assertEqual(len(rows), 1)

    def test_status_filter(self):
        rows = m.convert({"goals": [GOAL, {"id": "x", "is_active": False}]}, None, {"inactive"})
        self.assertEqual(rows[0][0], "x")

    def test_qualitative_type_matches(self):
        rows = m.convert({"goals": [{"id": "g", "goal_type": None}]}, {"qualitative"}, None)
        self.assertEqual(len(rows), 1)


class TestEnvelope(unittest.TestCase):
    def test_unwrap_shapes(self):
        for payload in ({"goals": [GOAL]}, {"items": [GOAL]}, {"data": [GOAL]}, [GOAL], GOAL):
            self.assertEqual(len(m.convert(payload, None, None)), 1)
        self.assertEqual(m.convert({"error": "no"}, None, None), [])


class TestOutput(unittest.TestCase):
    def test_bom_header_crlf(self):
        blob = m.emit_csv([m.normalize_row(GOAL)])
        self.assertTrue(blob.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b"id,title,goal_type", blob)
        self.assertIn(b"\r\n", blob)

    def test_exclusive_write(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "g.csv"
            out.write_text("keep")

            class _In:
                buffer = io.BytesIO(b"[]")

            buf, err = io.BytesIO(), io.StringIO()
            old = sys.stdin, sys.stdout, sys.stderr

            class _Out:
                buffer = buf

                def write(self, s):
                    return self.buffer.write(s)

                def flush(self):
                    pass

            sys.stdin, sys.stdout, sys.stderr = _In(), _Out(), err
            try:
                rc = m.main(["-", "-o", str(out)])
            finally:
                sys.stdin, sys.stdout, sys.stderr = old
            self.assertEqual(rc, 2)
            self.assertEqual(out.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
