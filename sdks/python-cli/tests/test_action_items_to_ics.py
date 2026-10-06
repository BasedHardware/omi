import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

recipe_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_ics.py"
spec = importlib.util.spec_from_file_location("action_items_to_ics", recipe_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

convert = module.convert
fold = module.fold
ics_text = module.ics_text
ics_datetime = module.ics_datetime
strip_surrogates = module.strip_surrogates
is_completed = module.is_completed


class TestActionItemsToIcs(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_basic_due_item_creates_vevent(self):
        src = self.tmp / "input.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps([
            {"id": "task-1", "description": "Dentist Appointment", "due_at": "2026-10-15T14:00:00Z", "completed": False}
        ]), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        self.assertEqual(skipped, 0)
        content = dst.read_text(encoding="utf-8")
        self.assertIn("BEGIN:VCALENDAR", content)
        self.assertIn("BEGIN:VEVENT", content)
        self.assertIn("UID:omi-action-task-1@omi-cli", content)
        self.assertIn("SUMMARY:Dentist Appointment", content)
        self.assertIn("DTSTART:20261015T140000Z", content)
        self.assertIn("DTEND:20261015T143000Z", content)
        self.assertIn("STATUS:CONFIRMED", content)
        self.assertIn("END:VEVENT", content)
        self.assertIn("END:VCALENDAR", content)

    def test_items_without_due_at_are_skipped(self):
        src = self.tmp / "input.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps([
            {"id": "1", "description": "No deadline task", "due_at": None},
            {"id": "2", "description": "Has deadline", "due_at": "2026-11-01T10:00:00Z"}
        ]), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        self.assertEqual(skipped, 1)
        content = dst.read_text(encoding="utf-8")
        self.assertIn("Has deadline", content)
        self.assertNotIn("No deadline task", content)

    def test_surrogate_protection(self):
        src = self.tmp / "input.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps([
            {"id": "surr-1\ud800", "description": "Surrogate task \ud800 text", "due_at": "2026-10-20T12:00:00Z"}
        ]), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        content = dst.read_text(encoding="utf-8")
        self.assertNotIn("\ud800", content)
        self.assertIn("Surrogate task  text", content)

    def test_rfc5545_line_folding(self):
        long_line = "SUMMARY:" + "A" * 100
        folded = fold(long_line)
        self.assertTrue(len(folded) > 1)
        for part in folded:
            self.assertLessEqual(len(part.encode("utf-8")), 75)
        # Unfolded content matches original
        unfolded = folded[0] + "".join(p[1:] for p in folded[1:])
        self.assertEqual(unfolded, long_line)

    def test_rfc5545_property_escaping(self):
        raw = "Buy milk, eggs; and bread \\ urgent\nNext line"
        escaped = ics_text(raw)
        self.assertEqual(escaped, "Buy milk\\, eggs\\; and bread \\\\ urgent\\nNext line")

    def test_envelope_unwrapping(self):
        src = self.tmp / "env.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps({
            "action_items": [
                {"id": "env-1", "description": "Envelope task", "due_at": "2026-12-01T09:00:00Z"}
            ]
        }), encoding="utf-8")
        written, skipped = convert(str(src), str(dst))
        self.assertEqual(written, 1)
        content = dst.read_text(encoding="utf-8")
        self.assertIn("Envelope task", content)

    def test_loosely_typed_completed_status(self):
        src = self.tmp / "status.json"
        dst = self.tmp / "output.ics"
        src.write_text(json.dumps([
            {"id": "t1", "description": "Done task", "due_at": "2026-10-01T00:00:00Z", "completed": "done"},
            {"id": "t2", "description": "Numeric task", "due_at": "2026-10-02T00:00:00Z", "completed": 1},
            {"id": "t3", "description": "Open task", "due_at": "2026-10-03T00:00:00Z", "completed": "false"}
        ]), encoding="utf-8")
        written, _ = convert(str(src), str(dst))
        self.assertEqual(written, 3)
        content = dst.read_text(encoding="utf-8")
        self.assertIn("STATUS:COMPLETED", content)
        self.assertIn("STATUS:CONFIRMED", content)

    def test_refuse_overwrite_existing_file(self):
        dst = self.tmp / "existing.ics"
        dst.write_text("pre-existing content", encoding="utf-8")
        src = self.tmp / "input.json"
        src.write_text(json.dumps([]), encoding="utf-8")
        with self.assertRaises(FileExistsError):
            convert(str(src), str(dst))

    def test_cli_invocation(self):
        src = self.tmp / "cli_input.json"
        dst = self.tmp / "cli_output.ics"
        src.write_text(json.dumps([
            {"id": "cli-1", "description": "CLI test", "due_at": "2026-10-30T10:00:00Z"}
        ]), encoding="utf-8")
        proc = subprocess.run([sys.executable, str(recipe_path), str(src), str(dst)],
                              capture_output=True, text=True, check=True)
        self.assertIn("1 event(s) written", proc.stdout)
        self.assertTrue(dst.exists())


if __name__ == "__main__":
    unittest.main()
