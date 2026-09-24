"""Tests for Omi memories to Obsidian knowledge vault recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_obsidian.py"
spec = importlib.util.spec_from_file_location("memories_to_obsidian", script_path)
m2o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2o)


class TestMemoriesToObsidian(unittest.TestCase):
    def test_slugify(self):
        self.assertEqual(m2o.slugify("Python Tips & Tricks"), "python_tips_tricks")
        self.assertEqual(m2o.slugify("  Spaces  "), "spaces")

    def test_extract_memories(self):
        raw = '[{"id": "mem-1", "content": "Learned Rust today"}]'
        res = m2o.extract_memories(raw)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "mem-1")

    def test_build_obsidian_vault_structure(self):
        mem1 = {"id": "m-1", "content": "Rust memory safety", "category": "Programming"}
        mem2 = {"id": "m-2", "content": "Morning walk habit", "category": "Health"}

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            f = tmp / "data.json"
            vault_dir = tmp / "MyVault"

            f.write_text(json.dumps([mem1, mem2]), encoding="utf-8")
            count = m2o.build_obsidian_vault([f], vault_dir, vault_name="Personal Second Brain")

            self.assertEqual(count, 2)

            # Check Index / MOC
            index_path = vault_dir / "Index.md"
            self.assertTrue(index_path.exists())
            index_content = index_path.read_text(encoding="utf-8")
            self.assertIn("Personal Second Brain", index_content)
            self.assertIn("[[Programming]]", index_content)
            self.assertIn("[[Health]]", index_content)

            # Check category hubs
            prog_hub = vault_dir / "Categories" / "Programming.md"
            self.assertTrue(prog_hub.exists())
            prog_content = prog_hub.read_text(encoding="utf-8")
            self.assertIn("Programming Hub", prog_content)

            # Check atomic notes
            notes = list((vault_dir / "Memories").glob("*.md"))
            self.assertEqual(len(notes), 2)


if __name__ == "__main__":
    unittest.main()
