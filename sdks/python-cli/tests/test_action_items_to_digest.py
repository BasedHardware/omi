"""Tests for the action_items_to_digest recipe."""

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_digest.py"
spec = importlib.util.spec_from_file_location("action_items_to_digest", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
ai2digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2digest)


class TestActionItemsToDigest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        self.sample_items = [
            {
                "id": "act_01_done",
                "description": "Submit quarterly budget report",
                "completed": True,
                "due_at": "2026-09-30T17:00:00Z",
                "created_at": "2026-09-25T09:00:00Z",
            },
            {
                "id": "act_02_overdue",
                "description": "Fix memory leak in background worker",
                "completed": False,
                "due_at": "2026-10-01T10:00:00Z",  # 1 day overdue relative to self.now
                "created_at": "2026-09-28T09:00:00Z",
            },
            {
                "id": "act_03_upcoming",
                "description": "Prepare release notes for v2.4",
                "completed": False,
                "due_at": "2026-10-05T15:00:00Z",  # In 3 days
                "created_at": "2026-10-01T09:00:00Z",
            },
            {
                "id": "act_04_undated",
                "description": "Explore speculative prototype ideas",
                "completed": False,
                "due_at": None,
                "created_at": "2026-10-01T09:00:00Z",
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_is_completed_normalization(self):
        self.assertTrue(ai2digest.is_completed(True))
        self.assertTrue(ai2digest.is_completed(1))
        self.assertTrue(ai2digest.is_completed("done"))
        self.assertTrue(ai2digest.is_completed("COMPLETED"))
        self.assertTrue(ai2digest.is_completed("yes"))
        self.assertFalse(ai2digest.is_completed(False))
        self.assertFalse(ai2digest.is_completed(0))
        self.assertFalse(ai2digest.is_completed("open"))
        self.assertFalse(ai2digest.is_completed(None))

    def test_parse_offset_boundaries(self):
        self.assertEqual(ai2digest.parse_offset("+09:00"), timedelta(hours=9))
        self.assertEqual(ai2digest.parse_offset("-05:30"), timedelta(hours=-5, minutes=-30))
        self.assertEqual(ai2digest.parse_offset("+14:00"), timedelta(hours=14))
        self.assertEqual(ai2digest.parse_offset("-14:00"), timedelta(hours=-14))
        with self.assertRaises(ValueError):
            ai2digest.parse_offset("invalid")
        with self.assertRaises(ValueError):
            ai2digest.parse_offset("+15:00")
        with self.assertRaises(ValueError):
            ai2digest.parse_offset("+05:70")

    def test_clean_markdown_cell(self):
        self.assertEqual(ai2digest.clean_markdown_cell("Simple text"), "Simple text")
        self.assertEqual(ai2digest.clean_markdown_cell("Pipe | inside"), "Pipe \\| inside")
        self.assertEqual(ai2digest.clean_markdown_cell("Line\nBreak"), "Line Break")
        self.assertEqual(ai2digest.clean_markdown_cell(None), "")
        self.assertEqual(
            ai2digest.clean_markdown_cell("Review *budget* & [link] `#1`"),
            "Review \\*budget\\* & \\[link\\] \\`\\#1\\`",
        )

    def test_load_and_envelope_unwrapping(self):
        for key in ("action_items", "items", "data", "results"):
            envelope = {key: self.sample_items}
            f = self.tmp / f"env_{key}.json"
            f.write_text(json.dumps(envelope), encoding="utf-8")
            loaded = ai2digest.load([str(f)])
            self.assertEqual(len(loaded), 4)

        # Bare dict
        bare_f = self.tmp / "bare.json"
        bare_f.write_text(json.dumps({"id": "single", "description": "Single task"}), encoding="utf-8")
        loaded_bare = ai2digest.load([str(bare_f)])
        self.assertEqual(len(loaded_bare), 1)
        self.assertIn("single", loaded_bare)

        # Numeric id coercion
        num_f = self.tmp / "numeric.json"
        num_f.write_text(json.dumps([{"id": 99, "description": "Num id"}]), encoding="utf-8")
        loaded_num = ai2digest.load([str(num_f)])
        self.assertIn("99", loaded_num)

    def test_digest_metrics_calculation(self):
        items_dict = {it["id"]: it for it in self.sample_items}
        md = ai2digest.build_digest(items_dict, now=self.now)

        self.assertIn("# Omi Action Items Digest", md)
        self.assertIn("**Total Tasks:** 4", md)
        self.assertIn("**Completed:** 1 (25.0%)", md)
        self.assertIn("**Open:** 3", md)
        self.assertIn("**Overdue:** 1", md)

        # Check Overdue section
        self.assertIn("## ⚠️ Overdue Tasks", md)
        self.assertIn("Fix memory leak in background worker", md)
        self.assertIn("(_overdue by 1 day_)", md)
        self.assertIn("act_02_overdue", md)

        # Check Upcoming section
        self.assertIn("## 📅 Upcoming Deadlines (Next 7 Days)", md)
        self.assertIn("Prepare release notes for v2.4", md)
        self.assertIn("act_03_upcoming", md)

        # Check Due Date table
        self.assertIn("## Due Date Schedule", md)
        self.assertIn("| 2026-09-30 | 0 | 1 | 1 |", md)
        self.assertIn("| 2026-10-01 | 1 | 0 | 1 |", md)
        self.assertIn("| 2026-10-05 | 1 | 0 | 1 |", md)

    def test_overdue_partial_day_duration(self):
        item = {
            "id": "act_hours",
            "description": "Urgent task due 2h ago",
            "completed": False,
            "due_at": "2026-10-02T10:00:00Z",
        }
        md = ai2digest.build_digest({"act_hours": item}, now=self.now)
        self.assertIn("(_overdue by less than a day_)", md)

    def test_empty_export_handling(self):
        md = ai2digest.build_digest({})
        self.assertIn("_No action items found matching the export criteria._", md)

    def test_status_filtering(self):
        items_dict = {it["id"]: it for it in self.sample_items}
        open_md = ai2digest.build_digest(items_dict, status_filter="open", now=self.now)
        self.assertIn("**Total Tasks:** 3", open_md)
        self.assertIn("**Completed:** 0", open_md)
        self.assertNotIn("Submit quarterly budget report", open_md)

        done_md = ai2digest.build_digest(items_dict, status_filter="completed", now=self.now)
        self.assertIn("**Total Tasks:** 1", done_md)
        self.assertIn("**Completed:** 1", done_md)
        self.assertNotIn("Fix memory leak", done_md)

    def test_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "digest.md"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        count = ai2digest.convert([str(src)], destination=str(dest))
        self.assertEqual(count, 4)
        self.assertTrue(dest.exists())

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            ai2digest.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        count2 = ai2digest.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(count2, 4)

    def test_failed_write_cleans_up_destination(self):
        src = self.tmp / "input_err.json"
        dest = self.tmp / "digest_err.md"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        real_open = Path.open

        def failing_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            mode = kwargs.get("mode", args[0] if args else "r")
            if "xb" in mode and str(self_path) == str(dest):
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk full"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_open):
            with self.assertRaises(OSError):
                ai2digest.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_items).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = ai2digest.load(["-"])
            self.assertEqual(len(loaded), 4)

    def test_main_cli_execution(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_digest.md"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        ret = ai2digest.main([str(src), "-o", str(dest), "--utc-offset", "+09:00"])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        content = dest.read_text(encoding="utf-8")
        self.assertIn("# Omi Action Items Digest", content)


if __name__ == "__main__":
    unittest.main()
