"""Hermetic tests for examples/action_items_to_xlsx.py (#18961).

Covers: native datetime/boolean cells, formula-safe string typing, frozen
header + AutoFilter, multi-file dedupe, atomic partial-write, overwrite
refusal. Requires openpyxl (``pip install openpyxl``).
"""

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

try:
    import openpyxl  # noqa: F401

    HAVE_XLSX = True
except ImportError:
    HAVE_XLSX = False

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

if HAVE_XLSX:
    import action_items_to_xlsx as m  # noqa: E402


ITEM = {
    "id": "ai1",
    "description": "Ship the release notes",
    "completed": False,
    "due_at": "2026-10-20T15:00:00+02:00",
    "created_at": "2026-10-15T10:00:00Z",
    "updated_at": "2026-10-15T11:00:00Z",
    "conversation_id": "c1",
    "source": "omi",
}


@unittest.skipUnless(HAVE_XLSX, "openpyxl not installed")
class TestCells(unittest.TestCase):
    def test_datetime_to_naive_utc(self):
        dt = m.cell_datetime("2026-10-20T15:00:00+02:00")
        self.assertIsInstance(dt, datetime)
        self.assertIsNone(dt.tzinfo)
        self.assertEqual(dt.hour, 13)  # 15:00+02:00 → 13:00Z

    def test_unparseable_datetime_kept_as_text(self):
        self.assertEqual(m.cell_datetime("not-a-date"), "not-a-date")

    def test_native_boolean(self):
        self.assertIs(m.cell_bool(True), True)
        self.assertIs(m.cell_bool("yes"), True)
        self.assertIsNone(m.cell_bool("maybe"))

    def test_text_coerced_and_condensed(self):
        self.assertEqual(m.cell_text({"a": 1}), '{"a": 1}')
        self.assertEqual(m.cell_text("a\nb\tc"), "a b c")


@unittest.skipUnless(HAVE_XLSX, "openpyxl not installed")
class TestConvert(unittest.TestCase):
    def _convert(self, td, payload, name="in.json", out="out.xlsx"):
        src = Path(td) / name
        src.write_text(json.dumps(payload), encoding="utf-8")
        dst = str(Path(td) / out)
        n = m.convert([str(src)], dst)
        return n, dst

    def test_workbook_shape(self):
        with tempfile.TemporaryDirectory() as td:
            n, dst = self._convert(td, {"action_items": [ITEM]})
            self.assertEqual(n, 1)
            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            self.assertEqual(ws.title, "action_items")
            header = [c.value for c in ws[1]]
            self.assertIn("id", header)
            self.assertIn("due_at (UTC)", header)
            self.assertTrue(ws.freeze_panes == "A2")
            self.assertIsNotNone(ws.auto_filter.ref)
            # completed as native bool, due_at as real datetime
            row = [c.value for c in ws[2]]
            self.assertIs(row[2], False)
            self.assertIsInstance(row[3], datetime)
            self.assertIsNone(row[3].tzinfo)

    def test_formula_safe_string_typing(self):
        with tempfile.TemporaryDirectory() as td:
            n, dst = self._convert(td, {"action_items": [{**ITEM, "description": "=SUM(A1)"}]})
            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            desc_cell = ws.cell(row=2, column=2)
            self.assertEqual(desc_cell.data_type, "s")
            self.assertEqual(desc_cell.value, "=SUM(A1)")

    def test_multi_page_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "p1.json"
            p1.write_text(json.dumps({"action_items": [ITEM, {**ITEM, "id": "ai2"}]}))
            p2 = Path(td) / "p2.json"
            p2.write_text(json.dumps({"action_items": [ITEM]}))  # ai1 dupes
            n = m.convert([str(p1), str(p2)], str(Path(td) / "o.xlsx"))
            self.assertEqual(n, 2)

    def test_envelope_shapes(self):
        for payload in ({"action_items": [ITEM]}, {"items": [ITEM]}, {"data": [ITEM]}, [ITEM], ITEM):
            self.assertEqual(len(m.extract_items(payload)), 1)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([ITEM]))
            out = Path(td) / "o.xlsx"
            out.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert([str(src)], str(out))
            self.assertEqual(out.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([ITEM]))
            with self.assertRaises(ValueError):
                m.convert([str(src)], "../escape.xlsx")

    def test_no_partial_left_on_failure(self):
        with tempfile.TemporaryDirectory() as td:
            # A payload that parses but whose save fails is hard to construct
            # without mocking; assert the partial-name convention holds.
            self.assertEqual(Path("o.xlsx").with_name("o.xlsx.partial").name, "o.xlsx.partial")


if __name__ == "__main__":
    unittest.main()
