"""Tests for the conversations_to_html recipe."""

from datetime import datetime, timedelta, timezone
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_html.py"
spec = importlib.util.spec_from_file_location("conversations_to_html", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
c2html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2html)


class TestConversationsToHTML(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.sample_convs = [
            {
                "id": "conv_01",
                "started_at": "2026-10-01T09:00:00Z",
                "finished_at": "2026-10-01T09:30:00Z",
                "structured": {
                    "title": "Quarterly Planning & Review",
                    "category": "work",
                },
                "folder_name": "Planning",
                "source": "desktop",
                "language": "en",
            },
            {
                "id": "conv_02",
                "started_at": "2026-10-01T23:30:00Z",
                "finished_at": "2026-10-02T00:15:00Z",
                "structured": {
                    "title": "Late Night Discussion",
                    "category": "ideas",
                },
                "folder_name": None,
                "source": "omi",
                "language": "en",
            },
            {
                "id": "conv_03_undated",
                "started_at": None,
                "finished_at": None,
                "structured": {
                    "title": "Draft Voice Memo",
                    "category": "notes",
                },
                "folder_name": "Drafts",
                "source": "mobile",
                "language": "en",
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_text_sanitization(self):
        self.assertEqual(c2html.text("Simple text"), "Simple text")
        self.assertEqual(c2html.text(None), "")
        self.assertEqual(c2html.text("Line\nBreak\tand   spaces"), "Line Break and spaces")
        # Control codes like \x07 and \x00 must be dropped
        sanitized = c2html.text("Hello\x00World\x07!")
        self.assertEqual(sanitized, "HelloWorld!")
        # Noncharacters U+FFFE and U+FFFF must be dropped
        nonchars = c2html.text("Test\ufffeand\uffffdone")
        self.assertEqual(nonchars, "Testanddone")

    def test_parse_time(self):
        dt = c2html.parse_time("2026-10-01T09:00:00Z")
        self.assertEqual(dt, datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc))

        dt_offset = c2html.parse_time("2026-10-01T11:00:00+02:00")
        self.assertEqual(dt_offset, datetime(2026, 10, 1, 9, 0, 0, tzinfo=timezone.utc))

        self.assertIsNone(c2html.parse_time("not-a-date"))
        self.assertIsNone(c2html.parse_time(None))

    def test_parse_offset(self):
        self.assertEqual(c2html.parse_offset("+09:00"), timedelta(hours=9))
        self.assertEqual(c2html.parse_offset("-05:30"), -timedelta(hours=5, minutes=30))
        self.assertEqual(c2html.parse_offset("+00:00"), timedelta(0))

        with self.assertRaises(ValueError):
            c2html.parse_offset("+15:00")
        with self.assertRaises(ValueError):
            c2html.parse_offset("+09:65")
        with self.assertRaises(ValueError):
            c2html.parse_offset("invalid")

    def test_format_duration(self):
        self.assertEqual(c2html.format_duration(0), "0 min")
        self.assertEqual(c2html.format_duration(30), "< 1 min")
        self.assertEqual(c2html.format_duration(1800), "30 min")
        self.assertEqual(c2html.format_duration(3600), "1h")
        self.assertEqual(c2html.format_duration(5400), "1h 30m")

    def test_unwrap_conversations_envelopes(self):
        for key in ("conversations", "items", "data", "results"):
            envelope = {key: self.sample_convs}
            items = c2html.unwrap_conversations(envelope, "test")
            self.assertEqual(len(items), 3)

        # Bare list
        self.assertEqual(len(c2html.unwrap_conversations(self.sample_convs, "test")), 3)

        # Single dict
        single = {"id": "single", "structured": {"title": "One"}}
        self.assertEqual(len(c2html.unwrap_conversations(single, "test")), 1)

        # Non-conversation dict returns empty list
        self.assertEqual(len(c2html.unwrap_conversations({"error": "not found"}, "test")), 0)

        with self.assertRaises(ValueError):
            c2html.unwrap_conversations("invalid string", "test")

    def test_load_and_deduplication(self):
        f1 = self.tmp / "c1.json"
        f2 = self.tmp / "c2.json"
        f1.write_text(json.dumps(self.sample_convs[:2]), encoding="utf-8")
        f2.write_text(json.dumps(self.sample_convs[1:]), encoding="utf-8")

        loaded = c2html.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 3)
        self.assertIn("conv_01", loaded)
        self.assertIn("conv_02", loaded)
        self.assertIn("conv_03_undated", loaded)

    def test_rows_by_day_grouping_and_timezone_shift(self):
        convs_dict = {c["id"]: c for c in self.sample_convs}

        # UTC grouping
        days_utc, undated = c2html.rows_by_day(convs_dict, timedelta(0))
        self.assertIn("2026-10-01", days_utc)
        self.assertEqual(len(days_utc["2026-10-01"]), 2)
        self.assertEqual(len(undated), 1)

        # +02:00 timezone shift: conv_02 at 23:30Z rolls over to 2026-10-02 01:30
        days_shifted, _ = c2html.rows_by_day(convs_dict, timedelta(hours=2))
        self.assertIn("2026-10-01", days_shifted)
        self.assertIn("2026-10-02", days_shifted)
        self.assertEqual(len(days_shifted["2026-10-01"]), 1)
        self.assertEqual(len(days_shifted["2026-10-02"]), 1)

    def test_build_report_valid_html_and_xss_escaping(self):
        xss_conv = {
            "id": "conv_xss",
            "started_at": "2026-10-01T14:00:00Z",
            "finished_at": "2026-10-01T14:30:00Z",
            "structured": {
                "title": "Discussion with <script>alert(1)</script> & Team > Leads",
                "category": "dev & ops",
            },
            "folder_name": "Folder <A>",
            "source": "web",
            "language": "en",
        }
        convs_dict = {c["id"]: c for c in self.sample_convs + [xss_conv]}
        html = c2html.build_report(
            convs_dict,
            offset=timedelta(0),
            offset_label="+00:00",
            report_title="Team <Sync> & Review",
        )

        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("<title>Team &lt;Sync&gt; &amp; Review</title>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt; &amp; Team &gt; Leads", html)
        self.assertIn("Folder &lt;A&gt;", html)
        self.assertIn("dev &amp; ops", html)
        self.assertIn("Conversations", html)
        self.assertIn("Active Days", html)
        self.assertIn("Undated", html)

    def test_empty_report(self):
        html = c2html.build_report({}, offset=timedelta(0), report_title="Empty Report")
        self.assertIn("<!DOCTYPE html>", html)
        self.assertIn("No conversations found in the exported data.", html)
        self.assertIn('<div class="num">0</div>', html)

    def test_convert_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "report.html"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        count = c2html.convert([str(src)], destination=str(dest))
        self.assertEqual(count, 3)
        self.assertTrue(dest.exists())
        orig_content = dest.read_bytes()

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            c2html.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        count2 = c2html.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(count2, 3)

        # No leftover .tmp_conversations_html_* files exist after successful replace
        tmp_files = list(self.tmp.glob(".tmp_conversations_html_*"))
        self.assertEqual(tmp_files, [])

        # Failing tmp write in overwrite mode cleans up temporary file and leaves destination intact
        real_open = Path.open

        def failing_tmp_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            if ".tmp_conversations_html_" in self_path.name:
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk write failed"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_tmp_open):
            with self.assertRaises(OSError):
                c2html.convert([str(src)], destination=str(dest), overwrite=True)

        self.assertEqual(dest.read_bytes(), orig_content)
        self.assertEqual(list(self.tmp.glob(".tmp_conversations_html_*")), [])

    def test_failed_write_cleans_up_destination(self):
        src = self.tmp / "input_err.json"
        dest = self.tmp / "err.html"
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
                c2html.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_main_cli_execution(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_report.html"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        ret = c2html.main([
            str(src),
            "-o", str(dest),
            "--utc-offset", "+09:00",
            "--title", "CLI Standup Report",
        ])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        text = dest.read_text(encoding="utf-8")
        self.assertIn("CLI Standup Report", text)

    def test_main_broken_pipe_error(self):
        src = self.tmp / "cli_pipe.json"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        orig_fd = os.dup(sys.stdout.fileno())
        try:
            with patch("sys.stdout.buffer.write", side_effect=BrokenPipeError):
                ret = c2html.main([str(src), "-o", "-"])
                self.assertEqual(ret, 1)
        finally:
            os.dup2(orig_fd, sys.stdout.fileno())
            os.close(orig_fd)

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_convs).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = c2html.load(["-"])
            self.assertEqual(len(loaded), 3)

    def test_main_overwrite_refusal(self):
        src = self.tmp / "cli_refuse_src.json"
        dest = self.tmp / "cli_refuse_dest.html"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")
        dest.write_text("existing content", encoding="utf-8")

        with self.assertRaises(SystemExit) as ctx:
            c2html.main([str(src), "-o", str(dest)])
        self.assertIn("Refusing to overwrite", str(ctx.exception))
        self.assertEqual(dest.read_text(encoding="utf-8"), "existing content")

    def test_main_invalid_utc_offset(self):
        src = self.tmp / "cli_bad_offset.json"
        dest = self.tmp / "cli_bad_offset.html"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        with self.assertRaises(SystemExit) as ctx:
            c2html.main([str(src), "-o", str(dest), "--utc-offset", "invalid"])
        self.assertIn("UTC offset must match", str(ctx.exception))

    def test_main_negative_utc_offset_forms(self):
        src = self.tmp / "cli_neg_offset.json"
        dest1 = self.tmp / "cli_neg_offset_1.html"
        dest2 = self.tmp / "cli_neg_offset_2.html"
        src.write_text(json.dumps(self.sample_convs), encoding="utf-8")

        ret1 = c2html.main([str(src), "-o", str(dest1), "--utc-offset=-05:00"])
        self.assertEqual(ret1, 0)
        self.assertTrue(dest1.exists())

        ret2 = c2html.main([str(src), "-o", str(dest2), "--utc-offset", "-05:00"])
        self.assertEqual(ret2, 0)
        self.assertTrue(dest2.exists())

    def test_conversation_id_lone_surrogate_sanitization(self):
        surrogate_data = [{
            "id": "conv_\ud800_test",
            "title": "Surrogate Test",
            "category": "work",
            "started_at": "2026-10-01T12:00:00Z",
            "finished_at": "2026-10-01T12:30:00Z",
        }]
        src = self.tmp / "surrogate_id.json"
        dest = self.tmp / "surrogate_id.html"
        src.write_text(json.dumps(surrogate_data), encoding="utf-8")

        ret = c2html.main([str(src), "-o", str(dest)])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        self.assertIn("conv__test", dest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
