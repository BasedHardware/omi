#!/usr/bin/env python3
"""
Unit tests for sdks/python-cli/examples/action_items_to_csv.py
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
import sys
from pathlib import Path
from unittest.mock import patch

# Add examples and tests directory to sys.path so pytest discovers example modules in CI
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_csv import (
    FIELDS,
    convert,
    is_completed,
    items_to_rows,
    load,
    main,
    spreadsheet_text,
)


class TestActionItemsToCsv(unittest.TestCase):

    def test_spreadsheet_text_escaping(self):
        self.assertEqual(spreadsheet_text(None), "")
        self.assertEqual(spreadsheet_text("  Submit quarterly report  \n"), "Submit quarterly report")

        # Test formula injection prevention
        self.assertEqual(spreadsheet_text("=SUM(B2:B10)"), "'=SUM(B2:B10)")
        self.assertEqual(spreadsheet_text("+12345"), "'+12345")
        self.assertEqual(spreadsheet_text("-cmd|' /C calc'!A0"), "'-cmd|' /C calc'!A0")
        self.assertEqual(spreadsheet_text("@danger"), "'@danger")
        self.assertEqual(spreadsheet_text("\t=cmd"), "'=cmd")

        # Non-string coercions
        self.assertEqual(spreadsheet_text(123), "123")
        self.assertEqual(spreadsheet_text({"tags": ["urgent"]}), '{"tags": ["urgent"]}')

    def test_is_completed(self):
        self.assertTrue(is_completed(True))
        self.assertTrue(is_completed(1))
        self.assertTrue(is_completed("true"))
        self.assertTrue(is_completed("TRUE"))
        self.assertTrue(is_completed("completed"))
        self.assertTrue(is_completed("done"))
        self.assertTrue(is_completed("yes"))

        self.assertFalse(is_completed(False))
        self.assertFalse(is_completed(0))
        self.assertFalse(is_completed("false"))
        self.assertFalse(is_completed("open"))
        self.assertFalse(is_completed(None))

    def test_items_to_rows_all(self):
        items = {
            "task_1": {
                "id": "task_1",
                "description": "Send meeting minutes",
                "completed": False,
                "due_at": "2026-09-30T17:00:00Z",
                "created_at": "2026-09-24T10:00:00Z",
                "updated_at": "2026-09-24T10:05:00Z",
                "conversation_id": "conv_abc",
            }
        }
        rows = items_to_rows(items, status_filter="all")
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r[0], "task_1")
        self.assertEqual(r[1], "Send meeting minutes")
        self.assertEqual(r[2], "FALSE")
        self.assertEqual(r[3], "open")
        self.assertEqual(r[4], "2026-09-30T17:00:00Z")
        self.assertEqual(r[5], "2026-09-24T10:00:00Z")
        self.assertEqual(r[6], "2026-09-24T10:05:00Z")
        self.assertEqual(r[7], "conv_abc")

    def test_items_to_rows_filtering(self):
        items = {
            "t1": {"id": "t1", "description": "Open task", "completed": False},
            "t2": {"id": "t2", "description": "Done task", "completed": True},
        }
        # Filter open
        open_rows = items_to_rows(items, status_filter="open")
        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0][0], "t1")

        # Filter completed
        done_rows = items_to_rows(items, status_filter="completed")
        self.assertEqual(len(done_rows), 1)
        self.assertEqual(done_rows[0][0], "t2")

        # Filter all
        all_rows = items_to_rows(items, status_filter="all")
        self.assertEqual(len(all_rows), 2)

    def test_load_and_deduplicate(self):
        d1 = [{"id": "t1", "description": "Initial draft", "completed": False}]
        d2 = [{"id": "t1", "description": "Revised draft", "completed": True}]

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "p1.json"
            p2 = Path(tmpdir) / "p2.json"
            p1.write_text(json.dumps(d1), encoding="utf-8")
            p2.write_text(json.dumps(d2), encoding="utf-8")

            res = load([str(p1), str(p2)])
            self.assertEqual(len(res), 1)
            self.assertEqual(res["t1"]["description"], "Revised draft")
            self.assertEqual(res["t1"]["completed"], True)

    def test_load_dict_wrapper(self):
        d_items = {"action_items": [{"id": "t_wrap1", "description": "Wrapped in action_items"}]}
        d_data = {"data": [{"id": "t_wrap2", "description": "Wrapped in data"}]}

        with tempfile.TemporaryDirectory() as tmpdir:
            p1 = Path(tmpdir) / "w1.json"
            p2 = Path(tmpdir) / "w2.json"
            p1.write_text(json.dumps(d_items), encoding="utf-8")
            p2.write_text(json.dumps(d_data), encoding="utf-8")

            res = load([str(p1), str(p2)])
            self.assertEqual(len(res), 2)
            self.assertIn("t_wrap1", res)
            self.assertIn("t_wrap2", res)

    def test_load_stdin(self):
        d = [{"id": "t_stdin", "description": "Stdin task", "completed": False}]
        with patch("sys.stdin", io.StringIO(json.dumps(d))):
            res = load(["-"])
            self.assertEqual(len(res), 1)
            self.assertEqual(res["t_stdin"]["description"], "Stdin task")

    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(FileNotFoundError):
                load([str(Path(tmpdir) / "missing.json")])

            bad_p = Path(tmpdir) / "bad.json"
            bad_p.write_text("{corrupt", encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(bad_p)])

            noid_p = Path(tmpdir) / "no_id.json"
            noid_p.write_text('[{"description": "No ID"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load([str(noid_p)])

    def test_convert_creates_utf8_bom_csv(self):
        sample = [{"id": "t_bom", "description": "Check BOM encoding", "completed": True}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            dst = Path(tmpdir) / "tasks.csv"
            src.write_text(json.dumps(sample), encoding="utf-8")

            # Overwrite protection test
            dst.write_text("existing", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(dst), force=False)

            convert([str(src)], str(dst), force=True)
            content_bytes = dst.read_bytes()
            # Check UTF-8 BOM
            self.assertTrue(content_bytes.startswith(b"\xef\xbb\xbf"))

            # Read CSV content
            decoded_text = content_bytes.decode("utf-8-sig")
            reader = list(csv.reader(io.StringIO(decoded_text)))
            self.assertEqual(reader[0], list(FIELDS))
            self.assertEqual(reader[1][0], "t_bom")
            self.assertEqual(reader[1][1], "Check BOM encoding")
            self.assertEqual(reader[1][2], "TRUE")
            self.assertEqual(reader[1][3], "completed")

    def test_cli_execution(self):
        sample = [{"id": "t_cli", "description": "CLI task", "completed": False}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "input.json"
            dst = Path(tmpdir) / "output.csv"
            dst2 = Path(tmpdir) / "output2.csv"
            src.write_text(json.dumps(sample), encoding="utf-8")

            with patch("sys.argv", ["action_items_to_csv.py", str(src), str(dst), "--status", "open"]):
                main()
            self.assertTrue(dst.exists())

            # Test failure exit code with missing source file
            with patch("sys.argv", ["action_items_to_csv.py", str(Path(tmpdir) / "nonexistent.json"), str(dst2)]):
                with self.assertRaises(SystemExit) as cm:
                    main()
                self.assertEqual(cm.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
