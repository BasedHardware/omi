"""Tests for memory list to Markdown digest exporter."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_digest.py"
spec = importlib.util.spec_from_file_location("memories_digest", script_path)
md = importlib.util.module_from_spec(spec)
spec.loader.exec_module(md)


class TestMemoriesDigest(unittest.TestCase):
    def test_generate_digest_and_stats(self):
        sample = [
            {
                "id": "m1",
                "category": "work",
                "visibility": "private",
                "content": "Prefers typing in dark mode",
                "tags": ["preferences", "ui"],
            },
            {
                "id": "m2",
                "category": "work",
                "visibility": "private",
                "content": "Working on OMI CLI recipes",
                "tags": ["python", "dev"],
            },
            {
                "id": "m3",
                "category": "fitness",
                "visibility": "public",
                "content": "Runs 5km every Saturday morning",
                "tags": ["running"],
            },
        ]

        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "part1.json"
            f2 = Path(tmp_dir) / "part2.json"
            out = Path(tmp_dir) / "digest.md"

            # Duplicate m1 to verify deduplication
            f1.write_text(json.dumps([sample[0], sample[1]]), encoding="utf-8")
            f2.write_text(json.dumps([sample[0], sample[2]]), encoding="utf-8")

            md.convert([str(f1), str(f2)], str(out))
            self.assertTrue(out.exists())

            content = out.read_text(encoding="utf-8")
            self.assertIn("# Memory Knowledge Digest", content)
            self.assertIn("- **Total Memories:** 3", content)
            self.assertIn("- **Categories Count:** 2", content)
            self.assertIn("work", content)
            self.assertIn("fitness", content)
            self.assertIn("Prefers typing in dark mode", content)
            self.assertIn("Runs 5km every Saturday morning", content)

    def test_refuse_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "part.json"
            out = Path(tmp_dir) / "digest.md"
            f1.write_text("[]", encoding="utf-8")
            out.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                md.convert([str(f1)], str(out))

    def test_empty_memories(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            f1 = Path(tmp_dir) / "empty.json"
            out = Path(tmp_dir) / "digest.md"
            f1.write_text("[]", encoding="utf-8")

            md.convert([str(f1)], str(out))
            content = out.read_text(encoding="utf-8")
            self.assertIn("No memories found in the export.", content)


if __name__ == "__main__":
    unittest.main()
