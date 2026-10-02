"""Tests for the conversations_to_ics recipe."""

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

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_ics.py"
spec = importlib.util.spec_from_file_location("conversations_to_ics", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
c2ics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2ics)


class TestConversationsToICS(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample_convs = [
            {
                "id": "conv_01",
                "started_at": "2026-10-01T09:00:00Z",
                "finished_at": "2026-10-01T09:45:00Z",
                "structured": {
                    "title": "Quarterly Planning; Strategy, & Review",
                    "category": "work",
                },
                "folder_name": "Planning",
                "source": "desktop",
            },
            {
                "id": "conv_02",
                "started_at": "2026-10-01T14:00:00Z",
                "finished_at": None,
                "structured": {
                    "title": "Quick Standup Sync",
                    "category": "ideas",
                },
                "source": "omi",
            },
            {
                "id": "conv_03_undated",
                "started_at": None,
                "finished_at": None,
                "structured": {
                    "title": "Undated Voice Note",
                    "category": "notes",
                },
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ics_text_escaping(self):
        self.assertEqual(c2ics.ics_text("Plain text"), "Plain text")
        self.assertEqual(c2ics.ics_text(None), "")
        escaped = c2ics.ics_text("A\\B; C, D\r\nLine 2\nLine 3")
        self.assertEqual(escaped, "A\\\\B\\; C\\, D\\nLine 2\\nLine 3")
        nonchars = c2ics.ics_text("Clean\x00\ufffeword\uffff")
        self.assertEqual(nonchars, "Cleanword")

    def test_parse_time_and_stamp(self):
        dt = c2ics.parse_time("2026-10-02T12:00:00Z")
        self.assertEqual(dt, datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(c2ics.stamp(dt), "20261002T120000Z")

        dt_offset = c2ics.parse_time("2026-10-02T14:00:00+02:00")
        self.assertEqual(dt_offset, datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc))
        self.assertEqual(c2ics.stamp(dt_offset), "20261002T120000Z")

        self.assertIsNone(c2ics.parse_time("not-a-date"))
        self.assertIsNone(c2ics.parse_time(None))

    def test_fold_rfc5545(self):
        short_line = "SUMMARY:Short line"
        self.assertEqual(c2ics.fold(short_line), [short_line])

        long_line = "DESCRIPTION:" + "x" * 100
        folded = c2ics.fold(long_line)
        self.assertGreater(len(folded), 1)
        self.assertTrue(all(len(part.encode("utf-8")) <= 75 for part in folded))
        self.assertTrue(folded[1].startswith(" "))

        unicode_line = "SUMMARY:" + "日本語テスト" * 15
        folded_u = c2ics.fold(unicode_line)
        self.assertTrue(all(len(p.encode("utf-8")) <= 75 for p in folded_u))
        rejoined = folded_u[0] + "".join(p[1:] for p in folded_u[1:])
        self.assertEqual(rejoined, unicode_line)

    def test_unwrap_conversations_envelopes(self):
        for key in ("conversations", "items", "data", "results"):
            envelope = {key: self.sample_convs}
            items = c2ics.unwrap_conversations(envelope, "test")
            self.assertEqual(len(items), 3)

        # Bare list
        self.assertEqual(len(c2ics.unwrap_conversations(self.sample_convs, "test")), 3)

        # Single dict
        single = {"id": "single", "structured": {"title": "One"}}
        self.assertEqual(len(c2ics.unwrap_conversations(single, "test")), 1)

        # Non-conversation dict returns empty list
        self.assertEqual(len(c2ics.unwrap_conversations({"error": "not found"}, "test")), 0)

        with self.assertRaises(ValueError):
            c2ics.unwrap_conversations("invalid string", "test")

    def test_load_and_deduplication(self):
        f1 = self.tmp / "c1.json"
        f2 = self.tmp / "c2.json"
        f1.write_text(json.dumps(self.sample_convs[:2]), encoding="utf-8")
        f2.write_text(json.dumps(self.sample_convs[1:]), encoding="utf-8")

        loaded = c2ics.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 3)
        self.assertIn("conv_01", loaded)
        self.assertIn("conv_02", loaded)
        self.assertIn("conv_03_undated", loaded)

    def test_build_ics_events_and_filtering(self):
        convs_dict = {c["id"]: c for c in self.sample_convs}

        # All events: 2 events with started_at, 1 skipped
        ics_text, written, skipped = c2ics.build_ics(convs_dict)
        self.assertEqual(written, 2)
        self.assertEqual(skipped, 1)
        self.assertIn("BEGIN:VCALENDAR", ics_text)
        self.assertIn("END:VCALENDAR", ics_text)
        self.assertIn("UID:omi-conversation-conv_01@omi-cli", ics_text)
        self.assertIn("STATUS:CONFIRMED", ics_text)
        self.assertIn("DTSTART:20261001T090000Z", ics_text)
        self.assertIn("DTEND:20261001T094500Z", ics_text)
        # Missing finished_at defaults to +30m
        self.assertIn("DTSTART:20261001T140000Z", ics_text)
        self.assertIn("DTEND:20261001T143000Z", ics_text)

        # Category filter: only 'work' category
        _, written_work, _ = c2ics.build_ics(convs_dict, category_filter="work")
        self.assertEqual(written_work, 1)

        # Custom default length (45 minutes)
        ics_45, _, _ = c2ics.build_ics(convs_dict, default_length_mins=45)
        self.assertIn("DTSTART:20261001T140000Z", ics_45)
        self.assertIn("DTEND:20261001T144500Z", ics_45)

    def test_convert_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "convs.ics"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        written, skipped = c2ics.convert([str(src)], destination=str(dest))
        self.assertEqual(written, 2)
        self.assertEqual(skipped, 1)
        self.assertTrue(dest.exists())
        orig_content = dest.read_bytes()

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            c2ics.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        written2, _ = c2ics.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(written2, 2)

        # No leftover .tmp_conversations_ics_* files exist after successful replace
        tmp_files = list(self.tmp.glob(".tmp_conversations_ics_*"))
        self.assertEqual(tmp_files, [])

        # Failing tmp write in overwrite mode cleans up temporary file and leaves destination intact
        real_open = Path.open

        def failing_tmp_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            if ".tmp_conversations_ics_" in self_path.name:
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk write failed"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_tmp_open):
            with self.assertRaises(OSError):
                c2ics.convert([str(src)], destination=str(dest), overwrite=True)

        self.assertEqual(dest.read_bytes(), orig_content)
        self.assertEqual(list(self.tmp.glob(".tmp_conversations_ics_*")), [])

    def test_failed_write_cleans_up_destination(self):
        src = self.tmp / "input_err.json"
        dest = self.tmp / "err.ics"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        real_open = Path.open

        def failing_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            mode = kwargs.get("mode", args[0] if args else "r")
            if "xb" in mode and str(self_path) == str(dest):
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk full"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_open):
            with self.assertRaises(OSError):
                c2ics.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_main_cli_execution(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_convs.ics"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        ret = c2ics.main([
            str(src),
            "-o", str(dest),
            "--category", "work",
            "--default-length", "45",
            "--calendar-name", "My Omi Sessions",
        ])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        content = dest.read_text(encoding="utf-8")
        self.assertIn("X-WR-CALNAME:My Omi Sessions", content)
        self.assertIn("DTSTART:20261001T090000Z", content)
        self.assertIn("DTEND:20261001T094500Z", content)

    def test_main_broken_pipe_error(self):
        src = self.tmp / "cli_pipe.json"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        orig_fd = os.dup(sys.stdout.fileno())
        try:
            with patch("sys.stdout.buffer.write", side_effect=BrokenPipeError):
                ret = c2ics.main([str(src), "-o", "-"])
                self.assertEqual(ret, 1)
        finally:
            os.dup2(orig_fd, sys.stdout.fileno())
            os.close(orig_fd)

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_convs).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = c2ics.load(["-"])
            self.assertEqual(len(loaded), 3)


if __name__ == "__main__":
    unittest.main()
