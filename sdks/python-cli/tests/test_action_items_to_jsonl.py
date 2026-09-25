"""Hermetic unit tests for Omi action items to JSONL recipe."""

import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from examples.action_items_to_jsonl import (
    convert_action_items,
    format_chat_entry,
    format_record_entry,
    validate_and_normalize_record,
)


class TestActionItemsToJsonl(unittest.TestCase):
    def test_validate_and_normalize_valid_record(self):
        raw = {
            "id": "act_001",
            "description": "Send project status update to leadership",
            "completed": False,
            "due_date": "2026-09-30T17:00:00Z",
            "created_at": "2026-09-25T12:00:00Z",
            "conversation_id": "conv_999",
        }
        item = validate_and_normalize_record(raw)
        self.assertIsNotNone(item)
        self.assertEqual(item["id"], "act_001")
        self.assertEqual(item["description"], "Send project status update to leadership")
        self.assertFalse(item["completed"])
        self.assertEqual(item["status"], "open")
        self.assertEqual(item["due_date"], "2026-09-30T17:00:00Z")
        self.assertEqual(item["conversation_id"], "conv_999")

    def test_validate_and_normalize_skips_invalid_records(self):
        self.assertIsNone(validate_and_normalize_record(None))
        self.assertIsNone(validate_and_normalize_record("not a dict"))
        self.assertIsNone(validate_and_normalize_record({}))
        self.assertIsNone(validate_and_normalize_record({"id": "act_002"}))  # missing description
        self.assertIsNone(validate_and_normalize_record({"id": "act_003", "description": "   "}))

    def test_validate_and_normalize_skips_deleted_records(self):
        raw = {"id": "act_del", "description": "Obsolete task", "deleted": True}
        self.assertIsNone(validate_and_normalize_record(raw))

    def test_boolean_coercion_for_completed(self):
        self.assertTrue(validate_and_normalize_record({"id": "1", "description": "t", "completed": True})["completed"])
        self.assertTrue(validate_and_normalize_record({"id": "2", "description": "t", "completed": "true"})["completed"])
        self.assertTrue(validate_and_normalize_record({"id": "3", "description": "t", "completed": 1})["completed"])
        self.assertFalse(validate_and_normalize_record({"id": "4", "description": "t", "completed": False})["completed"])
        self.assertFalse(validate_and_normalize_record({"id": "5", "description": "t", "completed": "false"})["completed"])
        self.assertFalse(validate_and_normalize_record({"id": "6", "description": "t", "completed": None})["completed"])

    def test_convert_task_extraction_format(self):
        records = [
            {
                "id": "act_101",
                "description": "Follow up with client about contract terms",
                "completed": False,
                "due_date": "2026-10-05",
                "conversation_id": "conv_123",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            dest = Path(tmpdir) / "output.jsonl"
            src.write_text(json.dumps(records), encoding="utf-8")

            total, written = convert_action_items([src], dest, output_format="task-extraction")
            self.assertEqual(total, 1)
            self.assertEqual(written, 1)

            lines = dest.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)

            row = json.loads(lines[0])
            self.assertEqual(row["id"], "act_101")
            self.assertEqual(len(row["messages"]), 3)
            self.assertEqual(row["messages"][0]["role"], "system")
            self.assertEqual(row["messages"][1]["role"], "user")
            self.assertIn("conv_123", row["messages"][1]["content"])
            self.assertEqual(row["messages"][2]["role"], "assistant")
            self.assertIn("Follow up with client", row["messages"][2]["content"])
            self.assertIn("Status: Pending", row["messages"][2]["content"])
            self.assertIn("Due Date: 2026-10-05", row["messages"][2]["content"])

    def test_convert_task_record_format(self):
        records = [
            {
                "id": "act_201",
                "description": "Buy groceries",
                "completed": True,
                "created_at": "2026-09-24T10:00:00Z",
                "conversation_id": "conv_456",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            dest = Path(tmpdir) / "output.jsonl"
            src.write_text(json.dumps(records), encoding="utf-8")

            total, written = convert_action_items([src], dest, output_format="task-record")
            self.assertEqual(total, 1)
            self.assertEqual(written, 1)

            lines = dest.read_text(encoding="utf-8").strip().splitlines()
            row = json.loads(lines[0])
            self.assertEqual(row["id"], "act_201")
            self.assertEqual(row["description"], "Buy groceries")
            self.assertTrue(row["completed"])
            self.assertEqual(row["status"], "completed")
            self.assertEqual(row["metadata"]["conversation_id"], "conv_456")

    def test_status_filter_open_and_completed(self):
        records = [
            {"id": "act_open", "description": "Open task", "completed": False},
            {"id": "act_done", "description": "Done task", "completed": True},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            src.write_text(json.dumps(records), encoding="utf-8")

            # Filter open only
            dest_open = Path(tmpdir) / "open.jsonl"
            convert_action_items([src], dest_open, status_filter="open")
            rows_open = dest_open.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows_open), 1)
            self.assertEqual(json.loads(rows_open[0])["id"], "act_open")

            # Filter completed only
            dest_done = Path(tmpdir) / "done.jsonl"
            convert_action_items([src], dest_done, status_filter="completed")
            rows_done = dest_done.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(rows_done), 1)
            self.assertEqual(json.loads(rows_done[0])["id"], "act_done")

    def test_deduplication_across_multiple_files(self):
        file1_data = [{"id": "act_dup", "description": "Task version 1", "completed": False}]
        file2_data = [
            {"id": "act_dup", "description": "Task version 2", "completed": True},
            {"id": "act_unique", "description": "Unique task", "completed": False},
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            src1 = Path(tmpdir) / "f1.json"
            src2 = Path(tmpdir) / "f2.json"
            dest = Path(tmpdir) / "dedup.jsonl"
            src1.write_text(json.dumps(file1_data), encoding="utf-8")
            src2.write_text(json.dumps(file2_data), encoding="utf-8")

            total, written = convert_action_items([src1, src2], dest)
            self.assertEqual(total, 3)
            self.assertEqual(written, 2)

    def test_atomic_overwrite_guard(self):
        records = [{"id": "act_1", "description": "Task 1", "completed": False}]

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            dest = Path(tmpdir) / "exists.jsonl"
            src.write_text(json.dumps(records), encoding="utf-8")
            dest.write_text("existing content\n", encoding="utf-8")

            # Should fail without force=True
            with self.assertRaises(FileExistsError):
                convert_action_items([src], dest, force=False)

            # Should succeed with force=True
            convert_action_items([src], dest, force=True)
            self.assertIn("act_1", dest.read_text(encoding="utf-8"))

    def test_enveloped_json_payloads(self):
        enveloped = {
            "action_items": [
                {"id": "act_env", "description": "Enveloped task", "completed": False}
            ]
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "enveloped.json"
            dest = Path(tmpdir) / "out.jsonl"
            src.write_text(json.dumps(enveloped), encoding="utf-8")

            total, written = convert_action_items([src], dest)
            self.assertEqual(total, 1)
            self.assertEqual(written, 1)


if __name__ == "__main__":
    unittest.main()
