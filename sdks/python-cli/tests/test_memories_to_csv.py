"""Tests for memories to CSV exporter recipe (#20285)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_csv.py"
spec = importlib.util.spec_from_file_location("memories_to_csv", script_path)
m2csv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2csv)


class TestMemoriesToCSV(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "mem_01_work",
                "category": "work",
                "visibility": "private",
                "content": "Prefers asynchronous communication",
                "tags": ["workflow", "management"],
                "created_at": "2026-09-15T10:30:00Z",
            },
            {
                "id": "mem_02_formula",
                "category": "=work",
                "visibility": "-private",
                "content": "+100 bonus points",
                "tags": ["@tag"],
                "created_at": "2026-09-16T14:15:00Z",
            },
        ]

    def test_csv_formatting_bom_and_formula_guard(self):
        csv_text = m2csv.memories_to_csv(self.sample_memories)
        self.assertTrue(csv_text.startswith("\ufeff"))
        self.assertIn("id,category,visibility,content,tags,created_at,updated_at", csv_text)
        self.assertIn("'=work", csv_text)
        self.assertIn("'-private", csv_text)
        self.assertIn("'+100 bonus points", csv_text)
        self.assertIn("'@tag", csv_text)

    def test_convert_file(self):
        import json

        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "memories.json"
            out_file = Path(tmp_dir) / "memories.csv"
            in_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2csv.convert(str(in_file), str(out_file))
            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertTrue(content.startswith("\ufeff"))
            self.assertIn("mem_01_work", content)


if __name__ == "__main__":
    unittest.main()
