"""Tests for action items to JSONL converter."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_jsonl.py"
spec = importlib.util.spec_from_file_location("action_items_to_jsonl", script_path)
a2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2j)


class TestActionItemsToJsonl(unittest.TestCase):
    def setUp(self):
        self.sample_items = [
            {"id": "a1", "description": "Send report", "completed": False},
            {"id": "a2", "description": "日本語 テスト 🎧", "completed": True},
        ]

    def test_conversion(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            a2j.convert(json_file, jsonl_file)
            lines = jsonl_file.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["id"], "a1")

    def test_unicode_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

            a2j.convert(json_file, jsonl_file)
            self.assertNotIn(b"\\u", jsonl_file.read_bytes())

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps({"action_items": self.sample_items}), encoding="utf-8")

            a2j.convert(json_file, jsonl_file)
            self.assertEqual(len(jsonl_file.read_text(encoding="utf-8").splitlines()), 2)

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text("[]", encoding="utf-8")

            a2j.convert(json_file, jsonl_file)
            self.assertEqual(jsonl_file.read_text(encoding="utf-8"), "")

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps([1, 2]), encoding="utf-8")

            with self.assertRaises(ValueError):
                a2j.convert(json_file, jsonl_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            jsonl_file = Path(tmpdir) / "output.jsonl"
            json_file.write_text(json.dumps(self.sample_items), encoding="utf-8")
            jsonl_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                a2j.convert(json_file, jsonl_file)


if __name__ == "__main__":
    unittest.main()
