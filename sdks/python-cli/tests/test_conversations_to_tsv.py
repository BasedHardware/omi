#!/usr/bin/env python3
"""
Unit tests for conversations_to_tsv converter.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from conversations_to_tsv import (
    COLUMNS,
    convert_conversations_to_tsv,
    escape_tsv_field,
    format_conversation_tsv_row,
    main,
    parse_conversations_payload,
)


class TestConversationsToTSV(unittest.TestCase):

    def test_escape_tsv_field(self):
        self.assertEqual(escape_tsv_field("hello\tworld\nsecond line"), "hello world\\nsecond line")
        self.assertEqual(escape_tsv_field(None), "")

    def test_parse_conversations_bare_array(self):
        bare = [{"id": "c1", "status": "completed"}]
        res = parse_conversations_payload(bare)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "c1")

    def test_parse_conversations_wrapped(self):
        for key in ("conversations", "items", "data", "results"):
            wrapped = {key: [{"id": f"c-{key}"}]}
            res = parse_conversations_payload(wrapped)
            self.assertEqual(len(res), 1)
            self.assertEqual(res[0]["id"], f"c-{key}")

    def test_format_conversation_tsv_row(self):
        item = {
            "id": "c-100",
            "started_at": "2026-06-01T10:00:00Z",
            "finished_at": "2026-06-01T10:30:00Z",
            "status": "completed",
            "structured": {
                "overview": "Quarterly planning\tmeeting\nwith leads",
            },
            "transcript_segments": [
                {"text": "Hello team."},
                {"text": "Let's review the roadmap."},
            ],
        }
        row = format_conversation_tsv_row(item)
        self.assertEqual(row["id"], "c-100")
        self.assertEqual(row["started_at"], "2026-06-01T10:00:00Z")
        self.assertEqual(row["finished_at"], "2026-06-01T10:30:00Z")
        self.assertEqual(row["status"], "completed")
        self.assertEqual(row["transcript_summary"], "Quarterly planning meeting\\nwith leads")
        self.assertEqual(row["transcript_segments_count"], "2")
        self.assertEqual(row["transcript_text"], "Hello team. Let's review the roadmap.")

    def test_convert_conversations_to_tsv_output(self):
        sample = [
            {
                "id": "c1",
                "started_at": "2026-06-01",
                "finished_at": "2026-06-01",
                "status": "completed",
                "transcript": "Audio transcript here",
            }
        ]
        tsv_text = convert_conversations_to_tsv(json.dumps(sample))
        lines = tsv_text.strip().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], "\t".join(COLUMNS))
        fields = lines[1].split("\t")
        self.assertEqual(fields[0], "c1")
        self.assertEqual(fields[6], "Audio transcript here")

    def test_path_traversal_rejection(self):
        with self.assertRaises(ValueError):
            convert_conversations_to_tsv("[]", Path("out/../../hack.tsv"))

    def test_invalid_json_rejection(self):
        with self.assertRaises(ValueError):
            convert_conversations_to_tsv("malformed {json")

    def test_atomic_file_write(self):
        sample = [{"id": "c-atom", "status": "completed"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "convos.tsv"
            convert_conversations_to_tsv(json.dumps(sample), out_file)
            self.assertTrue(out_file.is_file())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("c-atom", content)
            self.assertFalse(out_file.with_suffix(".tsv.partial").exists())

    def test_cli_execution_file(self):
        sample = [{"id": "c-cli", "status": "completed"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            in_file = Path(tmpdir) / "convos.json"
            out_file = Path(tmpdir) / "convos.tsv"
            in_file.write_text(json.dumps(sample), encoding="utf-8")

            exit_code = main([str(in_file), "-o", str(out_file)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.is_file())
            self.assertIn("c-cli", out_file.read_text(encoding="utf-8"))

    def test_cli_missing_input(self):
        exit_code = main(["nonexistent_convos.json"])
        self.assertEqual(exit_code, 1)


if __name__ == "__main__":
    unittest.main()
