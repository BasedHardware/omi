"""Hermetic tests for examples/memories_to_lancedb.py (#18937).

Covers: record normalization (text-for-vectorizer + metadata), envelope
unwrapping, dedupe, zero-dep JSON payload, optional-ingest guard, output
guards.
"""

import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1] / "examples"))

import memories_to_lancedb as m  # noqa: E402

MEM = {
    "id": "m1",
    "content": "Prefers short standups",
    "category": "Work",
    "tags": ["style", "meetings"],
    "visibility": "public",
    "manually_added": True,
    "reviewed": False,
    "app_id": "chatgpt",
    "created_at": "2026-10-17T12:00:00Z",
    "updated_at": "2026-10-17T13:00:00Z",
}


class TestNormalize(unittest.TestCase):
    def test_record_shape(self):
        r = m.normalize(MEM)
        self.assertEqual(r["id"], "m1")
        self.assertEqual(r["text"], "Prefers short standups")
        self.assertEqual(r["category"], "Work")
        self.assertEqual(r["tags"], ["style", "meetings"])
        self.assertIs(r["manually_added"], True)
        self.assertIs(r["reviewed"], False)

    def test_missing_id_dropped(self):
        self.assertIsNone(m.normalize({"content": "no id"}))

    def test_fallbacks(self):
        r = m.normalize({"memory_id": "m2", "text": "x", "source_app": "cli"})
        self.assertEqual(r["id"], "m2")
        self.assertEqual(r["app_id"], "cli")


class TestPayload(unittest.TestCase):
    def test_zero_dep_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM, {**MEM, "id": "m2"}]}))
            out = m.emit_payload([str(src)])
            lines = out.strip().split("\n")
            self.assertEqual(len(lines), 2)
            r = json.loads(lines[0])
            self.assertEqual(r["id"], "m1")
            self.assertIn("text", r)  # what the embedder consumes

    def test_dedupe(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM, MEM]}))
            self.assertEqual(len(m.emit_payload([str(src)]).strip().split("\n")), 1)

    def test_envelope_shapes(self):
        for payload in ({"memories": [MEM]}, {"items": [MEM]}, {"data": [MEM]}, [MEM], MEM):
            self.assertEqual(len(m.extract_memories(payload)), 1)


class TestIngestGuard(unittest.TestCase):
    def test_ingest_path(self):
        """Direct ingest: with the full stack, `text` becomes a vector
        column (semantic search); without it, a clean error."""
        import importlib.util

        has_lancedb = importlib.util.find_spec("lancedb") is not None
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM, {**MEM, "id": "m2"}]}))
            if has_lancedb:
                db_path = str(Path(td) / "db")
                try:
                    n = m.ingest([str(src)], db_path, "memories", "all-MiniLM-L6-v2")
                except ValueError as e:
                    # lancedb present but the embedding stack isn't —
                    # the honest error names what's missing.
                    self.assertIn("sentence-transformers", str(e))
                    return
                except OSError:
                    # model not cached + hub unreachable — the ingest
                    # path is still wired; only the vector assertion
                    # needs a real model.
                    self.skipTest("all-MiniLM-L6-v2 not downloadable here")
                self.assertEqual(n, 2)
                # the reviewer's ask: semantic search needs a real
                # `vector` column — assert the schema produced one.
                import lancedb as ldb

                tbl = ldb.connect(db_path).open_table("memories")
                self.assertIn("vector", tbl.schema.names)
            else:
                with self.assertRaises(ValueError) as ctx:
                    m.ingest([str(src)], str(Path(td) / "db"), "memories", "model")
                self.assertIn("pip install lancedb", str(ctx.exception))


class TestCli(unittest.TestCase):
    def test_exclusive_write(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            out = Path(td) / "o.json"
            out.write_text("keep")
            buf = io.StringIO()
            old = sys.stderr
            sys.stderr = buf
            try:
                rc = m.main([str(src), "-o", str(out)])
            finally:
                sys.stderr = old
            self.assertEqual(rc, 2)
            self.assertEqual(out.read_text(), "keep")

    def test_dotdot_refused(self):
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "m.json"
            src.write_text(json.dumps({"memories": [MEM]}))
            buf = io.StringIO()
            old = sys.stderr
            sys.stderr = buf
            try:
                rc = m.main([str(src), "-o", "../escape.json"])
            finally:
                sys.stderr = old
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
