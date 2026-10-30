import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

recipe_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_html.py"
spec = importlib.util.spec_from_file_location("conversations_to_html", recipe_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

convert = module.convert
report = module.report
parse_offset = module.parse_offset
strip_surrogates = module.strip_surrogates
text = module.text


class TestConversationsToHtml(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_basic_report_generation(self):
        src = self.tmp / "convs.json"
        dst = self.tmp / "report.html"
        src.write_text(json.dumps([
            {
                "id": "c1",
                "started_at": "2026-09-15T10:00:00Z",
                "finished_at": "2026-09-15T10:30:00Z",
                "structured": {"title": "Sprint Planning", "category": "Work"},
                "folder_name": "Projects",
                "source": "desktop",
                "language": "en"
            }
        ]), encoding="utf-8")
        convert([str(src)], str(dst))
        self.assertTrue(dst.exists())
        content = dst.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("Omi conversation report", content)
        self.assertIn("Sprint Planning", content)
        self.assertIn("2026-09-15", content)
        self.assertIn("30 min", content)
        self.assertIn("Work", content)
        self.assertIn("c1", content)

    def test_undated_conversations_bucketed(self):
        src = self.tmp / "convs.json"
        dst = self.tmp / "report.html"
        src.write_text(json.dumps([
            {
                "id": "c_undated",
                "started_at": None,
                "structured": {"title": "Undated Meeting"}
            }
        ]), encoding="utf-8")
        convert([str(src)], str(dst))
        content = dst.read_text(encoding="utf-8")
        self.assertIn("Undated", content)
        self.assertIn("Undated Meeting", content)

    def test_multi_source_deduplication(self):
        src1 = self.tmp / "p1.json"
        src2 = self.tmp / "p2.json"
        dst = self.tmp / "report.html"
        src1.write_text(json.dumps([
            {"id": "c1", "started_at": "2026-09-15T10:00:00Z", "structured": {"title": "Meeting 1"}}
        ]), encoding="utf-8")
        src2.write_text(json.dumps([
            {"id": "c1", "started_at": "2026-09-15T10:00:00Z", "structured": {"title": "Meeting 1"}},
            {"id": "c2", "started_at": "2026-09-15T11:00:00Z", "structured": {"title": "Meeting 2"}}
        ]), encoding="utf-8")
        convert([str(src1), str(src2)], str(dst))
        content = dst.read_text(encoding="utf-8")
        self.assertIn("Conversations: 2", content)

    def test_surrogate_protection(self):
        src = self.tmp / "convs.json"
        dst = self.tmp / "report.html"
        src.write_text(json.dumps([
            {
                "id": "c_surr\ud800",
                "started_at": "2026-09-15T10:00:00Z",
                "structured": {"title": "Title with surrogate \ud800"}
            }
        ]), encoding="utf-8")
        convert([str(src)], str(dst))
        content = dst.read_text(encoding="utf-8")
        self.assertNotIn("\ud800", content)
        self.assertIn("Title with surrogate", content)

    def test_envelope_unwrapping(self):
        src = self.tmp / "env.json"
        dst = self.tmp / "report.html"
        src.write_text(json.dumps({
            "conversations": [
                {"id": "env1", "started_at": "2026-09-15T10:00:00Z", "structured": {"title": "Wrapped Conv"}}
            ]
        }), encoding="utf-8")
        convert([str(src)], str(dst))
        content = dst.read_text(encoding="utf-8")
        self.assertIn("Wrapped Conv", content)

    def test_parse_offset(self):
        self.assertEqual(parse_offset("+09:00"), timedelta(hours=9))
        self.assertEqual(parse_offset("-05:30"), timedelta(hours=-5, minutes=-30))
        with self.assertRaises(ValueError):
            parse_offset("+15:00")
        with self.assertRaises(ValueError):
            parse_offset("invalid")

    def test_refuse_overwrite_existing_file(self):
        dst = self.tmp / "report.html"
        dst.write_text("existing", encoding="utf-8")
        src = self.tmp / "convs.json"
        src.write_text(json.dumps([]), encoding="utf-8")
        with self.assertRaises(FileExistsError):
            convert([str(src)], str(dst))

    def test_cli_invocation(self):
        src = self.tmp / "cli_input.json"
        dst = self.tmp / "cli_output.html"
        src.write_text(json.dumps([
            {"id": "cli1", "started_at": "2026-09-15T10:00:00Z", "structured": {"title": "CLI Report"}}
        ]), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(recipe_path), "--utc-offset", "+00:00", str(dst), str(src)],
                              capture_output=True, text=True, check=True)
        self.assertIn("report written to", proc.stdout)
        self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
