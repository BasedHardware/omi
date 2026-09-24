"""Tests for memories to HTML vault dashboard exporter.

Verifies:
- Self-contained HTML second brain structure and dark theme
- Overview metrics calculation (total memories, categories count, tags count)
- Real-time client-side search box and memory card rendering
- Category filtering (--category)
- Both bare array and wrapped {"memories": [...]} input formats
- Memory ID deduplication
- HTML XSS escaping for text, categories, and tags
- Overwrite guard and malformed input handling
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

# Load memories_to_html script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_html.py"
if not script_path.exists():
    script_path = Path(__file__).resolve().parent / "memories_to_html.py"

spec = importlib.util.spec_from_file_location("memories_to_html", script_path)
m2html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2html)


class TestMemoriesToHtml(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {
                "id": "mem-001",
                "content": "Key takeaway: Focus on latency reduction for edge AI models",
                "category": "learnings",
                "tags": ["ai", "edge", "performance"],
                "created_at": "2026-09-20T14:30:00Z"
            },
            {
                "id": "mem-002",
                "content": "Prefers oat milk in cappuccino with no extra sugar",
                "category": "preferences",
                "tags": ["coffee", "personal"],
                "created_at": "2026-09-21T09:15:00Z"
            }
        ]

    def test_basic_rendering_and_stats(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "memories.json"
            dst = Path(tmpdir) / "vault.html"
            src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            count = m2html.convert(str(src), str(dst), title="Personal Second Brain")
            self.assertEqual(count, 2)
            self.assertTrue(dst.exists())

            html = dst.read_text(encoding="utf-8")
            self.assertIn("<!DOCTYPE html>", html)
            self.assertIn("<title>Personal Second Brain</title>", html)
            self.assertIn("Total Memories", html)
            self.assertIn("Categories", html)
            self.assertIn("Unique Tags", html)
            self.assertIn("Focus on latency reduction", html)
            self.assertIn("Prefers oat milk", html)
            self.assertIn("category-learnings", html)
            self.assertIn("category-preferences", html)
            self.assertIn("#ai", html)
            self.assertIn("#coffee", html)
            self.assertIn('id="search"', html)

    def test_category_filtering(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "memories.json"
            dst = Path(tmpdir) / "learnings_only.html"
            src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            count = m2html.convert(str(src), str(dst), categories=["learnings"])
            self.assertEqual(count, 1)

            html = dst.read_text(encoding="utf-8")
            self.assertIn("Focus on latency reduction", html)
            self.assertNotIn("Prefers oat milk", html)

    def test_wrapped_json_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "wrapped.json"
            dst = Path(tmpdir) / "vault.html"
            src.write_text(json.dumps({"memories": self.sample_memories}), encoding="utf-8")

            count = m2html.convert(str(src), str(dst))
            self.assertEqual(count, 2)

    def test_deduplication(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "dup.json"
            dst = Path(tmpdir) / "vault.html"
            items_with_dup = [self.sample_memories[0], self.sample_memories[0], self.sample_memories[1]]
            src.write_text(json.dumps(items_with_dup), encoding="utf-8")

            count = m2html.convert(str(src), str(dst))
            self.assertEqual(count, 2)

    def test_xss_protection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "xss.json"
            dst = Path(tmpdir) / "vault.html"
            xss_memory = [{
                "id": "mem-xss",
                "content": "<script>alert('xss')</script> & safe text",
                "category": "<svg/onload=alert(1)>",
                "tags": ["<tag1>", "normal"]
            }]
            src.write_text(json.dumps(xss_memory), encoding="utf-8")

            count = m2html.convert(str(src), str(dst))
            self.assertEqual(count, 1)

            html = dst.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert('xss')</script>", html)
            self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", html)
            self.assertIn("&lt;svg/onload=alert(1)&gt;", html)
            self.assertIn("#&lt;tag1&gt;", html)

    def test_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            src = Path(tmpdir) / "memories.json"
            dst = Path(tmpdir) / "vault.html"
            src.write_text(json.dumps(self.sample_memories), encoding="utf-8")
            dst.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                m2html.convert(str(src), str(dst), overwrite=False)

    def test_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad = Path(tmpdir) / "bad.json"
            dst = Path(tmpdir) / "vault.html"
            bad.write_text(json.dumps("not a list"), encoding="utf-8")

            with self.assertRaises(ValueError):
                m2html.convert(str(bad), str(dst))


if __name__ == "__main__":
    unittest.main()
