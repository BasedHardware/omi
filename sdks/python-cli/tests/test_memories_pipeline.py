"""Unit tests for Omi memories batch pipeline (JSONL & CSV) (#19343).

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

# 动态加载 examples/memories_pipeline.py
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
            "created_at": "2026-09-22T12:00:00Z",
            "updated_at": "2026-09-22T12:00:00Z",
        }
        self.mem_formula = {
            "id": "mem-4444",
            "content": "=SUM(A1:A10) formula injection test",
            "category": "testing",
            "tags": ["formula"],
            "visibility": "public",
            "created_at": "2026-09-23T15:00:00Z",
            "updated_at": "2026-09-23T15:00:00Z",
        }

    def test_empty_input_jsonl_and_csv(self):
        jsonl = mp.format_as_jsonl([])
        self.assertEqual(jsonl, "")

        csv_text = mp.format_as_csv([])
        lines = csv_text.strip().split("\n")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], ",".join(mp.CSV_FIELDS))

    def test_envelope_unwrapping_all_keys(self):
        for key in ("memories", "items", "data", "results"):
            wrapped = {key: [self.mem_1]}
            unwrapped = mp.unwrap_memories_data(wrapped)
            self.assertEqual(len(unwrapped), 1)
            self.assertEqual(unwrapped[0]["id"], "mem-1111")

    def test_multi_page_deduplication_keeps_latest_updated_at(self):
        older_version = {
            "id": "mem-1111",
            "content": "Older content draft",
            "category": "preferences",
            "created_at": "2026-09-20T10:00:00Z",
            "updated_at": "2026-09-20T10:00:00Z",
        }
        newer_version = {
            "id": "mem-1111",
            "content": "Newer updated preferences content",
            "category": "preferences",
            "created_at": "2026-09-20T10:00:00Z",
            "updated_at": "2026-09-25T18:00:00Z",
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "page1.json"
            f2 = Path(tmp_dir) / "page2.json"
            f1.write_text(json.dumps([older_version]), encoding="utf-8")
            f2.write_text(json.dumps([newer_version]), encoding="utf-8")

            res = mp.load_and_deduplicate([str(f1), str(f2)])
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["content"], "Newer updated preferences content")

    def test_category_filtering(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "memories.json"
            src.write_text(json.dumps([self.mem_1, self.mem_2]), encoding="utf-8")

            res = mp.load_and_deduplicate([str(src)], categories={"work"})
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["id"], "mem-2222")

    def test_privacy_filtering_no_private(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "memories.json"
            src.write_text(json.dumps([self.mem_1, self.mem_private]), encoding="utf-8")

            res = mp.load_and_deduplicate([str(src)], include_private=False)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["id"], "mem-1111")

    def test_jsonl_raw_schema(self):
        jsonl = mp.format_as_jsonl([self.mem_1, self.mem_2], schema_mode="raw")
        lines = [json.loads(line) for line in jsonl.strip().split("\n")]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["id"], "mem-1111")
        self.assertEqual(lines[1]["id"], "mem-2222")

    def test_jsonl_chat_schema_for_llm_fine_tuning(self):
        jsonl = mp.format_as_jsonl([self.mem_1], schema_mode="chat")
        record = json.loads(jsonl.strip())
        self.assertIn("messages", record)
        self.assertEqual(len(record["messages"]), 3)
        self.assertEqual(record["messages"][0]["role"], "system")
        self.assertEqual(record["messages"][1]["role"], "user")
        self.assertEqual(record["messages"][2]["role"], "assistant")
        self.assertIn("User prefers dark mode", record["messages"][2]["content"])
        self.assertIn("metadata", record)

    def test_csv_export_and_formula_injection_guard(self):
        csv_text = mp.format_as_csv([self.mem_formula])
        lines = csv_text.strip().split("\n")
        self.assertEqual(len(lines), 2)
        # 确认公式被添加单引号转义，防止电子表格利用
        self.assertIn("'=SUM(A1:A10)", lines[1])

    def test_format_auto_inference_from_suffix(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "in.json"
            out_jsonl = Path(tmp_dir) / "out.jsonl"
            out_csv = Path(tmp_dir) / "out.csv"

            src.write_text(json.dumps([self.mem_1]), encoding="utf-8")

            # 自动推断为 jsonl
            mp.run_pipeline([str(src)], destination=str(out_jsonl))
            parsed = json.loads(out_jsonl.read_text(encoding="utf-8").strip())
            self.assertEqual(parsed["id"], "mem-1111")

            # 自动推断为 csv
            mp.run_pipeline([str(src)], destination=str(out_csv))
            content = out_csv.read_text(encoding="utf-8")
            self.assertTrue(content.startswith(",".join(mp.CSV_FIELDS)))

    def test_path_traversal_refusal(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "in.json"
            src.write_text("[]", encoding="utf-8")
            unsafe_dest = str(Path(tmp_dir) / "sub" / ".." / "outside.jsonl")

            with self.assertRaises(ValueError) as ctx:
                mp.run_pipeline([str(src)], destination=unsafe_dest)
            self.assertIn("contains '..'", str(ctx.exception))

    def test_overwrite_protection_and_force_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "in.json"
            dest = Path(tmp_dir) / "out.jsonl"
            src.write_text(json.dumps([self.mem_1]), encoding="utf-8")
            dest.write_text("existing content", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                mp.run_pipeline([str(src)], destination=str(dest), force=False)

            # force=True 允许覆盖
            mp.run_pipeline([str(src)], destination=str(dest), force=True)
            self.assertIn("mem-1111", dest.read_text(encoding="utf-8"))

    def test_cli_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            src = Path(tmp_dir) / "memories.json"
            dest = Path(tmp_dir) / "dataset.jsonl"
            src.write_text(json.dumps([self.mem_1, self.mem_2]), encoding="utf-8")

            proc = subprocess.run(
                [sys.executable, str(_script_path), str(src), "-o", str(dest), "--schema", "chat"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertTrue(dest.exists())
            lines = dest.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
