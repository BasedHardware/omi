"""Tests for memory list to CSV exporter."""

from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_csv.py"
spec = importlib.util.spec_from_file_location("memories_to_csv", script_path)
m2c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2c)


class TestMemoriesToCSV(unittest.TestCase):
    def test_convert_valid_memories(self):
        sample = [
            {
                "id": "mem-1",
                "category": "work",
                "visibility": "private",
                "content": "Prefers python 3.12 with async support",
                "tags": ["python", "dev"],
                "created_at": "2026-09-26T10:00:00Z",
            },
            {
                "id": "mem-2",
                "category": "personal",
                "visibility": "public",
                "content": "=cmd|' /C calc'!A0",
                "tags": [],
                "created_at": "2026-09-26T11:00:00Z",
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "memories.json"
            csv_file = Path(tmp_dir) / "memories.csv"
            json_file.write_text(json.dumps(sample), encoding="utf-8")

            m2c.convert(str(json_file), str(csv_file))
            self.assertTrue(csv_file.exists())

            with csv_file.open(encoding="utf-8-sig") as f:
                reader = list(csv.reader(f))
                self.assertEqual(reader[0], list(m2c.FIELDS))
                # Row 1
                self.assertEqual(reader[1][0], "mem-1")
                self.assertEqual(reader[1][1], "work")
                self.assertEqual(reader[1][3], "Prefers python 3.12 with async support")
                self.assertEqual(reader[1][4], "python, dev")
                # Row 2: formula prefix escaping
                self.assertEqual(reader[2][3], "'=cmd|' /C calc'!A0")

    def test_refuse_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "memories.json"
            csv_file = Path(tmp_dir) / "memories.csv"
            json_file.write_text(json.dumps([]), encoding="utf-8")
            csv_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                m2c.convert(str(json_file), str(csv_file))

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            json_file = Path(tmp_dir) / "invalid.json"
            csv_file = Path(tmp_dir) / "memories.csv"
            json_file.write_text(json.dumps({"error": "not a list"}), encoding="utf-8")

            with self.assertRaises(ValueError):
                m2c.convert(str(json_file), str(csv_file))


if __name__ == "__main__":
    unittest.main()
