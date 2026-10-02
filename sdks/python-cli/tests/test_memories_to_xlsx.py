import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from openpyxl import load_workbook

from memories_to_xlsx import (
    boolean_flag,
    load,
    safe_string,
    utc_stamp,
    validate_xlsx_path,
    write_workbook,
)


def _sample_memories():
    return [
        {
            "id": "mem-1",
            "content": "Prefers dark mode",
            "category": "preferences",
            "created_at": "2026-09-20T10:30:00Z",
            "updated_at": "2026-09-21T12:30:00+02:00",
            "manually_added": True,
            "reviewed": False,
            "source": "conversation",
        },
        {
            "id": "mem-2",
            "content": "=1+1",
            "category": "system",
            "created_at": "not-a-date",
            "updated_at": None,
            "manually_added": "yes",
            "reviewed": "no",
            "source": None,
        },
    ]


class TestHelpers(unittest.TestCase):
    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T10:30:00Z"), dt.datetime(2026, 9, 20, 10, 30))
        self.assertEqual(utc_stamp("2026-09-20T12:30:00+02:00"), dt.datetime(2026, 9, 20, 10, 30))
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp("invalid-date"))

    def test_boolean_flag_coercion(self):
        self.assertTrue(boolean_flag(True))
        self.assertFalse(boolean_flag(False))
        self.assertTrue(boolean_flag("yes"))
        self.assertFalse(boolean_flag("no"))
        self.assertIsNone(boolean_flag(None))
        self.assertIsNone(boolean_flag("maybe"))

    def test_safe_string_neutralizes_formulas(self):
        self.assertEqual(safe_string("=1+1"), "'=1+1")
        self.assertEqual(safe_string("+SUM(A1)"), "'+SUM(A1)")
        self.assertEqual(safe_string("@import"), "'@import")
        self.assertEqual(safe_string("-2+3"), "'-2+3")
        self.assertEqual(safe_string("plain text"), "plain text")
        self.assertIsNone(safe_string(None))

    def test_load_accepts_multiple_shapes(self):
        self.assertEqual(len(load({"memories": _sample_memories()})), 2)
        self.assertEqual(len(load({"items": _sample_memories()})), 2)
        self.assertEqual(len(load(_sample_memories())), 2)
        self.assertEqual(len(load([])), 0)
        self.assertEqual(len(load({"unrelated": 5})), 1)


class TestPathValidation(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_traversal(self):
        with self.assertRaises(ValueError):
            validate_xlsx_path(str(self.dir_path / ".." / "escape.xlsx"))

    def test_rejects_non_xlsx_existing_file(self):
        target = self.dir_path / "notes.txt"
        target.write_text("hello", encoding="utf-8")
        with self.assertRaises(ValueError):
            validate_xlsx_path(str(target))

    def test_accepts_existing_xlsx(self):
        target = self.dir_path / "existing.xlsx"
        write_workbook(_sample_memories(), str(target))
        validate_xlsx_path(str(target))  # must not raise


class TestWorkbookOutput(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.out_path = self.dir_path / "memories.xlsx"

    def tearDown(self):
        self.temp_dir.cleanup()

    def _reload(self):
        return load_workbook(self.out_path)

    def test_writes_rows_and_returns_count(self):
        count = write_workbook(_sample_memories(), str(self.out_path))
        self.assertEqual(count, 2)
        self.assertTrue(self.out_path.exists())

    def test_header_row_and_freeze(self):
        write_workbook(_sample_memories(), str(self.out_path))
        wb = self._reload()
        sheet = wb["memories"]
        self.assertEqual(sheet["A1"].value, "id")
        self.assertEqual(sheet["B1"].value, "content")
        self.assertEqual(sheet.freeze_panes, "A2")

    def test_datetime_cells_are_real_datetimes(self):
        write_workbook(_sample_memories(), str(self.out_path))
        sheet = self._reload()["memories"]
        self.assertIsInstance(sheet["D2"].value, dt.datetime)
        self.assertEqual(sheet["D2"].value, dt.datetime(2026, 9, 20, 10, 30))
        # Invalid timestamps stay empty instead of writing a wrong date.
        self.assertIsNone(sheet["D3"].value)

    def test_boolean_cells_are_real_booleans(self):
        write_workbook(_sample_memories(), str(self.out_path))
        sheet = self._reload()["memories"]
        self.assertIs(sheet["F2"].value, True)
        self.assertIs(sheet["G2"].value, False)
        # String flags are coerced to booleans too.
        self.assertIs(sheet["F3"].value, True)
        self.assertIs(sheet["G3"].value, False)

    def test_formula_injection_is_neutralized(self):
        write_workbook(_sample_memories(), str(self.out_path))
        sheet = self._reload()["memories"]
        cell = sheet["B3"]
        self.assertEqual(cell.data_type, "s")
        self.assertEqual(cell.value, "'=1+1")
        self.assertNotEqual(cell.value, "=1+1")

    def test_autofilter_and_widths(self):
        write_workbook(_sample_memories(), str(self.out_path))
        sheet = self._reload()["memories"]
        self.assertEqual(sheet.auto_filter.ref, "A1:H3")
        self.assertEqual(sheet.column_dimensions["B"].width, 60)

    def test_empty_export_still_writes_header(self):
        write_workbook([], str(self.out_path))
        sheet = self._reload()["memories"]
        self.assertEqual(sheet["A1"].value, "id")
        self.assertIsNone(sheet["A2"].value)
        self.assertIsNone(sheet.auto_filter.ref)

    def test_atomic_write_leaves_no_partial_file(self):
        write_workbook(_sample_memories(), str(self.out_path))
        self.assertFalse(Path(str(self.out_path) + ".partial").exists())

    def test_roundtrip_json_export_shape(self):
        payload = json.loads(json.dumps({"memories": _sample_memories()}))
        write_workbook(load(payload), str(self.out_path))
        sheet = self._reload()["memories"]
        self.assertEqual(sheet["A2"].value, "mem-1")


if __name__ == "__main__":
    unittest.main()