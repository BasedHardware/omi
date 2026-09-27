import csv
import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
import sys

# Ensure examples directory is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))

from action_items_to_jira import (
    clean_text,
    is_done,
    parse_time,
    parse_offset,
    load_action_items,
    format_jira_row,
    convert,
    build_parser,
)


class TestActionItemsToJira(unittest.TestCase):
    def test_clean_text(self):
        self.assertEqual(clean_text("  prepare   sprint   demo  "), "prepare sprint demo")
        self.assertEqual(clean_text(None), "")
        self.assertEqual(clean_text(123), "123")
        self.assertEqual(clean_text({"foo": "bar"}), '{"foo": "bar"}')

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

        t2 = parse_time("2026-09-27T12:00:00+02:00")
        self.assertIsNotNone(t2)
        self.assertEqual(t2.hour, 10)  # normalized to UTC

        self.assertIsNone(parse_time(None))
        self.assertIsNone(parse_time(""))
        self.assertIsNone(parse_time("invalid-timestamp"))

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+05:30"), timedelta(hours=5, minutes=30))
        self.assertEqual(parse_offset("-08:00"), timedelta(hours=-8))
        self.assertEqual(parse_offset("+00:00"), timedelta(0))

        with self.assertRaises(ValueError):
            parse_offset("invalid")
        with self.assertRaises(ValueError):
            parse_offset("+15:00")
        with self.assertRaises(ValueError):
            parse_offset("+05:65")

    def test_load_action_items_top_level_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f = Path(tmpdir) / "items.json"
            f.write_text(json.dumps([{"id": "item-1", "description": "Fix bug"}]), encoding="utf-8")
            items = load_action_items([str(f)])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], "item-1")

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
            f.write_text(json.dumps({"id": "single-1", "description": "Only task"}), encoding="utf-8")
            items = load_action_items([str(f)])
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["id"], "single-1")

    def test_load_action_items_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "page1.json"
            f2 = Path(tmpdir) / "page2.json"
            f1.write_text(json.dumps([
                {"id": "dup-1", "description": "Draft 1", "completed": False}
            ]), encoding="utf-8")
            f2.write_text(json.dumps([
                {"id": "dup-1", "description": "Draft 2", "completed": True},
                {"id": "uniq-2", "description": "Other task", "completed": False}
            ]), encoding="utf-8")
            items = load_action_items([str(f1), str(f2)])
            self.assertEqual(len(items), 2)
            self.assertEqual(items[0]["description"], "Draft 2")
            self.assertTrue(items[0]["completed"])

    def test_format_jira_row(self):
        raw = {
            "id": "act-555",
            "description": "Fix memory leak in websocket listener",
            "completed": False,
            "due_at": "2026-10-05T12:00:00Z",
            "created_at": "2026-09-27T08:00:00Z",
            "conversation_id": "conv-888",
        }
        row = format_jira_row(
            raw,
            offset=timedelta(0),
            default_priority="High",
            issue_type="Story",
            extra_labels=["backend bug"],
        )
        self.assertEqual(row["Summary"], "Fix memory leak in websocket listener")
        self.assertEqual(row["Status"], "To Do")
        self.assertEqual(row["Issue Type"], "Story")
        self.assertEqual(row["Priority"], "High")
        self.assertEqual(row["Due Date"], "2026-10-05")
        self.assertEqual(row["Created"], "2026-09-27 08:00:00")
        self.assertIn("omi", row["Labels"])
        self.assertIn("action-item", row["Labels"])
        self.assertIn("backend-bug", row["Labels"])
        self.assertIn("act-555", row["Description"])
        self.assertIn("conv-888", row["Description"])

    def test_format_jira_row_date_offset_boundary(self):
        raw = {
            "id": "act-midnight",
            "description": "Cross day boundary",
            "due_at": "2026-09-30T23:30:00Z",
        }
        # Offset +02:00 pushes 23:30 UTC into the next day (Oct 1)
        row = format_jira_row(raw, offset=timedelta(hours=2))
        self.assertEqual(row["Due Date"], "2026-10-01")

    def test_convert_filter_and_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "tasks.json"
            out = Path(tmpdir) / "jira.csv"
            src.write_text(json.dumps([
                {"id": "1", "description": "Bug 1", "completed": False},
                {"id": "2", "description": "Bug 2", "completed": True},
            ]), encoding="utf-8")

            # Filter completed only
            cnt = convert([str(src)], str(out), status_filter="completed")
            self.assertEqual(cnt, 1)
            self.assertTrue(out.exists())

            with open(out, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["Summary"], "Bug 2")
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
                self.assertEqual(rows[0]["Summary"], "Bug 1")
                self.assertEqual(rows[0]["Status"], "To Do")

    def test_cli_parser(self):
        parser = build_parser()
        args = parser.parse_args([
            "out.csv",
            "in1.json",
            "in2.json",
            "--utc-offset", "+09:00",
            "--status", "pending",
            "--priority", "High",
            "--issue-type", "Bug",
            "--label", "mobile",
            "--force",
        ])
        self.assertEqual(args.destination, "out.csv")
        self.assertEqual(args.sources, ["in1.json", "in2.json"])
        self.assertEqual(args.utc_offset, timedelta(hours=9))
        self.assertEqual(args.status, "pending")
        self.assertEqual(args.priority, "High")
        self.assertEqual(args.issue_type, "Bug")
        self.assertEqual(args.labels, ["mobile"])
        self.assertTrue(args.force)


if __name__ == "__main__":
    unittest.main()
