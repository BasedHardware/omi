import json
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "examples"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from action_items_to_html import (
    load,
    parse_offset,
    parse_time,
    report,
    convert,
    text,
)


class TestActionItemsToHtml(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)
        self.html_path = self.dir_path / "test_report.html"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+07:00"), timedelta(hours=7))
        self.assertEqual(parse_offset("-05:00"), timedelta(hours=-5))
        self.assertEqual(parse_offset("+00:00"), timedelta(0))
        with self.assertRaises(ValueError):
            parse_offset("invalid")
        with self.assertRaises(ValueError):
            parse_offset("+15:00")

    def test_parse_time(self):
        dt = parse_time("2026-09-24T08:00:00Z")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.hour, 8)
        self.assertIsNone(parse_time(None))
        self.assertIsNone(parse_time(""))
        self.assertIsNone(parse_time("not-a-date"))

    def test_load_and_deduplication(self):
        items1 = [
            {"id": "task_1", "description": "Buy milk", "completed": False, "created_at": "2026-09-24T08:00:00Z"},
            {"id": "task_2", "description": "Submit PR", "completed": True, "created_at": "2026-09-24T09:00:00Z"},
        ]
        items2 = [
            {"id": "task_2", "description": "Submit PR Updated", "completed": True, "created_at": "2026-09-24T09:00:00Z"},
            {"id": "task_3", "description": "Write documentation", "completed": False, "created_at": "2026-09-24T10:00:00Z"},
        ]

        f1 = self.dir_path / "p1.json"
        f2 = self.dir_path / "p2.json"
        f1.write_text(json.dumps(items1), encoding="utf-8")
        f2.write_text(json.dumps(items2), encoding="utf-8")

        loaded = load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 3)
        self.assertEqual(loaded["task_2"]["description"], "Submit PR Updated")

    def test_report_html_generation(self):
        items = {
            "task_1": {
                "id": "task_1",
                "description": "Fix <script>alert(1)</script> vulnerability",
                "completed": False,
                "created_at": "2026-09-24T08:00:00Z",
                "due_at": "2026-09-25T18:00:00Z",
                "conversation_id": "conv_999",
            },
            "task_2": {
                "id": "task_2",
                "description": "Clean codebase",
                "completed": True,
                "created_at": "2026-09-24T09:00:00Z",
                "due_at": None,
                "conversation_id": None,
            },
        }

        html_out = report(items, timedelta(hours=7), "+07:00")
        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("Omi Action Items Report", html_out)
        self.assertIn("Total Action Items: 2", html_out)
        self.assertIn("Pending: 1", html_out)
        self.assertIn("Completed: 1", html_out)
        # Verify XSS HTML escaping
        self.assertNotIn("<script>alert(1)</script>", html_out)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html_out)

    def test_convert_creates_file_and_protects_overwrite(self):
        items = [{"id": "task_1", "description": "Test task", "completed": False}]
        f_json = self.dir_path / "tasks.json"
        f_json.write_text(json.dumps(items), encoding="utf-8")

        convert([str(f_json)], str(self.html_path), timedelta(0), "")
        self.assertTrue(self.html_path.exists())
        self.assertGreater(self.html_path.stat().st_size, 0)

        # Second run should raise FileExistsError
        with self.assertRaises(FileExistsError):
            convert([str(f_json)], str(self.html_path), timedelta(0), "")

    def test_path_traversal_rejected(self):
        f_json = self.dir_path / "tasks.json"
        f_json.write_text(json.dumps([{"id": "1", "description": "a"}]), encoding="utf-8")

        with self.assertRaises(ValueError):
            convert([str(f_json)], str(self.dir_path / ".." / "out.html"), timedelta(0), "")


if __name__ == "__main__":
    unittest.main()
