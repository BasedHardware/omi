"""Hermetic tests for examples/memories_to_xlsx.py (#18985).

Covers: native datetime/boolean cells, | -joined tags, formula-safe string
typing, multi-file dedupe, atomic partial-write, overwrite refusal.
Requires openpyxl.
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
    import memories_to_xlsx as m  # noqa: E402


MEM = {
    "id": "m1",
    "content": "Prefers short standups",
    "category": "Work",
    "tags": ["style", "meetings"],
    "visibility": "public",
    "manually_added": True,
    "reviewed": False,
    "app_id": "chatgpt",
    "created_at": "2026-10-17T12:00:00+02:00",
    "updated_at": "2026-10-17T13:00:00Z",
}


@unittest.skipUnless(HAVE_XLSX, "openpyxl not installed")
class TestCells(unittest.TestCase):
    def test_datetime_to_naive_utc(self):
        dt = m.cell_datetime("2026-10-17T12:00:00+02:00")
        self.assertIsInstance(dt, datetime)
        self.assertIsNone(dt.tzinfo)
        self.assertEqual(dt.hour, 10)

    def test_native_booleans(self):
        self.assertIs(m.cell_bool(True), True)
        self.assertIs(m.cell_bool("yes"), True)
        self.assertIsNone(m.cell_bool("maybe"))

    def test_tags_joined(self):
        self.assertEqual(m.cell_tags(["a", "b"]), "a|b")
        self.assertEqual(m.cell_tags("solo"), "solo")


@unittest.skipUnless(HAVE_XLSX, "openpyxl not installed")
class TestConvert(unittest.TestCase):
    def test_workbook_shape(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            dst = str(Path(td) / "out.xlsx")
            n = m.convert([str(src)], dst)
            self.assertEqual(n, 1)
            wb = openpyxl.load_workbook(dst)
            ws = wb.active
            self.assertEqual(ws.title, "memories")
            self.assertTrue(ws.freeze_panes == "A2")
            row = [c.value for c in ws[2]]
            self.assertIs(row[5], True)  # manually_added
            self.assertIs(row[6], False)  # reviewed
            self.assertIsInstance(row[8], datetime)
            self.assertIsNone(row[8].tzinfo)

    def test_formula_safe_string(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps({"memories": [{**MEM, "content": "=SUM(A1)"}]}))
            dst = str(Path(td) / "out.xlsx")
            m.convert([str(src)], dst)
            wb = openpyxl.load_workbook(dst)
            cell = wb.active.cell(row=2, column=2)
            self.assertEqual(cell.data_type, "s")
            self.assertEqual(cell.value, "=SUM(A1)")

    def test_multi_page_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = Path(td) / "p1.json"
            p1.write_text(json.dumps({"memories": [MEM, {**MEM, "id": "m2"}]}))
            p2 = Path(td) / "p2.json"
            p2.write_text(json.dumps({"memories": [MEM]}))
            n = m.convert([str(p1), str(p2)], str(Path(td) / "o.xlsx"))
            self.assertEqual(n, 2)

    def test_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([MEM]))
            out = Path(td) / "o.xlsx"
            out.write_text("keep")
            with self.assertRaises(FileExistsError):
                m.convert([str(src)], str(out))
            self.assertEqual(out.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "in.json"
            src.write_text(json.dumps([MEM]))
            with self.assertRaises(ValueError):
                m.convert([str(src)], "../escape.xlsx")


if __name__ == "__main__":
    unittest.main()
