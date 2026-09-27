import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import timedelta

# Ensure examples directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_linear import (
    clean_text,
    is_done,
    parse_time,
    parse_offset,
    load_action_items,
    format_linear_row,
    convert,
    build_parser,
)


class TestActionItemsToLinear(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  update   linear   docs  "), "update linear docs")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text(456), "456")
        self.assertEqual(clean_text({"state": "active"}), '{"state": "active"}')

    def test_is_done(self):
        self.assertTrue(is_done(True))
        self.assertTrue(is_done(1))
        self.assertTrue(is_done("true"))
        self.assertTrue(is_done("yes"))
        self.assertTrue(is_done("completed"))
        self.assertTrue(is_done("done"))
        self.assertFalse(is_done(False))
        self.assertFalse(is_done(0))
        self.assertFalse(is_done("false"))
        self.assertFalse(is_done(None))

    def test_parse_time(self):
        t1 = parse_time("2026-09-27T10:00:00Z")
        self.assertIsNotNone(t1)
        self.assertEqual(t1.year, 2026)
        self.assertEqual(t1.hour, 10)

        t2 = parse_time("2026-09-27T14:00:00+04:00")
        self.assertIsNotNone(t2)
        self.assertEqual(t2.hour, 10)  # normalized to UTC

        self.assertIsNone(parse_time(None))
        self.assertIsNone(parse_time(""))
        self.assertIsNone(parse_time("not-a-timestamp"))

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+07:00"), timedelta(hours=7))
        self.assertEqual(parse_offset("-04:00"), timedelta(hours=-4))
        self.assertEqual(parse_offset("+00:00"), timedelta(0))

        with self.assertRaises(ValueError):
            parse_offset("invalid")
        with self.assertRaises(ValueError):
            parse_offset("+16:00")
        with self.assertRaises(ValueError):
            parse_offset("+05:70")

    def test_load_action_items_top_level_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "items.json"
            f.write_text(json.dumps([{"id": "linear-1", "description": "Fix bug"}]), encoding="utf-8")
            items = load_action_items([str(f)])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], "linear-1")

    def test_load_action_items_envelope_wrappers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "action_items.json"
            f1.write_text(json.dumps({"action_items": [{"id": "a1", "description": "Task 1"}]}), encoding="utf-8")
            self.assertEqual(len(load_action_items([str(f1)])), 1)

            f2 = Path(tmpdir) / "items.json"
            f2.write_text(json.dumps({"items": [{"id": "a2", "description": "Task 2"}]}), encoding="utf-8")
            self.assertEqual(len(load_action_items([str(f2)])), 1)

            f3 = Path(tmpdir) / "data.json"
            f3.write_text(json.dumps({"data": [{"id": "a3", "description": "Task 3"}]}), encoding="utf-8")
            self.assertEqual(len(load_action_items([str(f3)])), 1)

    def test_load_action_items_empty_envelope(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "empty.json"
            f.write_text(json.dumps({"action_items": []}), encoding="utf-8")
            items = load_action_items([str(f)])
            self.assertEqual(items, [])

    def test_load_action_items_single_object(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "single.json"
            f.write_text(json.dumps({"id": "single-1", "description": "Standalone task"}), encoding="utf-8")
            items = load_action_items([str(f)])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], "single-1")

    def test_load_action_items_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "batch1.json"
            f2 = Path(tmpdir) / "batch2.json"
            f1.write_text(json.dumps([
                {"id": "dup-1", "description": "Draft", "completed": False}
            ]), encoding="utf-8")
            f2.write_text(json.dumps([
                {"id": "dup-1", "description": "Finalized", "completed": True},
                {"id": "other-2", "description": "Other item", "completed": False}
            ]), encoding="utf-8")
            items = load_action_items([str(f1), str(f2)])
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["description"], "Finalized")
            self.assertTrue(items[0]["completed"])

    def test_format_linear_row(self):
        raw = {
            "id": "act-123",
            "description": "Send meeting minutes to team",
            "completed": False,
            "due_at": "2026-09-30T17:00:00Z",
            "created_at": "2026-09-27T10:00:00Z",
            "conversation_id": "conv-999",
        }
        row = format_linear_row(
            raw,
            offset=timedelta(hours=7),
            default_priority="High",
            extra_labels=["sprint-1"],
        )
        self.assertEqual(row["Title"], "Send meeting minutes to team")
        self.assertEqual(row["Status"], "Todo")
        self.assertEqual(row["Priority"], "High")
        self.assertEqual(row["Due Date"], "2026-10-01")  # +7h moves 17:00 to 00:00 next day
        self.assertEqual(row["Created At"], "2026-09-27 17:00:00")
        self.assertIn("omi", row["Labels"])
        self.assertIn("action-item", row["Labels"])
        self.assertIn("sprint-1", row["Labels"])
        self.assertIn("act-123", row["Description"])
        self.assertIn("conv-999", row["Description"])

    def test_convert_filter_and_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            out = Path(tmpdir) / "linear.csv"
            src.write_text(json.dumps([
                {"id": "1", "description": "Open task", "completed": False},
                {"id": "2", "description": "Closed task", "completed": True},
            ]), encoding="utf-8")

            # Filter completed only
            cnt = convert([str(src)], str(out), status_filter="completed")
            self.assertEqual(cnt, 1)
            self.assertTrue(out.exists())

            with open(out, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["Title"], "Closed task")
                self.assertEqual(rows[0]["Status"], "Done")

            # Refuse overwrite without --force
            with self.assertRaises(FileExistsError):
                convert([str(src)], str(out), force=False)

            # Overwrite with force=True
            cnt2 = convert([str(src)], str(out), status_filter="pending", force=True)
            self.assertEqual(cnt2, 1)
            with open(out, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["Title"], "Open task")
                self.assertEqual(rows[0]["Status"], "Todo")

    def test_cli_parser(self):
        parser = build_parser()
        args = parser.parse_args([
            "linear_export.csv",
            "input1.json",
            "input2.json",
            "--utc-offset", "+07:00",
            "--status", "pending",
            "--priority", "Urgent",
            "--label", "backend",
            "--force",
        ])
        self.assertEqual(args.destination, "linear_export.csv")
        self.assertEqual(args.sources, ["input1.json", "input2.json"])
        self.assertEqual(args.utc_offset, timedelta(hours=7))
        self.assertEqual(args.status, "pending")
        self.assertEqual(args.priority, "Urgent")
        self.assertEqual(args.labels, ["backend"])
        self.assertTrue(args.force)


if __name__ == "__main__":
    unittest.main()
