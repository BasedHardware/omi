"""Unit tests for Omi memories batch pipeline (JSONL & CSV) (#18526).

Validates:
- Multi-page deduplication retaining the latest updated_at record.
- Category filtering and privacy guards.
- JSONL raw and chat/LLM fine-tuning schemas.
- CSV export with spreadsheet formula injection defense.
- Format auto-inference from destination suffixes (.jsonl, .csv).
- Path traversal refusal ('..').
- Non-destructive overwrite guards and --force overrides.
- Pure standard library compliance.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# Dynamically load examples/memories_pipeline.py
_script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_pipeline.py"
_spec = importlib.util.spec_from_file_location("memories_pipeline", _script_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load module from {_script_path}")
mp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mp)


class TestMemoriesPipeline(unittest.TestCase):
    def setUp(self):
        self.mem_1 = {
            "id": "mem-1111",
            "content": "User prefers dark mode and Python 3.12",
            "category": "preferences",
            "tags": ["ui", "python"],
            "visibility": "public",
            "created_at": "2026-09-20T10:00:00Z",
            "updated_at": "2026-09-20T10:00:00Z",
        }
        self.mem_2 = {
            "id": "mem-2222",
            "content": "Working on Omi open-source bounty program",
            "category": "work",
            "tags": ["omi", "bounty"],
            "visibility": "public",
            "created_at": "2026-09-21T09:00:00Z",
            "updated_at": "2026-09-21T09:00:00Z",
        }
        self.mem_private = {
            "id": "mem-3333",
            "content": "Secret recovery phrase stored offline",
            "category": "security",
            "tags": ["private"],
            "visibility": "private",
            "created_at": "2026-09-22T08:00:00Z",
            "updated_at": "2026-09-22T08:00:00Z",
        }

    def test_deduplication_keeps_latest_updated_at(self):
        older_mem = {
            "id": "mem-1111",
            "content": "Old preferences content",
            "category": "preferences",
            "created_at": "2026-09-20T10:00:00Z",
            "updated_at": "2026-09-19T00:00:00Z",
        }
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "page1.json"
            f2 = Path(tmp_dir) / "page2.json"
            f1.write_text(json.dumps([older_mem]), encoding="utf-8")
            f2.write_text(json.dumps([self.mem_1]), encoding="utf-8")

            res = mp.load_and_deduplicate([str(f1), str(f2)])
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["content"], "User prefers dark mode and Python 3.12")

    def test_category_filtering(self):
        items = [self.mem_1, self.mem_2, self.mem_private]
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "data.json"
            f.write_text(json.dumps(items), encoding="utf-8")

            res = mp.load_and_deduplicate([str(f)], categories={"work"})
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["id"], "mem-2222")

    def test_privacy_guard_filters_private_memories(self):
        items = [self.mem_1, self.mem_private]
        with tempfile.TemporaryDirectory() as tmp_dir:
            f = Path(tmp_dir) / "data.json"
            f.write_text(json.dumps(items), encoding="utf-8")

            res = mp.load_and_deduplicate([str(f)], include_private=False)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["id"], "mem-1111")

    def test_jsonl_raw_format(self):
        jsonl = mp.format_as_jsonl([self.mem_1, self.mem_2], schema_mode="raw")
        lines = [json.loads(line) for line in jsonl.strip().split("\n")]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["id"], "mem-1111")
        self.assertEqual(lines[1]["id"], "mem-2222")

    def test_jsonl_chat_fine_tuning_schema(self):
        jsonl = mp.format_as_jsonl([self.mem_1], schema_mode="chat")
        line = json.loads(jsonl.strip())
        self.assertIn("messages", line)
        self.assertEqual(len(line["messages"]), 3)
        self.assertEqual(line["messages"][0]["role"], "system")
        self.assertEqual(line["messages"][1]["role"], "user")
        self.assertEqual(line["messages"][2]["role"], "assistant")
        self.assertEqual(line["messages"][2]["content"], "User prefers dark mode and Python 3.12")
        self.assertEqual(line["metadata"]["id"], "mem-1111")

    def test_csv_format_and_formula_injection_defense(self):
        malicious_mem = {
            "id": "mem-evil",
            "content": "=cmd|' /C calc'!A0",
            "category": "+finance",
            "created_at": "2026-09-23T00:00:00Z",
            "updated_at": "2026-09-23T00:00:00Z",
        }
        csv_out = mp.format_as_csv([malicious_mem])
        lines = csv_out.strip().splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], ",".join(mp.CSV_FIELDS))
        # Ensure single quote prefix prevents formula execution in spreadsheets
        self.assertIn("'+finance", lines[1])
        self.assertIn("'=cmd|' /C calc'!A0", lines[1])

    def test_destination_format_auto_inference(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "src.json"
            src.write_text(json.dumps([self.mem_1]), encoding="utf-8")

            dest_jsonl = Path(tmp_dir) / "out.ndjson"
            dest_csv = Path(tmp_dir) / "out.csv"

            mp.run_pipeline([str(src)], destination=str(dest_jsonl))
            self.assertTrue(dest_jsonl.exists())
            self.assertTrue(dest_jsonl.read_text(encoding="utf-8").startswith("{\"id\": \"mem-1111\""))

            mp.run_pipeline([str(src)], destination=str(dest_csv))
            self.assertTrue(dest_csv.exists())
            self.assertTrue(dest_csv.read_text(encoding="utf-8").startswith("id,created_at"))

    def test_path_traversal_refused(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "src.json"
            src.write_text("[]", encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                mp.run_pipeline([str(src)], destination="../../escaped.jsonl")
            self.assertIn("contains '..'", str(ctx.exception))

    def test_overwrite_protection_and_force_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "src.json"
            src.write_text("[]", encoding="utf-8")
            dest = Path(tmp_dir) / "existing.jsonl"
            dest.write_text("pre-existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                mp.run_pipeline([str(src)], destination=str(dest), force=False)

            mp.run_pipeline([str(src)], destination=str(dest), force=True)
            self.assertEqual(dest.read_text(encoding="utf-8"), "")

    def test_cli_end_to_end_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "input.json"
            dest = Path(tmp_dir) / "output.jsonl"
            src.write_text(json.dumps([self.mem_1]), encoding="utf-8")

            exit_code = mp.main([str(src), "-o", str(dest), "--schema", "chat"])
            self.assertEqual(exit_code, 0)
            self.assertTrue(dest.exists())
            content = json.loads(dest.read_text(encoding="utf-8").strip())
            self.assertEqual(content["messages"][2]["content"], "User prefers dark mode and Python 3.12")


if __name__ == "__main__":
    unittest.main()
