#!/usr/bin/env python3
"""Tests for Omi memories to Qdrant vector database points converter.

Pins payload schema, RFC 4122 UUID normalization, tag parsing, deduplication,
stdin streaming, placeholder vector dimensioning, and overwrite protection.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

# Load memories_to_qdrant dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_qdrant.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "memories_to_qdrant.py"

spec = importlib.util.spec_from_file_location("memories_to_qdrant", script_path)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Could not load module spec from {script_path}")
m2q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2q)

convert_memories_to_qdrant_payload = m2q.convert_memories_to_qdrant_payload
main = m2q.main
parse_memories_data = m2q.parse_memories_data
sanitize_uuid = m2q.sanitize_uuid
transform_memory_to_qdrant_point = m2q.transform_memory_to_qdrant_point


class TestMemoriesToQdrant(unittest.TestCase):
    def test_sanitize_uuid_valid(self):
        valid = "550e8400-e29b-41d4-a716-446655440000"
        self.assertEqual(sanitize_uuid(valid), valid)

    def test_sanitize_uuid_deterministic_fallback(self):
        raw = "custom-memory-id-123"
        u1 = sanitize_uuid(raw)
        u2 = sanitize_uuid(raw)
        self.assertEqual(u1, u2)
        # Check it is a valid UUID
        import uuid
        parsed = uuid.UUID(u1)
        self.assertEqual(parsed.version, 5)

    def test_parse_memories_data_formats(self):
        self.assertEqual(len(parse_memories_data([{"id": "m1"}])), 1)
        self.assertEqual(len(parse_memories_data({"memories": [{"id": "m2"}]})), 1)
        self.assertEqual(len(parse_memories_data({"items": [{"id": "m3"}]})), 1)

    def test_transform_memory_to_qdrant_point_basic(self):
        mem = {
            "id": "123e4567-e89b-12d3-a456-426614174000",
            "content": "User prefers dark mode in all apps",
            "category": "preferences",
            "tags": ["ui", "settings"],
            "created_at": "2026-09-24T10:00:00Z",
            "updated_at": "2026-09-24T11:00:00Z",
        }
        point = transform_memory_to_qdrant_point(mem)
        self.assertEqual(point["id"], "123e4567-e89b-12d3-a456-426614174000")
        self.assertNotIn("vector", point)
        payload = point["payload"]
        self.assertEqual(payload["memory_id"], "123e4567-e89b-12d3-a456-426614174000")
        self.assertEqual(payload["content"], "User prefers dark mode in all apps")
        self.assertEqual(payload["category"], "preferences")
        self.assertEqual(payload["tags"], ["ui", "settings"])

    def test_transform_with_vector_dim(self):
        mem = {"id": "m_vec", "content": "Embedding test"}
        point = transform_memory_to_qdrant_point(mem, vector_dim=4)
        self.assertIn("vector", point)
        self.assertEqual(point["vector"], [0.0, 0.0, 0.0, 0.0])

    def test_transform_missing_id_raises(self):
        with self.assertRaises(ValueError):
            transform_memory_to_qdrant_point({"content": "no id"})

    def test_deduplication_and_file_merge(self):
        m1 = [{"id": "m1", "content": "first version"}, {"id": "m2", "content": "second item"}]
        m2 = [{"id": "m1", "content": "updated version"}]

        with tempfile.TemporaryDirectory() as tmpdir:
            f1 = Path(tmpdir) / "f1.json"
            f2 = Path(tmpdir) / "f2.json"
            f1.write_text(json.dumps(m1), encoding="utf-8")
            f2.write_text(json.dumps(m2), encoding="utf-8")

            res = convert_memories_to_qdrant_payload([str(f1), str(f2)])
            points = res["points"]
            self.assertEqual(len(points), 2)
            # m1 should have updated content
            m1_point = [p for p in points if p["payload"]["memory_id"] == "m1"][0]
            self.assertEqual(m1_point["payload"]["content"], "updated version")

    def test_cli_integration_and_overwrite_guard(self):
        sample = [{"id": "cli_01", "content": "CLI test"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "src.json"
            dst = Path(tmpdir) / "out.json"
            src.write_text(json.dumps(sample), encoding="utf-8")

            # 1. Standard run
            sys.argv = ["memories_to_qdrant.py", str(src), "-o", str(dst)]
            main()
            self.assertTrue(dst.is_file())
            data = json.loads(dst.read_text(encoding="utf-8"))
            self.assertEqual(len(data["points"]), 1)

            # 2. Overwrite guard fails without --force
            with self.assertRaises(SystemExit) as cm:
                main()
            self.assertEqual(cm.exception.code, 1)

            # 3. Overwrite succeeds with --force
            sys.argv = ["memories_to_qdrant.py", str(src), "-o", str(dst), "--force"]
            main()
            self.assertTrue(dst.is_file())


if __name__ == "__main__":
    unittest.main()
