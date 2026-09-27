"""Unit tests for conversation to TSV exporter (#19310).

Validates:
- Pure stdlib compliance (zero external dependencies).
- Envelope unwrapping for bare lists and wrapped structures ('conversations', 'items', 'data', 'results').
- Path traversal refusal with '..' in destination path.
- Strictly 1 line per record constraint with safe newline and tab escaping.
- File overwriting protection and force override.
- CLI argument parsing, stdin/stdout streaming, and exit code semantics.
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

# 动态加载 examples/conversations_to_tsv.py 模块
_script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_tsv.py"
_spec = importlib.util.spec_from_file_location("conversations_to_tsv", _script_path)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Cannot load module from {_script_path}")
c2tsv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(c2tsv)


class TestConversationsToTsv(unittest.TestCase):
    def setUp(self):
        self.sample_conv_1 = {
            "id": "c1111111-2222-3333-4444-555555555555",
            "started_at": "2026-09-27T10:00:00Z",
            "structured": {
                "title": "Weekly Standup",
                "category": "work",
                "overview": "First line of overview.\nSecond line of overview.\tWith a tab.",
            },
            "source": "omi_necklace",
            "transcript": "Speaker 1: Hello team.\r\nSpeaker 2: Morning everyone!",
        }
        self.sample_conv_2 = {
            "id": "c2222222-3333-4444-5555-666666666666",
            "started_at": "2026-09-27T14:30:00Z",
            "structured": {
                "title": "Coffee Chat",
                "category": "personal",
                "overview": "Casual catch-up.",
            },
            "source": "friend_v1",
            "segments": [
                {"speaker": "Alice", "text": "How is the bounty going?"},
                {"speaker": "Bob", "text": "Almost merged!"},
            ],
        }

    def test_empty_list_produces_only_header(self):
        tsv = c2tsv.conversations_to_tsv_string([])
        lines = tsv.strip().split("\n")
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "\t".join(c2tsv.FIELDS))

    def test_bare_array_conversion(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "output.tsv"

            in_file.write_text(json.dumps([self.sample_conv_1, self.sample_conv_2]), encoding="utf-8")
            res = c2tsv.convert(str(in_file), str(out_file))

            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertEqual(res, content)
            lines = content.strip().split("\n")
            self.assertEqual(len(lines), 3)  # 表头 + 2 条记录

    def test_envelope_unwrapping_conversations(self):
        data = {"conversations": [self.sample_conv_1]}
        items = c2tsv.unwrap_conversations(data)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], self.sample_conv_1["id"])

    def test_envelope_unwrapping_items_data_results(self):
        for key in ("items", "data", "results"):
            data = {key: [self.sample_conv_2]}
            items = c2tsv.unwrap_conversations(data)
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], self.sample_conv_2["id"])

    def test_strictly_one_line_per_record_with_newlines_and_tabs(self):
        conv_with_messy_controls = {
            "id": "conv-control-test",
            "started_at": "2026-09-27T00:00:00Z",
            "structured": {
                "title": "Title\nwith\r\nnewlines\tand\ttabs",
                "category": "misc",
                "overview": "Multi-line\r\nsummary\nwith\tsome\tfields",
            },
            "source": "test_harness",
            "transcript": "Line 1\rLine 2\nLine 3\tTabbed",
        }

        tsv = c2tsv.conversations_to_tsv_string([conv_with_messy_controls])
        lines = tsv.strip().split("\n")
        # 必须绝对保证刚好 2 行：1 行 Header + 1 行 Record
        self.assertEqual(len(lines), 2)

        data_row = lines[1].split("\t")
        self.assertEqual(len(data_row), len(c2tsv.FIELDS))
        # 验证内部换行和制表符已转义为字面量字符
        self.assertIn("\\n", data_row[2])
        self.assertIn("\\t", data_row[2])
        self.assertIn("\\n", data_row[5])
        self.assertIn("\\t", data_row[5])
        self.assertIn("\\n", data_row[6])
        self.assertIn("\\t", data_row[6])

    def test_path_traversal_refusal(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            in_file.write_text("[]", encoding="utf-8")

            # 包含 '..' 路径遍历将被拦截
            unsafe_dest = str(Path(tmp_dir) / "sub" / ".." / "outside.tsv")
            with self.assertRaises(ValueError) as ctx:
                c2tsv.convert(str(in_file), unsafe_dest)
            self.assertIn("contains '..'", str(ctx.exception))

    def test_file_already_exists_protection(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "existing.tsv"

            in_file.write_text("[]", encoding="utf-8")
            out_file.write_text("pre-existing content", encoding="utf-8")

            # 默认不覆盖已有文件
            with self.assertRaises(FileExistsError) as ctx:
                c2tsv.convert(str(in_file), str(out_file), force=False)
            self.assertIn("Refusing to overwrite", str(ctx.exception))
            self.assertEqual(out_file.read_text(encoding="utf-8"), "pre-existing content")

    def test_force_overwrite_flag(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "existing.tsv"

            in_file.write_text(json.dumps([self.sample_conv_1]), encoding="utf-8")
            out_file.write_text("old content", encoding="utf-8")

            c2tsv.convert(str(in_file), str(out_file), force=True)
            new_content = out_file.read_text(encoding="utf-8")
            self.assertIn(self.sample_conv_1["id"], new_content)

    def test_stdin_and_stdout_streaming(self):
        input_json = json.dumps([self.sample_conv_1])
        with tempfile.TemporaryDirectory() as tmp_dir:
            stdin_mock = io.StringIO(input_json)
            stdout_mock = io.StringIO()

            old_stdin = sys.stdin
            old_stdout = sys.stdout
            try:
                sys.stdin = stdin_mock
                sys.stdout = stdout_mock
                code = c2tsv.main(["-", "-"])
                self.assertEqual(code, 0)
                output = stdout_mock.getvalue()
                self.assertIn(self.sample_conv_1["id"], output)
                self.assertTrue(output.startswith("\t".join(c2tsv.FIELDS)))
            finally:
                sys.stdin = old_stdin
                sys.stdout = old_stdout

    def test_malformed_json_error_handling(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "broken.json"
            in_file.write_text("{this is not valid json}", encoding="utf-8")

            with self.assertRaises(ValueError) as ctx:
                c2tsv.convert(str(in_file))
            self.assertIn("Malformed JSON", str(ctx.exception))

    def test_invalid_json_shape_error_handling(self):
        # 既不是列表也不是包裹对象
        with self.assertRaises(ValueError) as ctx:
            c2tsv.unwrap_conversations({"foo": "bar"})
        self.assertIn("expected a JSON array or envelope object", str(ctx.exception))

        # 包含非对象元素
        with self.assertRaises(ValueError) as ctx:
            c2tsv.unwrap_conversations(["not-a-dict"])
        self.assertIn("must be a JSON object", str(ctx.exception))

    def test_missing_input_file_error_handling(self):
        with self.assertRaises(FileNotFoundError):
            c2tsv.convert("non_existent_file_path_12345.json")

    def test_cli_invocation_end_to_end(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            in_file = Path(tmp_dir) / "input.json"
            out_file = Path(tmp_dir) / "output.tsv"

            in_file.write_text(json.dumps([self.sample_conv_1, self.sample_conv_2]), encoding="utf-8")

            # 运行命令行脚本
            proc = subprocess.run(
                [sys.executable, str(_script_path), str(in_file), "-o", str(out_file)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0)
            self.assertTrue(out_file.exists())
            self.assertIn("Weekly Standup", out_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
