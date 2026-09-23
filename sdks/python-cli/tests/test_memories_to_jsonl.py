"""Tests for memories to JSONL converter."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_jsonl.py"
spec = importlib.util.spec_from_file_location("memories_to_jsonl", script_path)
m2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2j)


class TestMemoriesToJsonl(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {"id": "m1", "category": "work", "content": "Prefers async standups"},
            {"id": "m2", "category": "hobbies", "content": "日本語 テスト 🎧"},
        ]

    def test_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2j.convert(json_file, jsonl_file)
            lines = jsonl_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["id"], "m1")

    def test_unicode_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2j.convert(json_file, jsonl_file)
            raw = jsonl_file.read_bytes()
            self.assertNotIn(b"\\u", raw)

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps({"memories": self.sample_memories}), encoding="utf-8")

            m2j.convert(json_file, jsonl_file)
            self.assertEqual(len(jsonl_file.read_text(encoding="utf-8").splitlines()), 2)

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text("[]", encoding="utf-8")

            m2j.convert(json_file, jsonl_file)
            self.assertEqual(jsonl_file.read_text(encoding="utf-8"), "")

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps([1, 2]), encoding="utf-8")

            with self.assertRaises(ValueError):
                m2j.convert(json_file, jsonl_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")
            jsonl_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                m2j.convert(json_file, jsonl_file)


if __name__ == "__main__":
    unittest.main()
