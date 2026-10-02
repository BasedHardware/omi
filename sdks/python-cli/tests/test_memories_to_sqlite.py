"""Tests for memories to SQLite exporter.

Pins SQLite schema creation, data insertion, upsert deduplication,
path traversal security, magic-byte database protection, timestamp UTC normalization,
tags formatting, envelope unwrapping, and stdin ingestion.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

# Load memories_to_sqlite dynamically so PYTHONPATH does not require examples/
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_sqlite.py"
spec = importlib.util.spec_from_file_location("memories_to_sqlite", script_path)
m2sql = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2sql)


class TestMemoriesToSqlite(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.db_path = self.tmp / "test_memories.sqlite"
        self.sample_memories = [
            {
                "id": "mem_01_work",
                "content": "Deliver quarterly performance metrics for Second Brain",
                "category": "work",
                "tags": ["roadmap", "q3"],
                "visibility": "private",
                "created_at": "2026-09-20T10:00:00Z",
                "updated_at": "2026-09-21T12:00:00Z",
                "app_id": "app_planner",
            },
            {
                "id": "mem_02_learning",
                "content": "Learned Rust zero-cost abstraction semantics",
                "category": "learnings",
                "tags": ["rust", "systems"],
                "visibility": "public",
                "created_at": "2026-09-22T14:30:00+02:00",
                "updated_at": None,
                "source_app": "app_notes",
            },
            {
                "id": "mem_03_interests",
                "content": "Explore micro-satellite telemetry decoding",
                "category": "interests",
                "tags": None,
                "visibility": "public",
                "created_at": "2026-09-25T08:15:00Z",
                "updated_at": None,
                "app_id": None,
            },
        ]

    def tearDown(self):
        self._tmp.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(m2sql.utc_stamp("2026-09-20T10:30:00Z"), "2026-09-20 10:30:00")
        self.assertEqual(m2sql.utc_stamp("2026-09-20T12:30:00+02:00"), "2026-09-20 10:30:00")
        self.assertIsNone(m2sql.utc_stamp(None))
        self.assertIsNone(m2sql.utc_stamp("invalid-date"))
        self.assertIsNone(m2sql.utc_stamp("9999-12-31T23:59:59-14:00"))

    def test_tags_text_formatting(self):
        self.assertEqual(m2sql.tags_text(["alpha", "beta"]), "alpha,beta")
        self.assertEqual(m2sql.tags_text(["single"]), "single")
        self.assertEqual(m2sql.tags_text([]), None)
        self.assertEqual(m2sql.tags_text("already,string"), "already,string")
        self.assertIsNone(m2sql.tags_text(None))

    def test_path_traversal_rejected(self):
        json_file = self.tmp / "test.json"
        json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")
        with self.assertRaises(ValueError):
            m2sql.load(str(self.tmp / ".." / "traversal.sqlite"), [str(json_file)])

    def test_non_sqlite_file_rejected(self):
        fake_db = self.tmp / "not_sqlite.sqlite"
        fake_db.write_text("plain text file", encoding="utf-8")
        json_file = self.tmp / "test.json"
        json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")
        with self.assertRaises(ValueError):
            m2sql.load(str(fake_db), [str(json_file)])

    def test_insertion_and_querying(self):
        json_file = self.tmp / "memories.json"
        json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

        loaded, added, total = m2sql.load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 3)
        self.assertEqual(added, 3)
        self.assertEqual(total, 3)

        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute("SELECT id, content, category, tags, visibility, app_id FROM memories ORDER BY id").fetchall()
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[0][0], "mem_01_work")
            self.assertEqual(rows[0][2], "work")
            self.assertEqual(rows[0][3], "roadmap,q3")
            self.assertEqual(rows[0][4], "private")
            self.assertEqual(rows[0][5], "app_planner")

            # Check UTC timestamp conversion for +02:00 offset
            row2_time = conn.execute("SELECT created_at FROM memories WHERE id = 'mem_02_learning'").fetchone()[0]
            self.assertEqual(row2_time, "2026-09-22 12:30:00")
        finally:
            conn.close()

    def test_upsert_deduplication(self):
        json_file1 = self.tmp / "p1.json"
        json_file2 = self.tmp / "p2.json"
        json_file1.write_text(json.dumps([self.sample_memories[0]]), encoding="utf-8")

        updated_mem0 = dict(self.sample_memories[0])
        updated_mem0["content"] = "Updated performance metrics description"
        json_file2.write_text(json.dumps([updated_mem0, self.sample_memories[1]]), encoding="utf-8")

        m2sql.load(str(self.db_path), [str(json_file1)])
        loaded2, added2, total2 = m2sql.load(str(self.db_path), [str(json_file2)])

        self.assertEqual(loaded2, 2)
        self.assertEqual(added2, 1)  # Only 1 new row (mem_02)
        self.assertEqual(total2, 2)

        conn = sqlite3.connect(self.db_path)
        try:
            content = conn.execute("SELECT content FROM memories WHERE id = 'mem_01_work'").fetchone()[0]
            self.assertEqual(content, "Updated performance metrics description")
        finally:
            conn.close()

    def test_envelope_unwrapping(self):
        envelope = {"memories": self.sample_memories}
        json_file = self.tmp / "envelope.json"
        json_file.write_text(json.dumps(envelope), encoding="utf-8")

        loaded, added, total = m2sql.load(str(self.db_path), [str(json_file)])
        self.assertEqual(loaded, 3)
        self.assertEqual(total, 3)

    def test_stdin_ingestion(self):
        payload = json.dumps(self.sample_memories).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded, added, total = m2sql.load(str(self.db_path), ["-"])
            self.assertEqual(loaded, 3)
            self.assertEqual(total, 3)

    def test_main_cli_execution(self):
        json_file = self.tmp / "cli_mems.json"
        json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

        ret = m2sql.main([str(self.db_path), str(json_file)])
        self.assertEqual(ret, 0)
        self.assertTrue(self.db_path.exists())


if __name__ == "__main__":
    unittest.main()
