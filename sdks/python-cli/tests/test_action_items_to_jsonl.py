import json
import tempfile
import unittest
from pathlib import Path
import sys

# Add parent directories to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_jsonl import (
    convert,
    format_record,
    parse_boolean,
    parse_datetime,
    read_action_items,
)


class TestActionItemsToJsonl(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.sample_items = [
            {
                "id": "task_1",
                "description": "Send invoice to client",
                "completed": False,
                "due_at": "2026-09-25T17:00:00Z",
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-20T10:00:00Z",
                "conversation_id": "conv_1",
            },
            {
                "id": "task_2",
                "description": "Deploy patch v2.4",
                "completed": True,
                "due_at": None,
                "created_at": "2026-09-21T09:00:00Z",
                "updated_at": "2026-09-21T11:00:00Z",
                "conversation_id": "conv_2",
            },
        ]
        self.input_file = self.dir_path / "action_items.json"
        self.input_file.write_text(json.dumps(self.sample_items), encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_datetime(self):
        self.assertEqual(parse_datetime("2026-09-20T10:00:00Z"), "2026-09-20T10:00:00+00:00")
        self.assertIsNone(parse_datetime(None))
        self.assertEqual(parse_datetime("not-a-date"), "not-a-date")

    def test_parse_boolean(self):
        self.assertTrue(parse_boolean(True))
        self.assertTrue(parse_boolean("true"))
        self.assertTrue(parse_boolean("1"))
        self.assertTrue(parse_boolean("completed"))
        self.assertFalse(parse_boolean(False))
        self.assertFalse(parse_boolean("false"))
        self.assertFalse(parse_boolean("0"))
        self.assertFalse(parse_boolean(None))

    def test_convert_standard_mode(self):
        out_file = self.dir_path / "standard.jsonl"
        count = convert([str(self.input_file)], str(out_file), mode="standard")
        self.assertEqual(count, 2)

        lines = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["id"], "task_1")
        self.assertEqual(lines[0]["description"], "Send invoice to client")
        self.assertFalse(lines[0]["completed"])
        self.assertEqual(lines[0]["conversation_id"], "conv_1")
        self.assertTrue(lines[1]["completed"])

    def test_convert_task_agent_mode(self):
        out_file = self.dir_path / "task_agent.jsonl"
        count = convert([str(self.input_file)], str(out_file), mode="task_agent")
        self.assertEqual(count, 2)

        lines = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(lines[0]["task_id"], "task_1")
        self.assertEqual(lines[0]["instruction"], "Send invoice to client")
        self.assertEqual(lines[0]["status"], "PENDING")
        self.assertIn("Task (PENDING)", lines[0]["prompt"])
        self.assertEqual(lines[1]["status"], "COMPLETED")

    def test_convert_minimal_mode(self):
        out_file = self.dir_path / "minimal.jsonl"
        count = convert([str(self.input_file)], str(out_file), mode="minimal")
        self.assertEqual(count, 2)

        lines = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line]
        self.assertEqual(set(lines[0].keys()), {"id", "task", "completed", "due"})
        self.assertEqual(lines[0]["task"], "Send invoice to client")

    def test_filter_pending_and_completed(self):
        out_pending = self.dir_path / "pending.jsonl"
        count_pending = convert([str(self.input_file)], str(out_pending), status_filter="pending")
        self.assertEqual(count_pending, 1)
        line = json.loads(out_pending.read_text(encoding="utf-8").strip())
        self.assertEqual(line["id"], "task_1")

        out_completed = self.dir_path / "completed.jsonl"
        count_completed = convert([str(self.input_file)], str(out_completed), status_filter="completed")
        self.assertEqual(count_completed, 1)
        line_c = json.loads(out_completed.read_text(encoding="utf-8").strip())
        self.assertEqual(line_c["id"], "task_2")

    def test_deduplication(self):
        dup_items = self.sample_items + [self.sample_items[0]]
        dup_file = self.dir_path / "dups.json"
        dup_file.write_text(json.dumps(dup_items), encoding="utf-8")

        out_file = self.dir_path / "deduped.jsonl"
        count = convert([str(dup_file)], str(out_file), dedupe=True)
        self.assertEqual(count, 2)

        out_raw = self.dir_path / "raw.jsonl"
        count_raw = convert([str(dup_file)], str(out_raw), dedupe=False)
        self.assertEqual(count_raw, 3)

    def test_unwrapped_action_items_key(self):
        wrapped = {"action_items": self.sample_items}
        wrap_file = self.dir_path / "wrapped.json"
        wrap_file.write_text(json.dumps(wrapped), encoding="utf-8")

        items = read_action_items([str(wrap_file)])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], "task_1")

    def test_path_traversal_safety(self):
        with self.assertRaises(ValueError):
            convert([str(self.input_file)], str(self.dir_path / "../escape.jsonl"))

    def test_missing_id_raises(self):
        bad_items = [{"description": "Missing ID task", "completed": False}]
        bad_file = self.dir_path / "bad.json"
        bad_file.write_text(json.dumps(bad_items), encoding="utf-8")

        with self.assertRaises(ValueError):
            convert([str(bad_file)], str(self.dir_path / "out.jsonl"))


if __name__ == "__main__":
    unittest.main()
