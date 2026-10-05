import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

# Load action_items_to_ics example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "action_items_to_ics.py"
spec = importlib.util.spec_from_file_location("action_items_to_ics", script_path)
a2i = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a2i)

convert = a2i.convert
fold = a2i.fold
ics_datetime = a2i.ics_datetime
ics_text = a2i.ics_text
stamp = a2i.stamp


class TestActionItemsToICS(unittest.TestCase):
    def test_ics_text_escaping_and_coercion(self):
        self.assertEqual(ics_text(None), "")
        self.assertEqual(ics_text("Call client"), "Call client")
        self.assertEqual(
            ics_text("Task; meeting, notes \\ follow-up \r\n tomorrow"),
            "Task\\; meeting\\, notes \\\\ follow-up \\n tomorrow",
        )
        self.assertEqual(ics_text("lone\rcarriage\rreturn"), "lone\\ncarriage\\nreturn")
        self.assertEqual(ics_text(42), "42")
        self.assertEqual(ics_text(False), "False")
        self.assertEqual(ics_text(["a", "b"]), '["a"\\, "b"]')

    def test_ics_datetime_parsing(self):
        self.assertIsNone(ics_datetime(None))
        self.assertIsNone(ics_datetime(""))
        self.assertIsNone(ics_datetime("not-a-date"))

        parsed_utc = ics_datetime("2026-10-05T09:00:00Z")
        self.assertIsNotNone(parsed_utc)
        self.assertEqual(parsed_utc.year, 2026)
        self.assertEqual(parsed_utc.hour, 9)
        self.assertEqual(parsed_utc.tzinfo, timezone.utc)

        parsed_offset = ics_datetime("2026-10-05T06:00:00-03:00")
        self.assertIsNotNone(parsed_offset)
        self.assertEqual(parsed_offset.hour, 9)
        self.assertEqual(parsed_offset.tzinfo, timezone.utc)

    def test_stamp(self):
        dt = datetime(2026, 10, 5, 9, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(stamp(dt), "20261005T090000Z")

    def test_fold_line(self):
        short = "SUMMARY:Short task"
        self.assertEqual(fold(short), [short])

        long_line = "DESCRIPTION:" + "B" * 120
        folded = fold(long_line)
        self.assertGreater(len(folded), 1)
        self.assertTrue(all(len(part.encode("utf-8")) <= 75 for part in folded))
        reconstructed = folded[0] + "".join(part[1:] for part in folded[1:])
        self.assertEqual(reconstructed, long_line)

    def test_fold_multibyte_safety(self):
        multibyte = "SUMMARY:" + "ñ" * 50
        folded = fold(multibyte)
        for part in folded:
            self.assertLessEqual(len(part.encode("utf-8")), 75)
        reconstructed = folded[0] + "".join(part[1:] for part in folded[1:])
        self.assertEqual(reconstructed, multibyte)

    def test_convert_success_and_statuses(self):
        items = [
            {
                "id": "act-1",
                "description": "Send follow-up email",
                "due_at": "2026-10-05T14:00:00Z",
                "created_at": "2026-10-04T12:00:00Z",
                "completed": False,
                "conversation_id": "conv-100",
            },
            {
                "id": "act-2",
                "description": "Review pull request",
                "due_at": "2026-10-05T16:00:00Z",
                "created_at": None,
                "completed": True,
            },
            {
                "id": "act-3",
                "description": "Undated task",
                "due_at": None,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "action_items.json"
            dst = Path(tmpdir) / "action_items.ics"
            src.write_text(json.dumps(items), encoding="utf-8")

            written, skipped = convert(src, dst)
            self.assertEqual(written, 2)
            self.assertEqual(skipped, 1)
            self.assertTrue(dst.exists())

            content = dst.read_text(encoding="utf-8")
            self.assertIn("BEGIN:VCALENDAR", content)
            self.assertIn("X-WR-CALNAME:Omi action items", content)
            self.assertNotIn("act-3", content)
            self.assertIn("END:VCALENDAR", content)

            # Separate into individual VEVENT blocks to assert properties per event
            events = [e for e in content.split("BEGIN:VEVENT") if "END:VEVENT" in e]
            self.assertEqual(len(events), 2)

            # Event 1: pending
            event_1 = next(e for e in events if "UID:omi-action-act-1@omi-cli" in e)
            self.assertIn("SUMMARY:Send follow-up email", event_1)
            self.assertIn("STATUS:CONFIRMED", event_1)
            self.assertIn("DTSTART:20261005T140000Z", event_1)
            self.assertIn("DTEND:20261005T143000Z", event_1)
            self.assertIn("CREATED:20261004T120000Z", event_1)
            self.assertIn("Conversation: conv-100", event_1)

            # Event 2: completed
            event_2 = next(e for e in events if "UID:omi-action-act-2@omi-cli" in e)
            self.assertIn("SUMMARY:[DONE] Review pull request", event_2)
            self.assertIn("STATUS:CONFIRMED", event_2)
            self.assertIn("DTSTART:20261005T160000Z", event_2)
            self.assertIn("DTEND:20261005T163000Z", event_2)

    def test_convert_exclusive_creation_and_validation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "action_items.json"
            dst = Path(tmpdir) / "action_items.ics"
            src.write_text("[]", encoding="utf-8")
            dst.write_text("already exists", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                convert(src, dst)

            src.write_text('{"error": "not a list"}', encoding="utf-8")
            dst_new = Path(tmpdir) / "new.ics"
            with self.assertRaises(ValueError):
                convert(src, dst_new)


if __name__ == "__main__":
    unittest.main()
