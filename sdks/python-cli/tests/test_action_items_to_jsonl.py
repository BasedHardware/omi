"""Hermetic unit tests for action_items_to_jsonl converter recipe.

Validates schema normalization, boolean coercion, timestamp parsing, deduplication,
filtering, sorting, path-traversal prevention, atomic file writes, and CLI execution.

Zero external dependencies: 100% Python standard library only.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

# Dynamically import the example script from sdks/python-cli/examples/
EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "examples"
if str(EXAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLE_DIR))

import action_items_to_jsonl as converter


class TestUnwrapActionItems(unittest.TestCase):
    def test_bare_list(self) -> None:
        data = [
            {"id": "1", "description": "Item 1"},
            {"id": "2", "description": "Item 2"},
            "not-a-dict",
        ]
        unwrapped = converter.unwrap_action_items(data)
        self.assertEqual(len(unwrapped), 2)
        self.assertEqual(unwrapped[0]["id"], "1")
        self.assertEqual(unwrapped[1]["id"], "2")

    def test_envelopes(self) -> None:
        for env_key in ("action_items", "items", "data", "results"):
            with self.subTest(env_key=env_key):
                data = {env_key: [{"id": f"id_{env_key}", "description": f"desc_{env_key}"}]}
                unwrapped = converter.unwrap_action_items(data)
                self.assertEqual(len(unwrapped), 1)
                self.assertEqual(unwrapped[0]["id"], f"id_{env_key}")

    def test_single_dict(self) -> None:
        data = {"id": "single_1", "description": "Direct task"}
        unwrapped = converter.unwrap_action_items(data)
        self.assertEqual(len(unwrapped), 1)
        self.assertEqual(unwrapped[0]["id"], "single_1")

    def test_empty_and_invalid(self) -> None:
        self.assertEqual(converter.unwrap_action_items([]), [])
        self.assertEqual(converter.unwrap_action_items({}), [])
        self.assertEqual(converter.unwrap_action_items(None), [])
        self.assertEqual(converter.unwrap_action_items("some string"), [])


class TestNormalizeRecord(unittest.TestCase):
    def test_standard_record(self) -> None:
        raw = {
            "id": "act_101",
            "description": "  Ship release v1.0  ",
            "completed": False,
            "created_at": "2026-10-01T10:00:00Z",
            "updated_at": "2026-10-02T12:00:00Z",
            "due_date": "2026-10-05T18:00:00Z",
            "conversation_id": "conv_99",
        }
        rec = converter.normalize_record(raw)
        self.assertEqual(rec["id"], "act_101")
        self.assertEqual(rec["description"], "Ship release v1.0")
        self.assertIs(rec["completed"], False)
        self.assertEqual(rec["status"], "open")
        self.assertEqual(rec["created_at"], "2026-10-01T10:00:00Z")
        self.assertEqual(rec["updated_at"], "2026-10-02T12:00:00Z")
        self.assertEqual(rec["due_date"], "2026-10-05T18:00:00Z")
        self.assertEqual(rec["conversation_id"], "conv_99")

    def test_boolean_coercion(self) -> None:
        truthy_values = (True, "true", "TRUE", "True", "1", "yes", "completed", "done", 1)
        for val in truthy_values:
            with self.subTest(val=val):
                rec = converter.normalize_record({"id": "t", "completed": val})
                self.assertIs(rec["completed"], True)
                self.assertEqual(rec["status"], "completed")

        falsy_values = (False, "false", "FALSE", "False", "0", "no", "open", "pending", 0, "")
        for val in falsy_values:
            with self.subTest(val=val):
                rec = converter.normalize_record({"id": "f", "completed": val})
                self.assertIs(rec["completed"], False)
                self.assertEqual(rec["status"], "open")

    def test_status_fallback_when_completed_missing(self) -> None:
        rec1 = converter.normalize_record({"id": "s1", "status": "completed"})
        self.assertIs(rec1["completed"], True)
        self.assertEqual(rec1["status"], "completed")

        rec2 = converter.normalize_record({"id": "s2", "status": "open"})
        self.assertIs(rec2["completed"], False)
        self.assertEqual(rec2["status"], "open")

    def test_timestamp_parsing_variants(self) -> None:
        # ISO with offset
        rec1 = converter.normalize_record({"id": "1", "created_at": "2026-10-01T14:00:00+02:00"})
        self.assertEqual(rec1["created_at"], "2026-10-01T12:00:00Z")

        # Millisecond timestamp
        rec2 = converter.normalize_record({"id": "2", "created_at": 1790856000000})
        self.assertIsNotNone(rec2["created_at"])
        self.assertTrue(rec2["created_at"].endswith("Z"))

        # Space-separated date time
        rec3 = converter.normalize_record({"id": "3", "created_at": "2026-10-01 10:00:00"})
        self.assertEqual(rec3["created_at"], "2026-10-01T10:00:00Z")

        # Invalid timestamp yields None
        rec4 = converter.normalize_record({"id": "4", "created_at": "invalid-datetime-here"})
        self.assertIsNone(rec4["created_at"])

    def test_due_at_alternative_field(self) -> None:
        rec = converter.normalize_record({"id": "due1", "due_at": "2026-10-10T12:00:00Z"})
        self.assertEqual(rec["due_date"], "2026-10-10T12:00:00Z")

    def test_missing_id_generates_synthetic_id(self) -> None:
        rec = converter.normalize_record({"description": "Task without ID", "created_at": "2026-10-01T10:00:00Z"})
        self.assertTrue(rec["id"].startswith("syn_"))
        self.assertEqual(len(rec["id"]), 20)

    def test_empty_conversation_id_normalized_to_none(self) -> None:
        rec1 = converter.normalize_record({"id": "c1", "conversation_id": ""})
        self.assertIsNone(rec1["conversation_id"])

        rec2 = converter.normalize_record({"id": "c2", "conversation_id": "   "})
        self.assertIsNone(rec2["conversation_id"])

        rec3 = converter.normalize_record({"id": "c3", "conversation_id": None})
        self.assertIsNone(rec3["conversation_id"])

    def test_timestamp_overflow_numeric_string_graceful(self) -> None:
        overflow_candidates = ("1e100", "-1e100", "1e1000", "9999999999999999999999999999999999999999")
        for candidate in overflow_candidates:
            with self.subTest(candidate=candidate):
                rec = converter.normalize_record({"id": "ov", "created_at": candidate})
                self.assertIsNone(rec["created_at"])


class TestDeduplication(unittest.TestCase):
    def test_synthetic_ids_different_attributes_no_collision(self) -> None:
        # Two tasks created in the same second with same description but different due_date or conversation
        raw1 = {
            "description": "Fix memory leak",
            "created_at": "2026-10-04T10:00:00Z",
            "due_date": "2026-10-05T10:00:00Z",
        }
        raw2 = {
            "description": "Fix memory leak",
            "created_at": "2026-10-04T10:00:00Z",
            "due_date": "2026-10-08T10:00:00Z",
        }
        norm1 = converter.normalize_record(raw1)
        norm2 = converter.normalize_record(raw2)
        self.assertNotEqual(norm1["id"], norm2["id"])
        deduped = converter.deduplicate_records([norm1, norm2])
        self.assertEqual(len(deduped), 2)
    def test_dedup_prefers_latest_updated_at(self) -> None:
        records = [
            {
                "id": "item_1",
                "description": "Initial text",
                "updated_at": "2026-10-01T10:00:00Z",
                "completed": False,
            },
            {
                "id": "item_1",
                "description": "Updated text",
                "updated_at": "2026-10-02T15:00:00Z",
                "completed": True,
            },
            {
                "id": "item_2",
                "description": "Independent task",
                "updated_at": "2026-10-01T09:00:00Z",
                "completed": False,
            },
        ]
        deduped = converter.deduplicate_records(records)
        self.assertEqual(len(deduped), 2)
        item1 = next(r for r in deduped if r["id"] == "item_1")
        self.assertEqual(item1["description"], "Updated text")
        self.assertIs(item1["completed"], True)

    def test_dedup_prefers_record_with_timestamp_over_none(self) -> None:
        records = [
            {"id": "item_x", "description": "Without timestamp", "updated_at": None},
            {"id": "item_x", "description": "With timestamp", "updated_at": "2026-10-01T10:00:00Z"},
        ]
        deduped = converter.deduplicate_records(records)
        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["description"], "With timestamp")


class TestFilterAndSort(unittest.TestCase):
    def setUp(self) -> None:
        self.sample = [
            {
                "id": "open_early",
                "completed": False,
                "created_at": "2026-10-01T10:00:00Z",
                "due_date": "2026-10-10T10:00:00Z",
            },
            {
                "id": "open_late",
                "completed": False,
                "created_at": "2026-10-03T10:00:00Z",
                "due_date": "2026-10-05T10:00:00Z",
            },
            {
                "id": "done_mid",
                "completed": True,
                "created_at": "2026-10-02T10:00:00Z",
                "due_date": None,
            },
        ]

    def test_filter_open(self) -> None:
        res = converter.filter_and_sort_records(self.sample, status_filter="open", sort_mode="none")
        self.assertEqual(len(res), 2)
        self.assertTrue(all(not r["completed"] for r in res))

    def test_filter_completed(self) -> None:
        res = converter.filter_and_sort_records(self.sample, status_filter="completed", sort_mode="none")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "done_mid")

    def test_sort_created_desc(self) -> None:
        res = converter.filter_and_sort_records(self.sample, status_filter="all", sort_mode="created_desc")
        ids = [r["id"] for r in res]
        self.assertEqual(ids, ["open_late", "done_mid", "open_early"])

    def test_sort_created_asc(self) -> None:
        res = converter.filter_and_sort_records(self.sample, status_filter="all", sort_mode="created_asc")
        ids = [r["id"] for r in res]
        self.assertEqual(ids, ["open_early", "done_mid", "open_late"])

    def test_sort_due_date(self) -> None:
        res = converter.filter_and_sort_records(self.sample, status_filter="all", sort_mode="due_date")
        # Earliest due date first, tasks without due_date last
        self.assertEqual(res[0]["id"], "open_late")
        self.assertEqual(res[1]["id"], "open_early")
        self.assertEqual(res[2]["id"], "done_mid")


class TestPathTraversal(unittest.TestCase):
    def test_rejects_parent_traversal(self) -> None:
        invalid_paths = (
            Path("../escape.jsonl"),
            Path("sub/../../escape.jsonl"),
            Path("..\\escape.jsonl"),
            Path("folder/..\\escape.jsonl"),
        )
        for p in invalid_paths:
            with self.subTest(p=p):
                with self.assertRaises(ValueError):
                    converter.check_path_traversal(p)


class TestAtomicFileWrite(unittest.TestCase):
    def test_atomic_write_new_file(self) -> None:
        records = [
            {"id": "1", "description": "Task 1", "completed": False},
            {"id": "2", "description": "Task 2", "completed": True},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output.jsonl"
            converter.write_jsonl_atomic(records, out_file)
            self.assertTrue(out_file.is_file())

            lines = out_file.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 2)
            parsed_1 = json.loads(lines[0])
            parsed_2 = json.loads(lines[1])
            self.assertEqual(parsed_1["id"], "1")
            self.assertEqual(parsed_2["id"], "2")

    def test_refuse_overwrite_by_default(self) -> None:
        records = [{"id": "1", "description": "Task 1"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "exists.jsonl"
            out_file.write_text("existing content\n", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                converter.write_jsonl_atomic(records, out_file, overwrite=False)

            # Confirm existing content was not touched
            self.assertEqual(out_file.read_text(encoding="utf-8"), "existing content\n")

    def test_allow_overwrite_when_requested(self) -> None:
        records = [{"id": "new_1", "description": "Replaced"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "exists.jsonl"
            out_file.write_text("old content\n", encoding="utf-8")

            converter.write_jsonl_atomic(records, out_file, overwrite=True)
            content = out_file.read_text(encoding="utf-8").strip()
            parsed = json.loads(content)
            self.assertEqual(parsed["id"], "new_1")


class TestCliExecution(unittest.TestCase):
    def test_cli_file_to_file(self) -> None:
        sample_input = {
            "action_items": [
                {
                    "id": "cli_1",
                    "description": "CLI Action",
                    "completed": False,
                    "created_at": "2026-10-01T12:00:00Z",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            in_file = Path(tmpdir) / "in.json"
            out_file = Path(tmpdir) / "out.jsonl"
            in_file.write_text(json.dumps(sample_input), encoding="utf-8")

            exit_code = converter.main([str(in_file), "-o", str(out_file)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(out_file.is_file())

            line = out_file.read_text(encoding="utf-8").strip()
            rec = json.loads(line)
            self.assertEqual(rec["id"], "cli_1")
            self.assertEqual(rec["description"], "CLI Action")

    def test_cli_stdin_pipeline(self) -> None:
        sample_input = [{"id": "stdin_1", "description": "Piped task", "completed": True}]
        stdin_stream = io.StringIO(json.dumps(sample_input))

        with patch("sys.stdin", stdin_stream):
            stdout_stream = io.StringIO()
            with patch("sys.stdout", stdout_stream):
                exit_code = converter.main(["-"])
                self.assertEqual(exit_code, 0)
                output = stdout_stream.getvalue().strip()
                rec = json.loads(output)
                self.assertEqual(rec["id"], "stdin_1")
                self.assertIs(rec["completed"], True)

    def test_cli_invalid_json_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_file = Path(tmpdir) / "bad.json"
            bad_file.write_text("{invalid json format here", encoding="utf-8")

            stderr_stream = io.StringIO()
            with patch("sys.stderr", stderr_stream):
                exit_code = converter.main([str(bad_file)])
                self.assertEqual(exit_code, 1)
                self.assertIn("Invalid JSON", stderr_stream.getvalue())

    def test_cli_empty_stdin_rejected_with_error(self) -> None:
        stdin_stream = io.StringIO("")  # Completely empty input from failing pipeline
        with patch("sys.stdin", stdin_stream):
            stderr_stream = io.StringIO()
            with patch("sys.stderr", stderr_stream):
                exit_code = converter.main(["-"])
                self.assertEqual(exit_code, 1)
                self.assertIn("Empty input received from stdin", stderr_stream.getvalue())

    def test_cli_empty_json_array_accepted(self) -> None:
        stdin_stream = io.StringIO("[]")  # Valid empty array
        with patch("sys.stdin", stdin_stream):
            stdout_stream = io.StringIO()
            with patch("sys.stdout", stdout_stream):
                exit_code = converter.main(["-"])
                self.assertEqual(exit_code, 0)
                self.assertEqual(stdout_stream.getvalue(), "")

    def test_cli_missing_input_file_returns_error(self) -> None:
        stderr_stream = io.StringIO()
        with patch("sys.stderr", stderr_stream):
            exit_code = converter.main(["/nonexistent/path/never_exists.json"])
            self.assertEqual(exit_code, 1)
            self.assertIn("not found", stderr_stream.getvalue())


if __name__ == "__main__":
    unittest.main()
