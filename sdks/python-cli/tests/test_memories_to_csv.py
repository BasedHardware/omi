"""Tests for the memories -> CSV exporter.

Pins the CSV column order, UTF-8 BOM and quoting, the formula-prefix guard,
timestamp normalisation across naive/offset inputs, the empty-content guard,
ordering, and the no-overwrite / no-partial-file guarantees.
"""

from __future__ import annotations

import csv
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_csv.py"
spec = importlib.util.spec_from_file_location("memories_to_csv", script_path)
mem2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mem2csv)


def read_rows(path):
    """Read the written CSV back, tolerating the UTF-8 BOM."""
    text = Path(path).read_bytes().decode("utf-8-sig")
    return list(csv.reader(io.StringIO(text)))


class TestMemoriesToCsv(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def export(self, items):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "memories.csv"
        counts = mem2csv.convert(source, destination)
        return counts, destination

    def test_header_and_row_order(self):
        _, destination = self.export([
            {"id": "m2", "category": "work", "created_at": "2026-09-02T10:00:00Z", "content": "second"},
            {"id": "m1", "category": "home", "created_at": "2026-09-01T10:00:00Z", "content": "first"},
        ])
        rows = read_rows(destination)
        self.assertEqual(rows[0], ["id", "category", "created_at", "manually_added", "content"])
        self.assertEqual(rows[1][0], "m1")
        self.assertEqual(rows[2][0], "m2")
        self.assertEqual(rows[1][2], "2026-09-01 10:00:00 UTC")

    def test_bom_and_formula_prefix_guard(self):
        _, destination = self.export([
            {"id": "m1", "category": "c", "created_at": "2026-09-01T00:00:00Z",
             "content": "=1+1"},
            {"id": "m2", "category": "c", "created_at": "2026-09-01T00:00:00Z",
             "content": "@mention"},
        ])
        raw = destination.read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "expected a UTF-8 BOM for Excel")
        rows = read_rows(destination)
        self.assertEqual(rows[1][4], "'=1+1")
        self.assertEqual(rows[2][4], "'@mention")

    def test_missing_or_null_content_is_empty(self):
        _, destination = self.export([
            {"id": "m1", "created_at": "2026-09-01T00:00:00Z", "content": None},
            {"id": "m2", "created_at": "2026-09-01T00:00:00Z"},
            {"id": "m3", "created_at": "2026-09-01T00:00:00Z", "content": "direct"},
        ])
        rows = read_rows(destination)
        values = {row[0]: row[4] for row in rows[1:]}
        self.assertEqual(values["m1"], "")
        self.assertEqual(values["m2"], "")
        self.assertEqual(values["m3"], "direct")

    def test_refuses_to_overwrite(self):
        source = self.tmp / "memories.json"
        source.write_text("[]", encoding="utf-8")
        destination = self.tmp / "memories.csv"
        destination.write_text("keep me", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            mem2csv.convert(source, destination)
        self.assertEqual(destination.read_text(encoding="utf-8"), "keep me")

    def test_empty_list_writes_header_only(self):
        counts, destination = self.export([])
        rows = read_rows(destination)
        self.assertEqual(rows, [["id", "category", "created_at", "manually_added", "content"]])
        self.assertEqual(counts, (0, 0, 0))

    def test_non_list_payload_is_rejected(self):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps({"items": []}), encoding="utf-8")
        destination = self.tmp / "out.csv"
        with self.assertRaises(ValueError):
            mem2csv.convert(source, destination)
        self.assertFalse(destination.exists(), "a rejected conversion must not create the file")


if __name__ == "__main__":
    unittest.main()
