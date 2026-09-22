"""Tests for memories to CSV exporter (#15813)."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_csv.py"
spec = importlib.util.spec_from_file_location("memories_to_csv", script_path)
m2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2c)


class TestMemoriesToCsv(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "mem_01",
                "content": "Prefers dark mode in IDEs.",
                "category": "lifestyle",
                "visibility": "private",
                "tags": ["editor", "ui"],
                "created_at": "2026-09-20T10:00:00Z",
            },
            {
                "id": "mem_02",
                "content": "=SUM(1+1) formula test",
                "category": "@work",
                "visibility": "public",
                "tags": ["testing"],
                "created_at": "2026-09-21T11:00:00Z",
            },
        ]

    def test_happy_path_conversion(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "memories.json"
            dst = Path(td) / "memories.csv"
            src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2c.convert(src, dst)
            self.assertTrue(dst.exists())

            with open(dst, "r", encoding="utf-8-sig") as f:
                reader = list(csv.reader(f))
                self.assertEqual(reader[0], ["id", "content", "category", "visibility", "tags", "created_at"])
                self.assertEqual(len(reader), 3)
                self.assertEqual(reader[1][0], "mem_01")
                self.assertEqual(reader[1][1], "Prefers dark mode in IDEs.")
                self.assertEqual(reader[1][4], '["editor", "ui"]')

    def test_formula_injection_neutralization(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "memories.json"
            dst = Path(td) / "memories.csv"
            src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2c.convert(src, dst)

            with open(dst, "r", encoding="utf-8-sig") as f:
                reader = list(csv.reader(f))
                row2 = reader[2]
                self.assertTrue(row2[1].startswith("'="), f"Expected neutralized formula, got {row2[1]}")
                self.assertTrue(row2[2].startswith("'@"), f"Expected neutralized @ category, got {row2[2]}")

    def test_refuse_to_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "memories.json"
            dst = Path(td) / "memories.csv"
            src.write_text(json.dumps(self.sample_memories), encoding="utf-8")
            dst.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                m2c.convert(src, dst)


if __name__ == "__main__":
    unittest.main()
