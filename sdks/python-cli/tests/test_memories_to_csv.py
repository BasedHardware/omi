"""Tests for memories to CSV exporter (#17842 / #17843).

Pins formula neutralization, overwrite refusal, UTF-8 BOM encoding,
header structure, and payload parsing.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# Load memories_to_csv example script dynamically
script_path = (
    Path(__file__).resolve().parent.parent / "examples" / "memories_to_csv.py"
)
spec = importlib.util.spec_from_file_location("memories_to_csv", script_path)
mem2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mem2csv)


class TestMemoriesToCsv(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "mem_01",
                "content": "Likes espresso with oat milk",
                "category": "lifestyle",
                "created_at": "2026-09-24T08:00:00Z",
                "updated_at": "2026-09-24T08:00:00Z",
                "manually_added": False,
            },
            {
                "id": "mem_02",
                "content": "=SUM(A1:A10)",  # Formula trigger
                "category": "work",
                "created_at": "2026-09-24T09:00:00Z",
                "updated_at": "2026-09-24T09:00:00Z",
                "manually_added": True,
            },
            {
                "id": "mem_03",
                "content": "Prefers dark mode 🌙",  # Unicode emoji
                "category": "preferences",
                "created_at": "2026-09-24T10:00:00Z",
                "updated_at": "2026-09-24T10:00:00Z",
                "manually_added": False,
            },
        ]

    def test_formula_neutralization(self):
        """Values starting with =, +, -, @ or leading whitespace/tabs must be escaped."""
        self.assertEqual(mem2csv.spreadsheet_text("=1+1"), "'=1+1")
        self.assertEqual(mem2csv.spreadsheet_text("+cmd|' /C calc'!A0"), "'+cmd|' /C calc'!A0")
        self.assertEqual(mem2csv.spreadsheet_text("-2+3|cmd"), "'-2+3|cmd")
        self.assertEqual(mem2csv.spreadsheet_text("@SUM(B1:B5)"), "'@SUM(B1:B5)")
        self.assertEqual(mem2csv.spreadsheet_text("  =SUM(A1)"), "'  =SUM(A1)")
        self.assertEqual(mem2csv.spreadsheet_text("\t=A1"), "'\t=A1")
        self.assertEqual(mem2csv.spreadsheet_text("Normal fact"), "Normal fact")
        self.assertEqual(mem2csv.spreadsheet_text(None), "")

    def test_overwrite_refusal_and_force(self):
        """Convert must refuse to overwrite existing files unless force=True."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            json_file = tmp / "memories.json"
            csv_file = tmp / "output.csv"

            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            # First conversion
            mem2csv.convert(json_file, csv_file)
            self.assertTrue(csv_file.exists())
            original = csv_file.read_bytes()

            # Second attempt without force raises FileExistsError
            with self.assertRaises(FileExistsError):
                mem2csv.convert(json_file, csv_file, force=False)
            self.assertEqual(csv_file.read_bytes(), original)

            # Overwrite with force=True succeeds
            count = mem2csv.convert(json_file, csv_file, force=True)
            self.assertEqual(count, 3)

    def test_convert_end_to_end_and_utf8_bom(self):
        """End-to-end export preserves UTF-8 BOM, exact header, and row contents."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            json_file = tmp / "memories.json"
            csv_file = tmp / "output.csv"

            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")
            mem2csv.convert(json_file, csv_file)

            raw_bytes = csv_file.read_bytes()
            self.assertTrue(raw_bytes.startswith(b"\xef\xbb\xbf"))

            decoded = raw_bytes.decode("utf-8-sig")
            reader = list(csv.reader(decoded.splitlines()))

            self.assertEqual(reader[0], list(mem2csv.FIELDS))
            self.assertEqual(len(reader), 4)
            self.assertEqual(reader[1][1], "Likes espresso with oat milk")
            self.assertEqual(reader[2][1], "'=SUM(A1:A10)")
            self.assertIn("🌙", reader[3][1])

    def test_wrapped_json_dictionary(self):
        """Handles payloads wrapped in a 'memories' dictionary key."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            json_file = tmp / "wrapped.json"
            csv_file = tmp / "output.csv"

            json_file.write_text(
                json.dumps({"memories": self.sample_memories}), encoding="utf-8"
            )
            count = mem2csv.convert(json_file, csv_file)
            self.assertEqual(count, 3)


if __name__ == "__main__":
    unittest.main()
