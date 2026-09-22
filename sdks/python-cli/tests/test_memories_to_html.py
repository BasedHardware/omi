"""Tests for memories to self-contained HTML report converter.

Pins category grouping, tag rendering, HTML-escaping of untrusted content,
and atomic-write / overwrite-refusal behavior.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_html.py"
spec = importlib.util.spec_from_file_location("memories_to_html", script_path)
m2h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2h)


class TestMemoriesToHtml(unittest.TestCase):
    def setUp(self):
        self.sample_memories = [
            {"id": "m1", "category": "work", "content": "Prefers async standups", "tags": ["workflow"]},
            {"id": "m2", "category": "hobbies", "content": "Plays chess weekly", "tags": []},
            {"id": "m3", "category": "work", "content": "Uses vim", "tags": ["tools", "editor"]},
        ]

    def test_conversion_and_grouping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")

            m2h.convert(json_file, html_file, title="My Memories")
            content = html_file.read_text(encoding="utf-8")

            self.assertIn("<title>My Memories</title>", content)
            self.assertIn("<h2>work</h2>", content)
            self.assertIn("<h2>hobbies</h2>", content)
            self.assertIn("Prefers async standups", content)
            self.assertIn("Uses vim", content)
            self.assertIn('<span class="tag">workflow</span>', content)
            # "work" section appears before "hobbies" is irrelevant; categories are alphabetical.
            self.assertLess(content.index("<h2>hobbies</h2>"), content.index("<h2>work</h2>"))

    def test_uncategorized_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps([{"id": "m1", "content": "no category"}]), encoding="utf-8")

            m2h.convert(json_file, html_file)
            self.assertIn("<h2>uncategorized</h2>", html_file.read_text(encoding="utf-8"))

    def test_html_escaping(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            unsafe = [{"id": "m1", "category": "work", "content": '<script>alert(1)</script> & "x"', "tags": []}]
            json_file.write_text(json.dumps(unsafe), encoding="utf-8")

            m2h.convert(json_file, html_file)
            content = html_file.read_text(encoding="utf-8")
            self.assertNotIn("<script>alert(1)</script>", content)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text("[]", encoding="utf-8")

            m2h.convert(json_file, html_file)
            self.assertIn("No memories found", html_file.read_text(encoding="utf-8"))

    def test_wrapped_object_input(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps({"memories": self.sample_memories}), encoding="utf-8")

            m2h.convert(json_file, html_file)
            self.assertTrue(html_file.is_file())

    def test_rejects_non_object_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(["nope"]), encoding="utf-8")

            with self.assertRaises(ValueError):
                m2h.convert(json_file, html_file)

    def test_refuse_overwrite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = Path(tmpdir) / "input.json"
            html_file = Path(tmpdir) / "report.html"
            json_file.write_text(json.dumps(self.sample_memories), encoding="utf-8")
            html_file.write_text("existing", encoding="utf-8")

            with self.assertRaises(FileExistsError):
                m2h.convert(json_file, html_file)


if __name__ == "__main__":
    unittest.main()
