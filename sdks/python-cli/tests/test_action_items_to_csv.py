"""Tests for action items to CSV exporter.

Pins CSV column order, formula injection guards, timezone offsets,
status filtering, completion coercion, envelope unwrapping,
idempotent deduplication, stdin streaming, and atomic overwrite safety.
"""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

# Load action_items_to_csv dynamically so PYTHONPATH does not require examples/
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_csv.py"
spec = importlib.util.spec_from_file_location("action_items_to_csv", script_path)
ai2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2csv)


class TestActionItemsToCsv(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.sample_items = [
            {
                "id": "act_01_review",
                "description": "Review API endpoints for export",
                "completed": False,
                "due_at": "2026-10-01T15:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-21T11:00:00Z",
                "conversation_id": "conv_101",
            },
            {
                "id": "act_02_kicad",
                "description": "Fix PCB trace impedance",
                "completed": True,
                "due_at": "2026-09-30T18:00:00Z",
                "created_at": "2026-09-18T08:00:00Z",
                "updated_at": "2026-09-19T09:00:00Z",
                "conversation_id": "conv_102",
            },
            {
                "id": "act_03_undated",
                "description": "Verify zero-dependency invariant",
                "completed": False,
                "due_at": None,
                "created_at": "2026-09-25T12:00:00Z",
                "updated_at": None,
                "conversation_id": None,
            },
        ]

    def tearDown(self):
        self._tmp.cleanup()

    def test_csv_headers_and_row_structure(self):
        items_dict = {it["id"]: it for it in self.sample_items}
        csv_out = ai2csv.export_csv(items_dict)
        reader = csv.reader(io.StringIO(csv_out))
        rows = list(reader)

        self.assertEqual(len(rows), 4)  # 1 header + 3 data rows
        self.assertEqual(rows[0], list(ai2csv.COLUMNS))
        self.assertEqual(rows[1][0], "act_01_review")
        self.assertEqual(rows[1][1], "Review API endpoints for export")
        self.assertEqual(rows[1][2], "FALSE")
        self.assertEqual(rows[1][3], "2026-10-01 15:00:00")
        self.assertEqual(rows[2][2], "TRUE")

    def test_formula_injection_guard(self):
        malicious_items = {
            "x1": {"id": "x1", "description": "=cmd|' /C calc'!A0", "completed": False},
            "x2": {"id": "x2", "description": "+123456789", "completed": False},
            "x3": {"id": "x3", "description": "-@danger", "completed": False},
            "x4": {"id": "x4", "description": "@SUM(A1:A5)", "completed": False},
            "x5": {"id": "x5", "description": "\tTabPrefix", "completed": False},
        }
        csv_out = ai2csv.export_csv(malicious_items)
        reader = csv.reader(io.StringIO(csv_out))
        rows = list(reader)[1:]

        for row in rows:
            desc = row[1]
            self.assertTrue(
                desc.startswith("'"),
                f"Formula injection string '{desc}' was not sanitized with leading quote",
            )

    def test_status_filtering_open_and_completed(self):
        items_dict = {it["id"]: it for it in self.sample_items}

        open_csv = ai2csv.export_csv(items_dict, status_filter="open")
        open_rows = list(csv.reader(io.StringIO(open_csv)))
        self.assertEqual(len(open_rows), 3)  # header + 2 open items
        for r in open_rows[1:]:
            self.assertEqual(r[2], "FALSE")

        done_csv = ai2csv.export_csv(items_dict, status_filter="completed")
        done_rows = list(csv.reader(io.StringIO(done_csv)))
        self.assertEqual(len(done_rows), 2)  # header + 1 completed item
        self.assertEqual(done_rows[1][2], "TRUE")

    def test_completion_coercion(self):
        self.assertTrue(ai2csv.is_completed(True))
        self.assertTrue(ai2csv.is_completed(1))
        self.assertTrue(ai2csv.is_completed("yes"))
        self.assertTrue(ai2csv.is_completed("DONE"))
        self.assertTrue(ai2csv.is_completed("True"))
        self.assertTrue(ai2csv.is_completed("x"))
        self.assertFalse(ai2csv.is_completed(False))
        self.assertFalse(ai2csv.is_completed(0))
        self.assertFalse(ai2csv.is_completed("no"))
        self.assertFalse(ai2csv.is_completed(None))
        self.assertFalse(ai2csv.is_completed({}))

    def test_timezone_offset_handling(self):
        items_dict = {
            "tz_test": {
                "id": "tz_test",
                "description": "Tokyo sync",
                "due_at": "2026-10-01T23:30:00Z",
                "completed": False,
            }
        }
        jst = timedelta(hours=9)
        csv_out = ai2csv.export_csv(items_dict, offset=jst)
        rows = list(csv.reader(io.StringIO(csv_out)))
        # 23:30 UTC + 9h -> next day 08:30
        self.assertEqual(rows[1][3], "2026-10-02 08:30:00")

    def test_parse_offset_validation(self):
        self.assertEqual(ai2csv.parse_offset("+09:00"), timedelta(hours=9))
        self.assertEqual(ai2csv.parse_offset("-05:30"), timedelta(hours=-5, minutes=-30))
        with self.assertRaises(ValueError):
            ai2csv.parse_offset("invalid")
        with self.assertRaises(ValueError):
            ai2csv.parse_offset("+15:00")
        with self.assertRaises(ValueError):
            ai2csv.parse_offset("+05:70")

    def test_parse_time_robustness(self):
        self.assertEqual(
            ai2csv.parse_time("2026-10-02T12:00:00Z"),
            datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            ai2csv.parse_time("2026-10-02T14:00:00+02:00"),
            datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            ai2csv.parse_time("2026-10-02T12:00:00"),
            datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(ai2csv.parse_time("bad-date"))
        self.assertIsNone(ai2csv.parse_time(""))
        self.assertIsNone(ai2csv.parse_time(None))
        self.assertIsNone(ai2csv.parse_time(9999))
        self.assertIsNone(ai2csv.parse_time("9999-12-31T23:59:59-14:00"))

    def test_envelope_unwrapping(self):
        nested = {"action_items": self.sample_items}
        self.assertEqual(len(ai2csv.unwrap_items(nested)), 3)

        single = {"id": "single", "description": "single task"}
        self.assertEqual(len(ai2csv.unwrap_items(single)), 1)

        with self.assertRaises(ValueError):
            ai2csv.unwrap_items("invalid string")

    def test_load_and_deduplication(self):
        f1 = self.tmp / "page1.json"
        f2 = self.tmp / "page2.json"
        f1.write_text(json.dumps([self.sample_items[0], self.sample_items[1]]), encoding="utf-8")
        f2.write_text(json.dumps([self.sample_items[1], self.sample_items[2]]), encoding="utf-8")

        loaded = ai2csv.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 3)
        self.assertIn("act_01_review", loaded)
        self.assertIn("act_02_kicad", loaded)
        self.assertIn("act_03_undated", loaded)

    def test_synthetic_id_allocation(self):
        f = self.tmp / "no_ids.json"
        items_missing_id = [
            {"description": "Task 1", "completed": False},
            {"description": "Task 2", "completed": True},
            {"id": "auto_existing", "description": "Explicit ID", "completed": False},
        ]
        f.write_text(json.dumps(items_missing_id), encoding="utf-8")
        loaded = ai2csv.load([str(f)])
        self.assertEqual(len(loaded), 3)
        self.assertIn("auto_existing", loaded)

    def test_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "tasks.csv"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        count1 = ai2csv.convert([str(src)], str(dest))
        self.assertEqual(count1, 3)
        self.assertTrue(dest.exists())

        # Second run without overwrite must raise FileExistsError
        with self.assertRaises(FileExistsError):
            ai2csv.convert([str(src)], str(dest), overwrite=False)

        # With overwrite=True it should succeed
        count2 = ai2csv.convert([str(src)], str(dest), overwrite=True)
        self.assertEqual(count2, 3)

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_items).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = ai2csv.load(["-"])
            self.assertEqual(len(loaded), 3)
            self.assertIn("act_01_review", loaded)

    def test_main_cli_execution(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "output.csv"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        ret = ai2csv.main([str(src), "-o", str(dest), "--status", "open"])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        content = dest.read_bytes().decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(content)))
        self.assertEqual(len(rows), 3)  # header + 2 open tasks


if __name__ == "__main__":
    unittest.main()
