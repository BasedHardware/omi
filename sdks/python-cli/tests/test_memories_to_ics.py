"""Hermetic unit tests for the memories_to_ics recipe."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

REPO_CLI_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_CLI_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_CLI_ROOT))

from examples.memories_to_ics import (
    DEFAULT_EVENT_DURATION,
    PRODID,
    _generate_synthetic_id,
    deduplicate_memories,
    extract_memories,
    fold_line,
    generate_ics,
    ics_datetime,
    ics_escape,
    main,
    memory_to_vevent,
    parse_memory_input,
    stamp_utc,
    write_ics,
)


class TestMemoriesToIcsUnit(unittest.TestCase):
    """Hermetic unit tests for memories to iCalendar conversion functions."""

    def test_ics_escape_special_chars(self) -> None:
        """Verify RFC 5545 §3.3.11 character escaping."""
        raw = 'Special: \\ backslash, ; semicolon, , comma, and \n newline \r\n double.'
        escaped = ics_escape(raw)
        self.assertEqual(
            escaped,
            'Special: \\\\ backslash\\, \\; semicolon\\, \\, comma\\, and \\n newline \\n double.',
        )

    def test_ics_escape_non_string_types(self) -> None:
        """Verify non-string types are converted safely without crashing."""
        self.assertEqual(ics_escape(None), "")
        self.assertEqual(ics_escape(12345), "12345")
        self.assertEqual(ics_escape(["a", "b"]), '["a"\\, "b"]')
        self.assertEqual(ics_escape({"key": "val"}), '{"key": "val"}')

    def test_ics_datetime_parsing(self) -> None:
        """Verify parsing of various ISO 8601 timestamps into aware UTC datetimes."""
        # Standard ISO-8601 with Z
        dt1 = ics_datetime("2026-09-25T14:30:00Z")
        self.assertIsNotNone(dt1)
        self.assertEqual(stamp_utc(dt1), "20260925T143000Z")

        # Offset timestamp (+02:00)
        dt2 = ics_datetime("2026-09-25T16:30:00+02:00")
        self.assertIsNotNone(dt2)
        self.assertEqual(stamp_utc(dt2), "20260925T143000Z")

        # Date only (YYYY-MM-DD)
        dt3 = ics_datetime("2026-09-25")
        self.assertIsNotNone(dt3)
        self.assertEqual(stamp_utc(dt3), "20260925T000000Z")

        # Invalid or empty values
        self.assertIsNone(ics_datetime(""))
        self.assertIsNone(ics_datetime("not-a-date"))
        self.assertIsNone(ics_datetime(None))
        self.assertIsNone(ics_datetime(123456789))
        self.assertIsNone(ics_datetime("1e1000"))

    def test_fold_line_rfc5545_compliance(self) -> None:
        """Verify RFC 5545 §3.1 line folding and multi-byte UTF-8 boundary safety."""
        # Short line requires no folding
        short_line = "SUMMARY:Short text"
        self.assertEqual(fold_line(short_line), [short_line])

        # Long ASCII line folds at 75 octets with continuation space
        long_line = "DESCRIPTION:" + "A" * 100
        folded = fold_line(long_line)
        self.assertGreater(len(folded), 1)
        for part in folded[1:]:
            self.assertTrue(part.startswith(" "))
        for part in folded:
            self.assertLessEqual(len(part.encode("utf-8")), 75)

        # Multi-byte UTF-8 (CJK characters, 3 bytes each)
        cjk_line = "SUMMARY:" + "学习人工智能记忆管理与模型微调实战" * 4
        folded_cjk = fold_line(cjk_line)
        self.assertGreater(len(folded_cjk), 1)
        # Verify decoding round-trip preserves content exactly
        reconstructed = folded_cjk[0] + "".join(p[1:] for p in folded_cjk[1:])
        self.assertEqual(reconstructed, cjk_line)

    def test_extract_memories_envelopes(self) -> None:
        """Verify unwrap of multiple envelope structures and BOM resilience."""
        sample_mem = {"id": "mem_1", "content": "Learned Python asyncio."}

        # Bare list
        self.assertEqual(extract_memories([sample_mem]), [sample_mem])

        # Wrapped in "memories"
        self.assertEqual(extract_memories({"memories": [sample_mem]}), [sample_mem])

        # Wrapped in "items"
        self.assertEqual(extract_memories({"items": [sample_mem]}), [sample_mem])

        # Wrapped in "data"
        self.assertEqual(extract_memories({"data": [sample_mem]}), [sample_mem])

        # Wrapped in "results"
        self.assertEqual(extract_memories({"results": [sample_mem]}), [sample_mem])

        # Single dictionary
        self.assertEqual(extract_memories(sample_mem), [sample_mem])

        # Non-dict / invalid elements filtered
        self.assertEqual(extract_memories([sample_mem, "not-a-dict", 123]), [sample_mem])
        self.assertEqual(extract_memories(None), [])
        self.assertEqual(extract_memories("invalid"), [])

    def test_deduplicate_memories_latest_wins(self) -> None:
        """Verify deduplication by ID selects the most recently updated entry."""
        older = {
            "id": "mem_1",
            "content": "Old content",
            "created_at": "2026-09-01T10:00:00Z",
            "updated_at": "2026-09-01T10:00:00Z",
        }
        newer = {
            "id": "mem_1",
            "content": "Updated content",
            "created_at": "2026-09-01T10:00:00Z",
            "updated_at": "2026-09-05T12:00:00Z",
        }
        other = {
            "id": "mem_2",
            "content": "Other memory",
            "created_at": "2026-09-02T10:00:00Z",
        }

        # newer later in list
        deduped = deduplicate_memories([older, newer, other])
        self.assertEqual(len(deduped), 2)
        self.assertEqual(deduped[0]["content"], "Updated content")

        # newer earlier in list
        deduped2 = deduplicate_memories([newer, older, other])
        self.assertEqual(len(deduped2), 2)
        self.assertEqual(deduped2[0]["content"], "Updated content")

    def test_memory_to_vevent_standard(self) -> None:
        """Verify VEVENT generation with all metadata attributes."""
        mem = {
            "id": "mem_42",
            "content": "User prefers dark mode in all development environments.\nSecond line notes.",
            "category": "preferences",
            "tags": ["ui", "editor"],
            "visibility": "private",
            "created_at": "2026-09-25T10:00:00Z",
            "updated_at": "2026-09-26T15:00:00Z",
        }
        lines = memory_to_vevent(mem, now_stamp="20260927T000000Z")
        self.assertIsNotNone(lines)
        event_text = "\n".join(lines)

        self.assertIn("BEGIN:VEVENT", event_text)
        self.assertIn("UID:omi-memory-mem_42@omi-cli", event_text)
        self.assertIn("DTSTART:20260925T100000Z", event_text)
        # Default duration is 15 minutes
        self.assertIn("DTEND:20260925T101500Z", event_text)
        self.assertIn("SUMMARY:User prefers dark mode in all development environments.", event_text)
        self.assertIn("DESCRIPTION:User prefers dark mode in all development environments.\\nSecond line notes.", event_text)
        self.assertIn("Memory ID: mem_42", event_text)
        self.assertIn("Category: preferences", event_text)
        self.assertIn("Tags: ui\\, editor", event_text)
        self.assertIn("Visibility: private", event_text)
        self.assertIn("STATUS:CONFIRMED", event_text)
        self.assertIn("CATEGORIES:Omi,Memories,Preferences,ui,editor", event_text)
        self.assertIn("END:VEVENT", event_text)

    def test_memory_to_vevent_custom_duration(self) -> None:
        """Verify custom duration calculation."""
        mem = {
            "id": "mem_custom",
            "content": "Quick note",
            "created_at": "2026-09-25T10:00:00Z",
        }
        from datetime import timedelta
        lines = memory_to_vevent(mem, now_stamp="20260927T000000Z", duration=timedelta(minutes=45))
        self.assertIsNotNone(lines)
        event_text = "\n".join(lines)
        self.assertIn("DTSTART:20260925T100000Z", event_text)
        self.assertIn("DTEND:20260925T104500Z", event_text)

    def test_memory_missing_created_at_is_skipped(self) -> None:
        """Verify records without a valid timestamp return None (safe skip)."""
        mem_no_time = {"id": "mem_invalid", "content": "No timestamp available"}
        self.assertIsNone(memory_to_vevent(mem_no_time, now_stamp="20260927T000000Z"))

        mem_bad_time = {"id": "mem_bad", "content": "Bad time", "created_at": "invalid-time"}
        self.assertIsNone(memory_to_vevent(mem_bad_time, now_stamp="20260927T000000Z"))

    def test_synthetic_id_fallback(self) -> None:
        """Verify anonymous memory generates a deterministic synthetic ID."""
        mem = {
            "content": "Secret note without id",
            "category": "work",
            "created_at": "2026-09-25T10:00:00Z",
        }
        syn_id = _generate_synthetic_id(mem)
        self.assertTrue(syn_id.startswith("syn_"))

        # Re-generating with identical content produces identical hash
        self.assertEqual(syn_id, _generate_synthetic_id(mem))

        lines = memory_to_vevent(mem, now_stamp="20260927T000000Z")
        self.assertIsNotNone(lines)
        self.assertIn(f"UID:omi-memory-{syn_id}@omi-cli", "\n".join(lines))

    def test_long_summary_truncation(self) -> None:
        """Verify summary truncates long content and appends ellipsis."""
        long_text = "This is an extremely long single line of memory text that goes on and on beyond sixty characters."
        mem = {
            "id": "mem_long",
            "content": long_text,
            "created_at": "2026-09-25T10:00:00Z",
        }
        lines = memory_to_vevent(mem, now_stamp="20260927T000000Z")
        self.assertIsNotNone(lines)
        summary_line = [l for l in lines if l.startswith("SUMMARY:")][0]
        self.assertTrue(summary_line.endswith("..."))
        self.assertLessEqual(len(summary_line), 80)

    def test_generate_ics_filtering(self) -> None:
        """Verify category and tag filtering during iCalendar generation."""
        memories = [
            {"id": "1", "content": "Work memory", "category": "work", "tags": ["code"], "created_at": "2026-09-25T10:00:00Z"},
            {"id": "2", "content": "Personal memory", "category": "personal", "tags": ["family"], "created_at": "2026-09-25T11:00:00Z"},
            {"id": "3", "content": "Skill memory", "category": "skills", "tags": ["code", "python"], "created_at": "2026-09-25T12:00:00Z"},
            {"id": "4", "content": "Missing time", "category": "work"},
        ]

        # Category filter
        ics_cat, written_cat, skipped_cat = generate_ics(memories, category_filter=["work", "skills"])
        self.assertEqual(written_cat, 2)
        self.assertIn("UID:omi-memory-1@omi-cli", ics_cat)
        self.assertIn("UID:omi-memory-3@omi-cli", ics_cat)
        self.assertNotIn("UID:omi-memory-2@omi-cli", ics_cat)

        # Tag filter
        ics_tag, written_tag, skipped_tag = generate_ics(memories, tag_filter=["python"])
        self.assertEqual(written_tag, 1)
        self.assertIn("UID:omi-memory-3@omi-cli", ics_tag)
        self.assertNotIn("UID:omi-memory-1@omi-cli", ics_tag)

    def test_write_ics_path_traversal_refusal(self) -> None:
        """Verify path traversal attempts are strictly refused."""
        with self.assertRaises(ValueError) as ctx:
            write_ics("../forbidden.ics", "BEGIN:VCALENDAR\nEND:VCALENDAR")
        self.assertIn("Path traversal detected", str(ctx.exception))

        with self.assertRaises(ValueError):
            write_ics("nested/../../evil.ics", "BEGIN:VCALENDAR\nEND:VCALENDAR")

    def test_write_ics_atomic_and_overwrite_protection(self) -> None:
        """Verify safe overwrite protection and atomic replacement."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir) / "output.ics"
            dest.write_text("initial content", encoding="utf-8")

            # Overwrite refused without force
            with self.assertRaises(FileExistsError):
                write_ics(str(dest), "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", force=False)
            self.assertEqual(dest.read_text(encoding="utf-8"), "initial content")

            # Overwrite permitted with force
            write_ics(str(dest), "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n", force=True)
            self.assertEqual(dest.read_bytes(), b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")

    def test_cli_stdin_to_stdout_pipeline(self) -> None:
        """Verify full CLI pipeline reading from stdin and writing to stdout."""
        sample_json = json.dumps([
            {
                "id": "cli_mem",
                "content": "Pipeline memory stream test",
                "category": "cli",
                "created_at": "2026-09-25T10:00:00Z",
            }
        ])

        buffer_capture = io.BytesIO()
        fake_stdout = mock.MagicMock()
        fake_stdout.buffer = buffer_capture

        with mock.patch("sys.stdin", io.StringIO(sample_json)):
            with mock.patch("sys.stdout", fake_stdout):
                exit_code = main(["-", "-o", "-"])
                self.assertEqual(exit_code, 0)

        output = buffer_capture.getvalue().decode("utf-8")
        self.assertIn("BEGIN:VCALENDAR", output)
        self.assertIn("UID:omi-memory-cli_mem@omi-cli", output)
        self.assertIn("SUMMARY:Pipeline memory stream test", output)
        self.assertTrue(output.endswith("\r\n"))

    def test_cli_file_export_and_options(self) -> None:
        """Verify CLI execution reading from files and writing to output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            in_file = Path(tmpdir) / "input.json"
            out_file = Path(tmpdir) / "output.ics"

            in_file.write_text(
                json.dumps([
                    {
                        "id": "file_mem_1",
                        "content": "File export memory",
                        "category": "work",
                        "created_at": "2026-09-25T14:00:00Z",
                    }
                ]),
                encoding="utf-8",
            )

            stderr_capture = io.StringIO()
            with mock.patch("sys.stderr", stderr_capture):
                exit_code = main([
                    str(in_file),
                    "-o",
                    str(out_file),
                    "--name",
                    "Custom Work Calendar",
                    "--duration-minutes",
                    "30",
                ])
                self.assertEqual(exit_code, 0)

            self.assertTrue(out_file.exists())
            content = out_file.read_text(encoding="utf-8")
            self.assertIn("X-WR-CALNAME:Custom Work Calendar", content)
            self.assertIn("DTSTART:20260925T140000Z", content)
            self.assertIn("DTEND:20260925T143000Z", content)
            self.assertIn("Successfully exported 1 memory event", stderr_capture.getvalue())

    def test_empty_input_file_handling(self) -> None:
        """Verify empty input file returns empty list and produces valid calendar shell."""
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_file = Path(tmpdir) / "empty.json"
            empty_file.write_text("   \n", encoding="utf-8")
            memories = parse_memory_input(str(empty_file))
            self.assertEqual(memories, [])

            ics_text, written, skipped = generate_ics(memories)
            self.assertEqual(written, 0)
            self.assertEqual(skipped, 0)
            self.assertIn("BEGIN:VCALENDAR", ics_text)
            self.assertIn("END:VCALENDAR", ics_text)

    def test_windows_path_traversal_refusal(self) -> None:
        """Verify Windows backslash path traversal is refused."""
        with self.assertRaises(ValueError):
            write_ics("..\\windows_evil.ics", "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n")

    def test_cli_file_not_found_error_exit(self) -> None:
        """Verify CLI exits with code 1 when input file is missing."""
        stderr_capture = io.StringIO()
        with mock.patch("sys.stderr", stderr_capture):
            exit_code = main(["non_existent_file.json", "-o", "-"])
            self.assertEqual(exit_code, 1)
        self.assertIn("Input file not found", stderr_capture.getvalue())

    def test_tags_none_and_empty_filtering(self) -> None:
        """Verify memory with None or empty string in tags list does not fail."""
        mem = {
            "id": "mem_tags",
            "content": "Tag test memory",
            "tags": [None, "", "valid_tag"],
            "created_at": "2026-09-25T10:00:00Z",
        }
        lines = memory_to_vevent(mem, now_stamp="20260927T000000Z")
        self.assertIsNotNone(lines)
        event_text = "\n".join(lines)
        self.assertIn("Tags: valid_tag", event_text)
        self.assertIn("CATEGORIES:Omi,Memories,valid_tag", event_text)

    def test_datetime_overflow_clamping(self) -> None:
        """Verify datetime at max year boundary clamps without throwing OverflowError."""
        mem = {
            "id": "mem_future",
            "content": "Future knowledge",
            "created_at": "9999-12-31T23:55:00Z",
        }
        lines = memory_to_vevent(mem, now_stamp="20260927T000000Z")
        self.assertIsNotNone(lines)
        event_text = "\n".join(lines)
        self.assertIn("DTSTART:99991231T235500Z", event_text)
        self.assertIn("DTEND:99991231T235959Z", event_text)

    def test_deduplicate_timezone_aware_comparison(self) -> None:
        """Verify timezone-aware datetimes sort correctly regardless of string representation."""
        earlier_utc = {
            "id": "mem_tz",
            "content": "Earlier UTC version",
            "created_at": "2026-09-25T12:00:00Z",
        }
        later_offset = {
            "id": "mem_tz",
            "content": "Later +02:00 version",
            "created_at": "2026-09-25T15:00:00+02:00",  # 13:00 UTC (1 hour later than 12:00 UTC)
        }
        deduped = deduplicate_memories([earlier_utc, later_offset])
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["content"], "Later +02:00 version")

    def test_deduplicate_anonymous_memories_merge_identical(self) -> None:
        """Verify identical memories without ID are deduplicated to avoid duplicate UIDs."""
        anon1 = {
            "content": "Same anonymous fact",
            "category": "personal",
            "created_at": "2026-09-25T10:00:00Z",
        }
        anon2 = {
            "content": "Same anonymous fact",
            "category": "personal",
            "created_at": "2026-09-25T10:00:00Z",
        }
        deduped = deduplicate_memories([anon1, anon2])
        self.assertEqual(len(deduped), 1)

        ics_text, written, skipped = generate_ics(deduped)
        self.assertEqual(written, 1)
        self.assertEqual(ics_text.count("BEGIN:VEVENT"), 1)


if __name__ == "__main__":
    unittest.main()
