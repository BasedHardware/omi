"""Hermetic unit tests for action_items_to_csv example recipe.

Verifies CSV formatting, TSV output, formula injection defenses,
status filtering, date sorting, boolean formats, resilient schema loading,
and Excel BOM handling.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_csv.py"
spec = importlib.util.spec_from_file_location("action_items_to_csv", script_path)
ai2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2csv)


class TestActionItemsToCsv(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {
                "id": "act_01_urgent",
                "description": "Prepare release notes for v1.0",
                "completed": False,
                "due_at": "2026-09-28T12:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-21T10:00:00Z",
                "conversation_id": "conv_100",
            },
            {
                "id": "act_02_done",
                "description": "Fix BLE pairing timeout bug",
                "completed": True,
                "due_at": "2026-09-25T15:30:00Z",
                "created_at": "2026-09-18T08:00:00Z",
                "updated_at": "2026-09-25T16:00:00Z",
                "conversation_id": "conv_200",
            },
            {
                "id": "act_03_undated",
                "description": "Research LLM fine-tuning techniques",
                "completed": False,
                "due_at": None,
                "created_at": "2026-09-22T09:00:00Z",
                "updated_at": None,
                "conversation_id": None,
            },
        ]

    def test_default_csv_structure_and_header(self):
        csv_out = ai2csv.export_csv(self.sample_items)
        lines = csv_out.strip().splitlines()
        self.assertGreaterEqual(len(lines), 4)

        reader = csv.reader(io.StringIO(csv_out))
        rows = list(reader)
        self.assertEqual(
            rows[0],
            ["id", "description", "completed", "due_at_utc", "created_at_utc", "updated_at_utc", "conversation_id"],
        )
        self.assertEqual(rows[1][0], "act_01_urgent")
        self.assertEqual(rows[1][1], "Prepare release notes for v1.0")
        self.assertEqual(rows[1][2], "FALSE")
        self.assertEqual(rows[1][3], "2026-09-28 12:00:00")
        self.assertEqual(rows[2][2], "TRUE")

    def test_tsv_mode(self):
        tsv_out = ai2csv.export_csv(self.sample_items, delimiter="\t")
        first_line = tsv_out.strip().splitlines()[0]
        self.assertIn("\t", first_line)
        parts = first_line.split("\t")
        self.assertEqual(parts[0], "id")
        self.assertEqual(parts[1], "description")

    def test_formula_injection_defense(self):
        vulnerable_items = [
            {"id": "vuln_1", "description": "=cmd|' /C calc'!A0", "completed": False},
            {"id": "vuln_2", "description": "+2+5+cmd", "completed": True},
            {"id": "vuln_3", "description": "-@dangerous", "completed": False},
            {"id": "vuln_4", "description": "@SUM(A1:A10)", "completed": False},
            {"id": "num_neg", "description": "-42", "completed": False},
        ]
        csv_out = ai2csv.export_csv(vulnerable_items, defend_formula_injection=True)
        reader = csv.reader(io.StringIO(csv_out))
        rows = list(reader)[1:]

        self.assertEqual(rows[0][1], "'=cmd|' /C calc'!A0")
        self.assertEqual(rows[1][1], "'+2+5+cmd")
        self.assertEqual(rows[2][1], "'-@dangerous")
        self.assertEqual(rows[3][1], "'@SUM(A1:A10)")
        # Bare numeric values should not be escaped
        self.assertEqual(rows[4][1], "-42")

    def test_disable_formula_defense(self):
        items = [{"id": "item1", "description": "=1+1", "completed": False}]
        csv_out = ai2csv.export_csv(items, defend_formula_injection=False)
        reader = csv.reader(io.StringIO(csv_out))
        rows = list(reader)[1:]
        self.assertEqual(rows[0][1], "=1+1")

    def test_status_filtering(self):
        open_items = ai2csv.filter_and_sort_items(self.sample_items, status_filter="open")
        self.assertEqual(len(open_items), 2)
        self.assertTrue(all(not it.get("completed") for it in open_items))

        completed_items = ai2csv.filter_and_sort_items(self.sample_items, status_filter="completed")
        self.assertEqual(len(completed_items), 1)
        self.assertEqual(completed_items[0]["id"], "act_02_done")

        all_items = ai2csv.filter_and_sort_items(self.sample_items, status_filter="all")
        self.assertEqual(len(all_items), 3)

    def test_sorting_by_due_date_and_reverse(self):
        sorted_items = ai2csv.filter_and_sort_items(self.sample_items, sort_by="due_at")
        # act_02_done has 2026-09-25, act_01_urgent has 2026-09-28, act_03 has None (max)
        self.assertEqual(sorted_items[0]["id"], "act_02_done")
        self.assertEqual(sorted_items[1]["id"], "act_01_urgent")
        self.assertEqual(sorted_items[2]["id"], "act_03_undated")

        reversed_items = ai2csv.filter_and_sort_items(self.sample_items, sort_by="due_at", reverse=True)
        self.assertEqual(reversed_items[0]["id"], "act_03_undated")

    def test_boolean_formatting(self):
        items = [{"id": "1", "description": "T", "completed": True}, {"id": "2", "description": "F", "completed": False}]

        csv_check = ai2csv.export_csv(items, bool_format="check")
        self.assertIn("[x]", csv_check)
        self.assertIn("[ ]", csv_check)

        csv_bool = ai2csv.export_csv(items, bool_format="boolean")
        self.assertIn("true", csv_bool)
        self.assertIn("false", csv_bool)

        csv_int = ai2csv.export_csv(items, bool_format="int")
        reader = list(csv.reader(io.StringIO(csv_int)))
        self.assertEqual(reader[1][2], "1")
        self.assertEqual(reader[2][2], "0")

    def test_resilient_loading(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            # 1. Wrapped in {"action_items": [...]}
            p1 = tmp / "wrapped.json"
            p1.write_text(json.dumps({"action_items": self.sample_items}))
            loaded = ai2csv.load_items(str(p1))
            self.assertEqual(len(loaded), 3)

            # 2. Wrapped in {"items": [...]}
            p2 = tmp / "items_wrapped.json"
            p2.write_text(json.dumps({"items": self.sample_items}))
            loaded = ai2csv.load_items(str(p2))
            self.assertEqual(len(loaded), 3)

            # 3. Single item
            p3 = tmp / "single.json"
            p3.write_text(json.dumps({"id": "only_one", "description": "Lone task"}))
            loaded = ai2csv.load_items(str(p3))
            self.assertEqual(len(loaded), 1)

            # 4. Empty file
            p4 = tmp / "empty.json"
            p4.write_text("")
            loaded = ai2csv.load_items(str(p4))
            self.assertEqual(len(loaded), 0)

    def test_excel_bom_flag(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "tasks_bom.csv"
            ai2csv.export_csv(self.sample_items, output_path=str(out_file), excel_bom=True)
            raw_bytes = out_file.read_bytes()
            # UTF-8 BOM is \xef\xbb\xbf
            self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

    def test_no_header_flag(self):
        csv_out = ai2csv.export_csv(self.sample_items, include_header=False)
        reader = list(csv.reader(io.StringIO(csv_out)))
        self.assertNotEqual(reader[0][0], "id")
        self.assertEqual(reader[0][0], "act_01_urgent")


if __name__ == "__main__":
    unittest.main()
