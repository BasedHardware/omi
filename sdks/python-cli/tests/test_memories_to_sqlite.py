#!/usr/bin/env python3
"""
Unit tests for sdks/python-cli/examples/memories_to_sqlite.py
"""

from __future__ import annotations

import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from memories_to_sqlite import (
    load,
    rows_from,
    text,
    utc_stamp,
)


class TestMemoriesToSqlite(unittest.TestCase):

    def test_text_helper(self):
        self.assertIsNone(text(None))
        self.assertEqual(text("  learn   asyncio \n"), "learn asyncio")
        self.assertEqual(text(99), "99")
        self.assertEqual(text(["dev", "python"]), '["dev", "python"]')
        self.assertEqual(text({"a": 1}), '{"a": 1}')

    def test_utc_stamp(self):
        self.assertIsNone(utc_stamp(None))
        self.assertIsNone(utc_stamp(""))
        self.assertIsNone(utc_stamp("invalid-date"))

        ts_z = utc_stamp("2026-09-20T14:30:00Z")
        self.assertEqual(ts_z, "2026-09-20 14:30:00")

        ts_offset = utc_stamp("2026-09-20T22:30:00+08:00")
        self.assertEqual(ts_offset, "2026-09-20 14:30:00")

    def test_load_and_deduplicate(self):
        data1 = [
            {
                "id": "m1",
                "content": "Discussed migrating to SQLite with team",
                "category": "work",
                "tags": ["sqlite", "database"],
                "created_at": "2026-09-20T10:00:00Z",
            },
            {
                "id": "m2",
                "content": "Started reading Rust book chapter 4",
                "category": "learnings",
                "tags": ["rust"],
                "created_at": "2026-09-20T14:00:00Z",
            }
        ]
        data2 = [
            {
                "id": "m2",
                "content": "Finished reading Rust book chapter 4 on ownership",
                "category": "learnings",
                "tags": ["rust", "ownership", "systems"],
                "created_at": "2026-09-20T14:00:00Z",
                "updated_at": "2026-09-21T09:00:00Z",
            },
            {
                "id": "m3",
                "content": "Prefers dark mode and monospace fonts",
                "category": "preferences",
                "tags": ["editor", "ui"],
                "created_at": "2026-09-21T10:00:00Z",
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test_memories.sqlite")
            p1 = Path(tmpdir) / "p1.json"
            p2 = Path(tmpdir) / "p2.json"
            p1.write_text(json.dumps(data1), encoding="utf-8")
            p2.write_text(json.dumps(data2), encoding="utf-8")

            loaded, added, total = load(db_path, [str(p1), str(p2)])
            self.assertEqual(loaded, 4)
            self.assertEqual(added, 3)
            self.assertEqual(total, 3)

            conn = sqlite3.connect(db_path)
            try:
                # Check updated memory content
                row_m2 = conn.execute("SELECT content, updated_at FROM memories WHERE id = 'm2'").fetchone()
                self.assertIn("ownership", row_m2[0])
                self.assertEqual(row_m2[1], "2026-09-21 09:00:00")

                # Check tags synchronization (old tags cleared and replaced)
                tags_m2 = [r[0] for r in conn.execute("SELECT tag FROM memory_tags WHERE memory_id = 'm2' ORDER BY tag").fetchall()]
                self.assertEqual(tags_m2, ["ownership", "rust", "systems"])

                # Check FTS deduplication (exactly 1 match for m2 in FTS)
                fts_count = conn.execute("SELECT COUNT(*) FROM memories_fts WHERE id = 'm2'").fetchone()[0]
                self.assertEqual(fts_count, 1)

                # Reload same file to verify idempotence
                loaded2, added2, total2 = load(db_path, [str(p1)])
                self.assertEqual(loaded2, 2)
                self.assertEqual(added2, 0)
                self.assertEqual(total2, 3)
            finally:
                conn.close()

    def test_load_stdin(self):
        data = [{"id": "m_pipe", "content": "Memory via stdin stream", "category": "test"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "stdin.sqlite")
            with patch("sys.stdin", io.StringIO(json.dumps(data))):
                loaded, added, total = load(db_path, ["-"])
                self.assertEqual(loaded, 1)
                self.assertEqual(added, 1)
                self.assertEqual(total, 1)

    def test_schema_and_indexes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "schema.sqlite")
            load(db_path, [])
            conn = sqlite3.connect(db_path)
            try:
                tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
                self.assertIn("memories", tables)
                self.assertIn("memory_tags", tables)
                self.assertIn("memories_fts", tables)

                # Check columns
                m_cols = [r[1] for r in conn.execute("PRAGMA table_info(memories)").fetchall()]
                self.assertEqual(m_cols, ["id", "content", "category", "created_at", "updated_at", "raw_json"])

                t_cols = [r[1] for r in conn.execute("PRAGMA table_info(memory_tags)").fetchall()]
                self.assertEqual(t_cols, ["memory_id", "tag"])

                # Check indexes
                indexes = {r[1] for r in conn.execute("PRAGMA index_list(memories)").fetchall()}
                self.assertIn("idx_memories_category", indexes)
                self.assertIn("idx_memories_created_at", indexes)

                tag_indexes = {r[1] for r in conn.execute("PRAGMA index_list(memory_tags)").fetchall()}
                self.assertIn("idx_memory_tags_tag", tag_indexes)
            finally:
                conn.close()

    def test_fts5_queries(self):
        data = [
            {"id": "m1", "content": "Implementing high-performance FTS5 full text search in SQLite", "category": "work", "tags": ["sqlite", "search"]},
            {"id": "m2", "content": "Deep dive into Python asyncio task cancellation semantics", "category": "learnings", "tags": ["python", "asyncio"]},
            {"id": "m3", "content": "Setting up Rust cargo workspaces for microservices", "category": "work", "tags": ["rust", "backend"]},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "fts_test.sqlite")
            p = Path(tmpdir) / "data.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            load(db_path, [str(p)])

            conn = sqlite3.connect(db_path)
            try:
                # Exact keyword match
                r1 = conn.execute("SELECT id FROM memories_fts WHERE memories_fts MATCH 'asyncio'").fetchall()
                self.assertEqual(len(r1), 1)
                self.assertEqual(r1[0][0], "m2")

                # Boolean OR match
                r2 = conn.execute("SELECT id FROM memories_fts WHERE memories_fts MATCH 'sqlite OR rust'").fetchall()
                matched_ids = {r[0] for r in r2}
                self.assertEqual(matched_ids, {"m1", "m3"})

                # Prefix match
                r3 = conn.execute("SELECT id FROM memories_fts WHERE memories_fts MATCH 'micro*'").fetchall()
                self.assertEqual(len(r3), 1)
                self.assertEqual(r3[0][0], "m3")

                # Tag match in FTS
                r4 = conn.execute("SELECT id FROM memories_fts WHERE memories_fts MATCH 'search'").fetchall()
                self.assertEqual(len(r4), 1)
                self.assertEqual(r4[0][0], "m1")
            finally:
                conn.close()

    def test_relational_tag_queries(self):
        data = [
            {"id": "m1", "content": "Mem 1", "tags": ["python", "api"]},
            {"id": "m2", "content": "Mem 2", "tags": ["python", "backend"]},
            {"id": "m3", "content": "Mem 3", "tags": ["rust", "backend"]},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "rel_test.sqlite")
            p = Path(tmpdir) / "data.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            load(db_path, [str(p)])

            conn = sqlite3.connect(db_path)
            try:
                # Find all memories tagged with 'python'
                rows = conn.execute("""
                    SELECT m.id FROM memories m
                    JOIN memory_tags t ON m.id = t.memory_id
                    WHERE t.tag = 'python'
                    ORDER BY m.id
                """).fetchall()
                self.assertEqual([r[0] for r in rows], ["m1", "m2"])

                # Tag counts
                counts = dict(conn.execute("SELECT tag, COUNT(*) FROM memory_tags GROUP BY tag ORDER BY tag").fetchall())
                self.assertEqual(counts["python"], 2)
                self.assertEqual(counts["backend"], 2)
                self.assertEqual(counts["api"], 1)
                self.assertEqual(counts["rust"], 1)
            finally:
                conn.close()

    def test_invalid_inputs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "invalid.sqlite")

            with self.assertRaises(FileNotFoundError):
                load(db_path, [str(Path(tmpdir) / "nonexistent.json")])

            bad_p = Path(tmpdir) / "bad.json"
            bad_p.write_text("{corrupt", encoding="utf-8")
            with self.assertRaises(ValueError):
                load(db_path, [str(bad_p)])

            noid_p = Path(tmpdir) / "no_id.json"
            noid_p.write_text('[{"content": "missing id"}]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load(db_path, [str(noid_p)])

            nondict_p = Path(tmpdir) / "non_dict.json"
            nondict_p.write_text('["just a string"]', encoding="utf-8")
            with self.assertRaises(ValueError):
                load(db_path, [str(nondict_p)])


if __name__ == "__main__":
    unittest.main()
