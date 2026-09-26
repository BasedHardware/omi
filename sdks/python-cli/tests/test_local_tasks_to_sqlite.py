#!/usr/bin/env python3
"""Tests for local tasks to SQLite database converter.

Pins table schema, index creation, normalization, deduplication/upsert,
stdin piping, search checklist prose parsing, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

# Load local_tasks_to_sqlite example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "local_tasks_to_sqlite.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "local_tasks_to_sqlite.py"

spec = importlib.util.spec_from_file_location("local_tasks_to_sqlite", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
t2s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t2s)

import_tasks_to_db = t2s.import_tasks_to_db
main = t2s.main
normalize_task_record = t2s.normalize_task_record
parse_tasks_data = t2s.parse_tasks_data
parse_prose_line = t2s.parse_prose_line


class TestLocalTasksToSqlite(unittest.TestCase):
    def test_parse_tasks_data_formats(self):
        self.assertEqual(len(parse_tasks_data([{"id": "t1"}])), 1)
        self.assertEqual(len(parse_tasks_data({"tasks": [{"id": "t2"}]})), 1)
        self.assertEqual(len(parse_tasks_data({"result": [{"id": "t3"}]})), 1)
        self.assertEqual(len(parse_tasks_data({"rows": [{"id": "t4"}]})), 1)
        self.assertEqual(len(parse_tasks_data({"data": [{"id": "t5"}]})), 1)

    def test_parse_prose_search_output(self):
        raw_output = (
            "1. [x] Review spec (similarity: 0.91, id: abc, source: action_items)\n"
            "2. [ ] Write documentation (similarity: 0.85, id: def, source: work)\n"
        )
        parsed = parse_tasks_data(raw_output)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], "abc")
        self.assertEqual(parsed[0]["title"], "Review spec")
        self.assertTrue(parsed[0]["completed"])
        self.assertEqual(parsed[0]["category"], "action_items")
        self.assertEqual(parsed[0]["similarity"], 0.91)

        self.assertEqual(parsed[1]["id"], "def")
        self.assertEqual(parsed[1]["title"], "Write documentation")
        self.assertFalse(parsed[1]["completed"])
        self.assertEqual(parsed[1]["category"], "work")

    def test_parse_json_encoded_prose_string(self):
        raw_output = "1. [x] Buy groceries (id: task_g1)\n" "2. [ ] Book flight (id: task_f2)\n"
        json_wrapped = json.dumps(raw_output)
        parsed = parse_tasks_data(json_wrapped)
        self.assertEqual(len(parsed), 2)
        self.assertEqual(parsed[0]["id"], "task_g1")
        self.assertEqual(parsed[1]["id"], "task_f2")

    def test_normalize_task_record(self):
        item = {
            "id": "t_01",
            "title": "Review Bug #123",
            "description": "Fix typo",
            "completed": True,
            "created_at": "2026-09-24T10:00:00Z",
            "due_at": "2026-09-25T12:00:00Z",
            "category": "bugs",
        }
        rec = normalize_task_record(item, 0)
        self.assertEqual(rec[0], "t_01")
        self.assertEqual(rec[1], "Review Bug #123")
        self.assertEqual(rec[2], "Fix typo")
        self.assertEqual(rec[3], 1)
        self.assertEqual(rec[4], "2026-09-24T10:00:00Z")
        self.assertEqual(rec[6], "2026-09-25T12:00:00Z")
        self.assertEqual(rec[7], "bugs")

    def test_deterministic_id_fallback(self):
        item1 = {"title": "Task Alpha"}
        item2 = {"title": "Task Beta"}
        rec1 = normalize_task_record(item1, 0)
        rec2 = normalize_task_record(item2, 1)
        self.assertTrue(rec1[0].startswith("task_"))
        self.assertTrue(rec2[0].startswith("task_"))
        self.assertNotEqual(rec1[0], rec2[0])
        # Verify idempotency of hash derivation
        rec1_again = normalize_task_record(item1, 5)
        self.assertEqual(rec1[0], rec1_again[0])

    def test_import_tasks_to_db_and_query(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tasks.db"
            sample_tasks = [
                {"id": "t1", "title": "Buy groceries", "completed": False, "category": "errands"},
                {"id": "t2", "title": "Deploy PR", "completed": True, "category": "work"},
            ]
            total, completed = import_tasks_to_db(db_path, sample_tasks)
            self.assertEqual(total, 2)
            self.assertEqual(completed, 1)

            # Query database directly to verify schema and indexes
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("SELECT id, title, completed, category FROM local_tasks ORDER BY id")
            rows = cur.fetchall()
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0], ("t1", "Buy groceries", 0, "errands"))
            self.assertEqual(rows[1], ("t2", "Deploy PR", 1, "work"))
            conn.close()

    def test_import_tasks_idempotent_upsert(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tasks.db"
            initial = [{"id": "t1", "title": "Draft spec", "completed": False}]
            import_tasks_to_db(db_path, initial)

            # Second import with updated completion status
            updated = [{"id": "t1", "title": "Draft spec", "completed": True}]
            total, completed = import_tasks_to_db(db_path, updated)
            self.assertEqual(total, 1)
            self.assertEqual(completed, 1)

    def test_cli_end_to_end_file_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "tasks.json"
            out_db = tmppath / "out.db"

            in_file.write_text(json.dumps([{"id": "c1", "title": "CLI task"}]), encoding="utf-8")
            code = main([str(in_file), "-o", str(out_db)])
            self.assertEqual(code, 0)
            self.assertTrue(out_db.exists())

    def test_cli_end_to_end_prose_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "search_results.txt"
            out_db = tmppath / "prose.db"

            in_file.write_text("1. [x] Clean workspace (id: cw-1, similarity: 0.99)\n", encoding="utf-8")
            code = main([str(in_file), "-o", str(out_db)])
            self.assertEqual(code, 0)
            self.assertTrue(out_db.exists())

            conn = sqlite3.connect(out_db)
            cur = conn.cursor()
            cur.execute("SELECT id, title, completed FROM local_tasks")
            row = cur.fetchone()
            self.assertEqual(row, ("cw-1", "Clean workspace", 1))
            conn.close()

    def test_cli_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            in_file = tmppath / "input.json"
            out_db = tmppath / "existing.db"

            in_file.write_text(json.dumps([{"id": "t1", "title": "First"}]), encoding="utf-8")
            main([str(in_file), "-o", str(out_db)])

            # Re-running with --force recreates database cleanly
            in_file2 = tmppath / "input2.json"
            in_file2.write_text(json.dumps([{"id": "t2", "title": "Second"}]), encoding="utf-8")
            code_ok = main([str(in_file2), "-o", str(out_db), "--force"])
            self.assertEqual(code_ok, 0)

            conn = sqlite3.connect(out_db)
            cur = conn.cursor()
            cur.execute("SELECT id FROM local_tasks")
            ids = [r[0] for r in cur.fetchall()]
            self.assertEqual(ids, ["t2"])
            conn.close()

    def test_cli_stdin(self):
        sample = json.dumps([{"id": "stdin_t", "title": "Piped task"}])
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(sample)
            with tempfile.TemporaryDirectory() as tmpdir:
                db_path = Path(tmpdir) / "stdin.db"
                code = main(["-", "-o", str(db_path)])
                self.assertEqual(code, 0)
                self.assertTrue(db_path.exists())
        finally:
            sys.stdin = old_stdin

    def test_normalize_task_record_camel_case_timestamps(self):
        item = {
            "id": "t_macos_01",
            "description": "macOS Desktop Action Item",
            "completed": 1,
            "createdAt": "2026-09-24T10:00:00Z",
            "updatedAt": "2026-09-24T11:00:00Z",
            "dueAt": "2026-09-25T12:00:00Z",
        }
        rec = normalize_task_record(item, 0)
        self.assertEqual(rec[0], "t_macos_01")
        self.assertEqual(rec[1], "macOS Desktop Action Item")
        self.assertEqual(rec[2], "macOS Desktop Action Item")
        self.assertEqual(rec[3], 1)
        self.assertEqual(rec[4], "2026-09-24T10:00:00Z")
        self.assertEqual(rec[5], "2026-09-24T11:00:00Z")
        self.assertEqual(rec[6], "2026-09-25T12:00:00Z")

    def test_parse_prose_line_priority_tag_cleaned(self):
        line = "1. [x] Review spec [high] (similarity: 0.91, id: 42, source: action_items)"
        item = parse_prose_line(line, 0)
        self.assertIsNotNone(item)
        self.assertEqual(item["id"], "42")
        self.assertEqual(item["title"], "Review spec")
        self.assertEqual(item["priority"], "high")
        self.assertTrue(item["completed"])
        self.assertEqual(item["category"], "action_items")


if __name__ == "__main__":
    unittest.main()
