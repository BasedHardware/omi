"""Tests for Omi memories to TSV export recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_tsv.py"
spec = importlib.util.spec_from_file_location("memories_to_tsv", script_path)
m2t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2t)


class TestMemoriesToTsv(unittest.TestCase):
    def test_utc_stamp_and_escaping(self):
        self.assertEqual(m2t.utc_stamp("2026-09-24T18:00:00Z"), "2026-09-24 18:00:00")
        self.assertEqual(m2t.utc_stamp(None), "")
        self.assertEqual(m2t.spreadsheet_tsv_text("=1+1"), "'=1+1")
        self.assertEqual(m2t.spreadsheet_tsv_text("A\tB\nC"), "A B C")

    def test_extract_memories(self):
        raw_list = '[{"id": "mem-1", "content": "Knowledge item"}]'
        raw_wrapped = '{"memories": [{"id": "mem-2", "content": "Another fact"}]}'

        res1 = m2t.extract_memories(raw_list)
        res2 = m2t.extract_memories(raw_wrapped)

        self.assertEqual(len(res1), 1)
        self.assertEqual(res1[0]["id"], "mem-1")
        self.assertEqual(len(res2), 1)
        self.assertEqual(res2[0]["id"], "mem-2")

    def test_convert_to_tsv_formatting_and_filtering(self):
        item1 = {
            "id": "mem-1",
            "content": "Python is dynamic",
            "category": "work",
            "tags": ["python", "dev"],
            "visibility": "public",
        }
        item2 = {
            "id": "mem-2",
            "content": "Likes espresso",
            "category": "personal",
            "tags": ["coffee"],
            "visibility": "private",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "memories.json"
            out = tmp / "memories.tsv"

            f.write_text(json.dumps([item1, item2]), encoding="utf-8")

            # All items
            count = m2t.convert_to_tsv([f], out)
            self.assertEqual(count, 2)
            lines = out.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 3)  # header + 2 rows

            header = lines[0].split("\t")
            self.assertEqual(header, list(m2t.FIELDS))

            row1 = lines[1].split("\t")
            self.assertEqual(row1[0], "mem-1")
            self.assertEqual(row1[1], "Python is dynamic")
            self.assertEqual(row1[2], "work")
            self.assertEqual(row1[3], "python, dev")

            # Category filter
            out_work = tmp / "work.tsv"
            count_work = m2t.convert_to_tsv([f], out_work, category_filter="work")
            self.assertEqual(count_work, 1)
            work_lines = out_work.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(work_lines), 2)


if __name__ == "__main__":
    unittest.main()
