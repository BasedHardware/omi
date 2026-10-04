"""Unit tests for conversations -> Org-mode exporter.

Pins envelope unwrapping, UTF-8 BOM handling, properties drawer,
action item completion normalization, speaker transcripts, Org syntax escaping,
and single-file vs directory export modes.
"""

from __future__ import annotations

from datetime import timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_org.py"
spec = importlib.util.spec_from_file_location("conversations_to_org", script_path)
c2org = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2org)

JST = timezone(timedelta(hours=9))
UTC = timezone.utc


class TestConversationsToOrg(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_extract_conversations_envelopes(self):
        sample = {"id": "c1", "structured": {"title": "Test 1"}}

        # Bare list
        self.assertEqual(len(c2org.extract_conversations([sample])), 1)

        # Envelopes
        self.assertEqual(len(c2org.extract_conversations({"conversations": [sample]})), 1)
        self.assertEqual(len(c2org.extract_conversations({"items": [sample]})), 1)
        self.assertEqual(len(c2org.extract_conversations({"data": [sample]})), 1)

        # Single dict
        self.assertEqual(len(c2org.extract_conversations(sample)), 1)

        # Empty envelopes
        self.assertEqual(len(c2org.extract_conversations({"conversations": []})), 0)
        self.assertEqual(len(c2org.extract_conversations({"items": []})), 0)
        self.assertEqual(len(c2org.extract_conversations({})), 0)
        self.assertEqual(len(c2org.extract_conversations([])), 0)

    def test_utf8_bom_handling(self):
        sample = [{"id": "c1", "structured": {"title": "BOM Test", "overview": "Summary text"}}]
        bom_payload = "\ufeff" + json.dumps(sample)
        source = self.tmp / "bom.json"
        source.write_bytes(bom_payload.encode("utf-8"))

        dest = self.tmp / "bom.org"
        count = c2org.convert(source, dest, UTC)
        self.assertEqual(count, 1)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* BOM Test", content)
        self.assertIn("Summary text", content)

    def test_properties_drawer_and_metadata(self):
        sample = [{
            "id": "conv-uuid-1234",
            "started_at": "2026-09-28T10:00:00Z",
            "created_at": "2026-09-28T10:30:00Z",
            "source": "omi-device",
            "structured": {
                "title": "Strategy Sync",
                "category": "business",
                "overview": "Quarterly planning sync",
            }
        }]
        source = self.tmp / "meta.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "meta.org"
        c2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("* Strategy Sync", content)
        self.assertIn(":PROPERTIES:", content)
        self.assertIn(":OMI_ID: conv-uuid-1234", content)
        self.assertIn(":DATE: [2026-09-28 Mon 10:00]", content)
        self.assertIn(":CATEGORY: business", content)
        self.assertIn(":SOURCE: omi-device", content)
        self.assertIn(":CREATED: [2026-09-28 Mon 10:30]", content)
        self.assertIn(":END:", content)
        self.assertIn("** Summary\nQuarterly planning sync", content)

    def test_action_items_completion_normalization(self):
        sample = [{
            "id": "c1",
            "structured": {
                "title": "Action Items Task",
                "action_items": [
                    {"description": "Task 1", "completed": True},
                    {"description": "Task 2", "completed": "true"},
                    {"description": "Task 3", "completed": "yes"},
                    {"description": "Task 4", "completed": "1"},
                    {"description": "Task 5", "completed": "done"},
                    {"description": "Task 6", "completed": "completed"},
                    {"description": "Task 7", "completed": False},
                    {"description": "Task 8", "completed": "false"},
                    {"description": "Task 9", "completed": "no"},
                    {"description": "Task 10", "completed": "0"},
                    {"description": "Task 11", "completed": None},
                ]
            }
        }]
        source = self.tmp / "actions.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "actions.org"
        c2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("** Action Items", content)
        self.assertIn("- [X] Task 1", content)
        self.assertIn("- [X] Task 2", content)
        self.assertIn("- [X] Task 3", content)
        self.assertIn("- [X] Task 4", content)
        self.assertIn("- [X] Task 5", content)
        self.assertIn("- [X] Task 6", content)
        self.assertIn("- [ ] Task 7", content)
        self.assertIn("- [ ] Task 8", content)
        self.assertIn("- [ ] Task 9", content)
        self.assertIn("- [ ] Task 10", content)
        self.assertIn("- [ ] Task 11", content)

    def test_speaker_transcripts_and_timestamps(self):
        sample = [{
            "id": "c1",
            "structured": {"title": "Podcast Recording"},
            "transcript_segments": [
                {"speaker": 0, "start": 15.5, "text": "Welcome to the show."},
                {"speaker": "Alice", "start": 95.0, "text": "Glad to be here."},
                {"speaker": 1, "start": 3665.0, "text": "An hour later wrap-up."},
            ]
        }]
        source = self.tmp / "transcript.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "transcript.org"
        c2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        self.assertIn("** Transcript", content)
        self.assertIn("- [00:15] *Speaker 0:* Welcome to the show.", content)
        self.assertIn("- [01:35] *Alice:* Glad to be here.", content)
        self.assertIn("- [01:01:05] *Speaker 1:* An hour later wrap-up.", content)

    def test_syntax_escaping_in_headings(self):
        sample = [{
            "id": "c1",
            "structured": {
                "title": "[#A] High Priority :meeting:",
            }
        }]
        source = self.tmp / "escape.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "escape.org"
        c2org.convert(source, dest, UTC)

        content = dest.read_text(encoding="utf-8")
        # Priority cookie escaped with ZWSP at start
        self.assertIn(c2org.ZWSP + "[#A]", content)
        # Heading tags escaped with ZWSP at end
        self.assertIn(":meeting:" + c2org.ZWSP, content)

        # Direct heading_text unit tests matching conventions
        self.assertEqual(
            c2org.heading_text("[#A] Sync with Team :standup:"),
            c2org.ZWSP + "[#A] Sync with Team :standup:" + c2org.ZWSP
        )
        self.assertEqual(
            c2org.heading_text("Meeting at <2026-09-28 Mon>"),
            "Meeting at <" + c2org.ZWSP + "2026-09-28 Mon>"
        )

    def test_directory_export_mode(self):
        samples = [
            {"id": "conv1", "started_at": "2026-09-28T09:00:00Z", "structured": {"title": "Meeting One"}},
            {"id": "conv2", "started_at": "2026-09-28T14:00:00Z", "structured": {"title": "Meeting Two"}},
        ]
        source = self.tmp / "multi.json"
        source.write_text(json.dumps(samples), encoding="utf-8")

        out_dir = self.tmp / "org_notes"
        count = c2org.convert(source, out_dir, UTC, output_dir=out_dir)
        self.assertEqual(count, 2)

        files = list(out_dir.glob("*.org"))
        self.assertEqual(len(files), 2)
        for f in files:
            content = f.read_text(encoding="utf-8")
            self.assertIn("# -*- mode: org; coding: utf-8 -*-", content)
            self.assertTrue(":OMI_ID:" in content)

    def test_no_overwrite_guard(self):
        sample = [{"id": "c1", "structured": {"title": "Protected"}}]
        source = self.tmp / "test.json"
        source.write_text(json.dumps(sample), encoding="utf-8")

        dest = self.tmp / "protected.org"
        dest.write_text("Existing sensitive data", encoding="utf-8")

        # By default without force/overwrite, single file must raise FileExistsError
        with self.assertRaises(FileExistsError):
            c2org.convert(source, dest, UTC, overwrite=False)

        # Verify content was preserved
        self.assertEqual(dest.read_text(encoding="utf-8"), "Existing sensitive data")

        # With overwrite=True, it succeeds
        c2org.convert(source, dest, UTC, overwrite=True)
        self.assertIn("* Protected", dest.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
