"""Tests for the action_items_to_ics recipe."""

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_ics.py"
spec = importlib.util.spec_from_file_location("action_items_to_ics", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
ai2ics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ai2ics)


class TestActionItemsToICS(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample_items = [
            {
                "id": "act_01_done",
                "description": "Submit quarterly budget report; review numbers, & check totals",
                "completed": True,
                "due_at": "2026-09-30T17:00:00Z",
                "created_at": "2026-09-25T09:00:00Z",
                "conversation_id": "conv_991",
            },
            {
                "id": "act_02_open",
                "description": "Fix memory leak in background worker\nCheck logs first",
                "completed": False,
                "due_at": "2026-10-01T10:00:00Z",
                "created_at": "2026-09-28T09:00:00Z",
            },
            {
                "id": "act_03_nodue",
                "description": "Speculative idea without due date",
                "completed": False,
                "due_at": None,
                "created_at": "2026-10-01T11:00:00Z",
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_is_completed_normalization(self):
        self.assertTrue(ai2ics.is_completed(True))
        self.assertTrue(ai2ics.is_completed(1))
        self.assertTrue(ai2ics.is_completed("done"))
        self.assertTrue(ai2ics.is_completed("COMPLETED"))
        self.assertTrue(ai2ics.is_completed("yes"))
        self.assertTrue(ai2ics.is_completed("x"))
        self.assertFalse(ai2ics.is_completed(False))
        self.assertFalse(ai2ics.is_completed(0))
        self.assertFalse(ai2ics.is_completed("open"))
        self.assertFalse(ai2ics.is_completed(None))

    def test_ics_text_escaping(self):
        self.assertEqual(ai2ics.ics_text("Plain text"), "Plain text")
        self.assertEqual(ai2ics.ics_text(None), "")
        # Semicolons, commas, backslashes, and newlines must be escaped
        escaped = ai2ics.ics_text("A\\B; C, D\r\nLine 2\nLine 3")
        self.assertEqual(escaped, "A\\\\B\\; C\\, D\\nLine 2\\nLine 3")
        # Control characters and noncharacters dropped
        nonchars = ai2ics.ics_text("Clean\x00\ufffeword\uffff")
        self.assertEqual(nonchars, "Cleanword")

    def test_parse_time_and_stamp(self):
        dt = ai2ics.parse_time("2026-10-02T12:00:00Z")
        self.assertEqual(dt, datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(ai2ics.stamp(dt), "20261002T120000Z")

        dt_offset = ai2ics.parse_time("2026-10-02T14:00:00+02:00")
        self.assertEqual(dt_offset, datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(ai2ics.stamp(dt_offset), "20261002T120000Z")

        self.assertIsNone(ai2ics.parse_time("not-a-date"))
        self.assertIsNone(ai2ics.parse_time(None))

    def test_fold_rfc5545(self):
        short_line = "SUMMARY:Short line"
        self.assertEqual(ai2ics.fold(short_line), [short_line])

        # Long line requiring folding at 75 octets
        long_line = "DESCRIPTION:" + "x" * 100
        folded = ai2ics.fold(long_line)
        self.assertGreater(len(folded), 1)
        self.assertTrue(all(len(part.encode("utf-8")) <= 75 for part in folded))
        self.assertTrue(folded[1].startswith(" "))

        # Multi-byte UTF-8 character preservation across fold boundaries
        unicode_line = "SUMMARY:" + "日本語テスト" * 15
        folded_u = ai2ics.fold(unicode_line)
        self.assertTrue(all(len(p.encode("utf-8")) <= 75 for p in folded_u))
        # Rejoined string must reconstruct original text
        rejoined = folded_u[0] + "".join(p[1:] for p in folded_u[1:])
        self.assertEqual(rejoined, unicode_line)

    def test_unwrap_items_envelopes(self):
        for key in ("action_items", "items", "data", "results"):
            envelope = {key: self.sample_items}
            items = ai2ics.unwrap_items(envelope, "test")
            self.assertEqual(len(items), 3)

        # Bare list
        self.assertEqual(len(ai2ics.unwrap_items(self.sample_items, "test")), 3)

        # Bare single dict
        single = {"id": "single", "description": "Single task"}
        self.assertEqual(len(ai2ics.unwrap_items(single, "test")), 1)

        # Non-item dict returns empty list
        self.assertEqual(len(ai2ics.unwrap_items({"error": "not found"}, "test")), 0)

        with self.assertRaises(ValueError):
            ai2ics.unwrap_items("invalid string", "test")

    def test_load_and_deduplication(self):
        f1 = self.tmp / "f1.json"
        f2 = self.tmp / "f2.json"
        f1.write_text(json.dumps(self.sample_items[:2]), encoding="utf-8")
        f2.write_text(json.dumps(self.sample_items[1:]), encoding="utf-8")

        loaded = ai2ics.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 3)
        self.assertIn("act_01_done", loaded)
        self.assertIn("act_02_open", loaded)
        self.assertIn("act_03_nodue", loaded)

    def test_build_ics_events_and_filtering(self):
        items_dict = {it["id"]: it for it in self.sample_items}

        # All events: 2 events with due_at, 1 skipped
        ics_text, written, skipped = ai2ics.build_ics(items_dict, status_filter="all")
        self.assertEqual(written, 2)
        self.assertEqual(skipped, 1)
        self.assertIn("BEGIN:VCALENDAR", ics_text)
        self.assertIn("END:VCALENDAR", ics_text)
        self.assertIn("UID:omi-action-act_01_done@omi-cli", ics_text)
        self.assertIn("STATUS:COMPLETED", ics_text)
        self.assertIn("STATUS:CONFIRMED", ics_text)
        self.assertIn("DTSTART:20260930T170000Z", ics_text)
        self.assertIn("DTEND:20260930T173000Z", ics_text)

        # Open filter: only 1 open task with due date
        _, written_open, _ = ai2ics.build_ics(items_dict, status_filter="open")
        self.assertEqual(written_open, 1)

        # Completed filter: only 1 completed task with due date
        _, written_comp, _ = ai2ics.build_ics(items_dict, status_filter="completed")
        self.assertEqual(written_comp, 1)

        # Custom event length (60 minutes)
        ics_60, _, _ = ai2ics.build_ics(items_dict, event_length_mins=60)
        self.assertIn("DTSTART:20260930T170000Z", ics_60)
        self.assertIn("DTEND:20260930T180000Z", ics_60)

    def test_convert_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "calendar.ics"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        written, skipped = ai2ics.convert([str(src)], destination=str(dest))
        self.assertEqual(written, 2)
        self.assertEqual(skipped, 1)
        self.assertTrue(dest.exists())
        orig_content = dest.read_bytes()

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            ai2ics.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        written2, _ = ai2ics.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(written2, 2)

        # No leftover .tmp_action_items_ics_* files exist after successful replace
        tmp_files = list(self.tmp.glob(".tmp_action_items_ics_*"))
        self.assertEqual(tmp_files, [])

        # Failing tmp write in overwrite mode cleans up temporary file and leaves destination intact
        real_open = Path.open

        def failing_tmp_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            if ".tmp_action_items_ics_" in self_path.name:
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk write failed"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_tmp_open):
            with self.assertRaises(OSError):
                ai2ics.convert([str(src)], destination=str(dest), overwrite=True)

        self.assertEqual(dest.read_bytes(), orig_content)
        self.assertEqual(list(self.tmp.glob(".tmp_action_items_ics_*")), [])

    def test_failed_write_cleans_up_destination(self):
        src = self.tmp / "input_err.json"
        dest = self.tmp / "err.ics"
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
                ai2ics.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_main_cli_execution(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_cal.ics"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        ret = ai2ics.main([
            str(src),
            "-o", str(dest),
            "--status", "open",
            "--event-length", "45",
            "--calendar-name", "My Omi Calendar",
        ])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        content = dest.read_text(encoding="utf-8")
        self.assertIn("X-WR-CALNAME:My Omi Calendar", content)
        self.assertIn("DTSTART:20261001T100000Z", content)
        self.assertIn("DTEND:20261001T104500Z", content)

    def test_main_broken_pipe_error(self):
        src = self.tmp / "cli_pipe.json"
        src.write_text(json.dumps(self.sample_items), encoding="utf-8")

        orig_fd = os.dup(sys.stdout.fileno())
        try:
            with patch("sys.stdout.buffer.write", side_effect=BrokenPipeError):
                ret = ai2ics.main([str(src), "-o", "-"])
                self.assertEqual(ret, 1)
        finally:
            os.dup2(orig_fd, sys.stdout.fileno())
            os.close(orig_fd)

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_items).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = ai2ics.load(["-"])
            self.assertEqual(len(loaded), 3)


if __name__ == "__main__":
    unittest.main()
