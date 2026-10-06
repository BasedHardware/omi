import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

recipe_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_ics.py"
spec = importlib.util.spec_from_file_location("conversations_to_ics", recipe_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

convert = module.convert
fold = module.fold
ics_text = module.ics_text
ics_datetime = module.ics_datetime
strip_surrogates = module.strip_surrogates


class TestConversationsToIcs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_basic_conversation_creates_vevent(self):
        src = self.tmp / "input.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps([
            {
                "id": "conv-101",
                "started_at": "2026-10-10T15:00:00Z",
                "finished_at": "2026-10-10T15:45:00Z",
                "structured": {"title": "Team Sync", "category": "Work"}
            }
        ]), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        self.assertEqual(skipped, 0)
        content = dst.read_text(encoding="utf-8")
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("BEGIN:VEVENT", content)
        self.assertIn("UID:omi-conversation-conv-101@omi-cli", content)
        self.assertIn("SUMMARY:Team Sync", content)
        self.assertIn("DTSTART:20261010T150000Z", content)
        self.assertIn("DTEND:20261010T154500Z", content)
        self.assertIn("Category: Work", content)
        self.assertIn("END:VEVENT", content)
        self.assertIn("END:VCALENDAR", content)

    def test_fallback_duration_when_finished_at_missing(self):
        src = self.tmp / "input.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps([
            {
                "id": "conv-102",
                "started_at": "2026-10-10T10:00:00Z",
                "finished_at": None,
                "structured": {"title": "Quick Chat"}
            }
        ]), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        content = dst.read_text(encoding="utf-8")
        self.assertIn("DTSTART:20261010T100000Z", content)
        self.assertIn("DTEND:20261010T103000Z", content)  # +30 mins default

    def test_items_without_start_are_skipped(self):
        src = self.tmp / "input.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps([
            {"id": "conv-1", "started_at": None},
            {"id": "conv-2", "started_at": "2026-10-12T12:00:00Z"}
        ]), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        self.assertEqual(skipped, 1)

    def test_surrogate_protection(self):
        src = self.tmp / "input.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps([
            {
                "id": "c-\ud800",
                "started_at": "2026-10-10T08:00:00Z",
                "structured": {"title": "Title with surrogate \ud800"}
            }
        ]), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        content = dst.read_text(encoding="utf-8")
        self.assertNotIn("\ud800", content)
        self.assertIn("Title with surrogate ", content)

    def test_envelope_unwrapping(self):
        src = self.tmp / "env.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps({
            "conversations": [
                {
                    "id": "env-conv",
                    "started_at": "2026-10-10T09:00:00Z",
                    "structured": {"title": "Envelope Conversation"}
                }
            ]
        }), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        content = dst.read_text(encoding="utf-8")
        self.assertIn("Envelope Conversation", content)

    def test_refuse_overwrite_existing_file(self):
        dst = self.tmp / "existing.ics"
        dst.write_text("existing", encoding="utf-8")
        src = self.tmp / "input.json"
        src.write_text(json.dumps([]), encoding="utf-8")
        with self.assertRaises(FileExistsError):
            convert(str(src), str(dst))

    def test_cli_invocation(self):
        src = self.tmp / "cli_input.json"
        dst = self.tmp / "cli_output.ics"
        src.write_text(json.dumps([
            {
                "id": "cli-conv",
                "started_at": "2026-10-11T11:00:00Z",
                "structured": {"title": "CLI Conv"}
            }
        ]), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(recipe_path), str(src), str(dst)],
                              capture_output=True, text=True, check=True)
        self.assertIn("1 event(s) written", proc.stdout)
        self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
