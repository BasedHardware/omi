"""Tests for memories_to_html recipe.

Covers:
- HTML escaping and sanitization
- Category grouping and emoji headers
- Statistical calculation (total, categories, manual, auto)
- Deduplication of records across export pages
- Output file creation
- Error handling on invalid records
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

# Load memories_to_html example script dynamically
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_html.py"
spec = importlib.util.spec_from_file_location("memories_to_html", script_path)
m2h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2h)

convert_paths_to_html = m2h.convert_paths_to_html
generate_html_wiki = m2h.generate_html_wiki
utc_stamp = m2h.utc_stamp


SAMPLE_MEMORIES = [
    {
        "id": "mem_1",
        "content": "Prefers Python & dark mode themes",
        "category": "preferences",
        "manually_added": True,
        "created_at": "2026-09-20T09:00:00Z",
    },
    {
        "id": "mem_2",
        "content": "Special note <script>alert('xss')</script>",
        "category": "work",
        "manually_added": False,
        "created_at": "2026-09-19T14:00:00+02:00",
    },
    {
        "id": "mem_3",
        "content": "Completed React 19 architecture review",
        "category": "work",
        "manually_added": True,
        "created_at": "2026-09-21T08:00:00Z",
    },
]


class TestMemoriesToHtml(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_utc_stamp_normalization(self):
        self.assertEqual(utc_stamp("2026-09-20T11:00:00Z"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp("2026-09-20T13:00:00+02:00"), "2026-09-20 11:00:00")
        self.assertEqual(utc_stamp(""), "")
        self.assertEqual(utc_stamp(None), "")

    def test_html_escaping(self):
        wiki = generate_html_wiki(SAMPLE_MEMORIES)
        self.assertNotIn("<script>", wiki)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;", wiki)
        self.assertIn("Prefers Python &amp; dark mode themes", wiki)

    def test_categories_and_stats(self):
        wiki = generate_html_wiki(SAMPLE_MEMORIES)
        self.assertIn("3 total knowledge item(s)", wiki)
        self.assertIn("2 category/categories", wiki)
        self.assertIn("Work &amp; Career", wiki)
        self.assertIn("User Preferences", wiki)
        self.assertIn("badge-manual", wiki)
        self.assertIn("badge-auto", wiki)

    def test_deduplication(self):
        duplicated = [SAMPLE_MEMORIES[0], SAMPLE_MEMORIES[0]]
        wiki = generate_html_wiki(duplicated)
        self.assertIn("1 total knowledge item(s)", wiki)

    def test_convert_to_file(self):
        json_file = self.dir_path / "memories.json"
        json_file.write_text(json.dumps(SAMPLE_MEMORIES), encoding="utf-8")
        out_html = self.dir_path / "wiki.html"

        count = convert_paths_to_html([json_file], out_html)
        self.assertEqual(count, 3)
        self.assertTrue(out_html.exists())
        content = out_html.read_text(encoding="utf-8")
        self.assertIn("<!DOCTYPE html>", content)
        self.assertIn("Omi Memories Knowledge Base", content)

    def test_missing_id_raises_value_error(self):
        invalid = [{"content": "No ID memory"}]
        json_file = self.dir_path / "invalid.json"
        json_file.write_text(json.dumps(invalid), encoding="utf-8")

        with self.assertRaises(ValueError) as ctx:
            convert_paths_to_html([json_file])
        self.assertIn("missing required 'id' field", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
