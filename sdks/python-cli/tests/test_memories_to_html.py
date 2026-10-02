"""Tests for memories to HTML exporter.

Pins HTML structure, stats grid, category grouping, tags, privacy badges,
escaping against XSS, timezone offset handling, envelope unwrapping,
idempotent deduplication, stdin streaming, and atomic overwrite safety.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

# Load memories_to_html dynamically so PYTHONPATH does not require examples/
script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_html.py"
spec = importlib.util.spec_from_file_location("memories_to_html", script_path)
m2html = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2html)


class TestMemoriesToHtml(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.sample_memories = [
            {
                "id": "mem_01_work",
                "content": "Deliver quarterly performance metrics for Second Brain",
                "category": "work",
                "tags": ["roadmap", "q3"],
                "visibility": "private",
                "created_at": "2026-09-20T10:00:00Z",
            },
            {
                "id": "mem_02_learning",
                "content": "Learned Rust zero-cost abstraction semantics",
                "category": "learnings",
                "tags": ["rust", "systems"],
                "visibility": "public",
                "created_at": "2026-09-22T14:30:00Z",
            },
            {
                "id": "mem_03_interests",
                "content": "Explore micro-satellite telemetry decoding",
                "category": "interests",
                "tags": [],
                "visibility": "public",
                "created_at": "2026-09-25T08:15:00Z",
            },
        ]

    def tearDown(self):
        self._tmp.cleanup()

    def test_report_structure_and_stats(self):
        items_dict = {it["id"]: it for it in self.sample_memories}
        html_out = m2html.report(
            items_dict,
            timedelta(0),
            "",
            title="Second Brain Knowledge",
        )
        self.assertIn("<!DOCTYPE html>", html_out)
        self.assertIn("<title>Second Brain Knowledge</title>", html_out)
        self.assertIn("<h1>Second Brain Knowledge</h1>", html_out)
        self.assertIn("Total: 3 · Categories: 3 · Tagged: 2 · Private: 1.", html_out)
        self.assertIn('<div class="stat-card"><div class="num">3</div><div class="lbl">Total Memories</div></div>', html_out)
        self.assertIn('<div class="stat-card"><div class="num">2</div><div class="lbl">Tagged</div></div>', html_out)
        self.assertIn('<div class="stat-card"><div class="num" style="color:var(--badge-priv-text);">1</div><div class="lbl">Private</div></div>', html_out)

    def test_category_grouping_and_emojis(self):
        items_dict = {it["id"]: it for it in self.sample_memories}
        html_out = m2html.report(items_dict, timedelta(0), "")
        self.assertIn("💼 Work (1)", html_out)
        self.assertIn("🧠 Learnings (1)", html_out)
        self.assertIn("💡 Interests (1)", html_out)
        self.assertIn("#roadmap", html_out)
        self.assertIn("#rust", html_out)
        self.assertIn("🔒 Private", html_out)

    def test_escaping_against_xss(self):
        malicious = {
            "xss": {
                "id": "<img src=x onerror=alert(1)>",
                "content": "<script>alert('xss')</script> & 'quotes'",
                "category": "work",
                "tags": ["<script>", "normal"],
                "visibility": "public",
                "created_at": "2026-09-20T10:00:00Z",
            }
        }
        html_out = m2html.report(malicious, timedelta(0), "")
        self.assertNotIn("<script>alert", html_out)
        self.assertIn("&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt; &amp; &#x27;quotes&#x27;", html_out)
        self.assertNotIn("<img src=x", html_out)

    def test_timezone_offset(self):
        items_dict = {
            "m_tz": {
                "id": "m_tz",
                "content": "Midnight sync note",
                "category": "personal",
                "created_at": "2026-10-01T23:30:00Z",
            }
        }
        jst = timedelta(hours=9)
        html_out = m2html.report(items_dict, jst, "+09:00")
        self.assertIn("2026-10-02 08:30", html_out)
        self.assertIn("Times shown in UTC+09:00.", html_out)

    def test_category_filtering(self):
        items_dict = {it["id"]: it for it in self.sample_memories}
        html_out = m2html.report(items_dict, timedelta(0), "", category_filter="work")
        self.assertIn("Deliver quarterly performance metrics", html_out)
        self.assertNotIn("Learned Rust zero-cost", html_out)
        self.assertIn("Total: 1 · Categories: 1", html_out)

    def test_envelope_unwrapping(self):
        nested = {"memories": self.sample_memories}
        self.assertEqual(len(m2html.unwrap_memories(nested)), 3)

        single = {"id": "single", "content": "standalone note"}
        self.assertEqual(len(m2html.unwrap_memories(single)), 1)

        with self.assertRaises(ValueError):
            m2html.unwrap_memories(12345)

    def test_load_and_deduplication(self):
        f1 = self.tmp / "f1.json"
        f2 = self.tmp / "f2.json"
        f1.write_text(json.dumps([self.sample_memories[0], self.sample_memories[1]]), encoding="utf-8")
        f2.write_text(json.dumps([self.sample_memories[1], self.sample_memories[2]]), encoding="utf-8")

        loaded = m2html.load([str(f1), str(f2)])
        self.assertEqual(len(loaded), 3)
        self.assertIn("mem_01_work", loaded)
        self.assertIn("mem_02_learning", loaded)
        self.assertIn("mem_03_interests", loaded)

    def test_synthetic_id_allocation(self):
        f = self.tmp / "no_ids.json"
        items_missing_id = [
            {"content": "Note 1", "category": "other"},
            {"content": "Note 2", "category": "other"},
            {"id": "auto_existing", "content": "Explicit ID"},
        ]
        f.write_text(json.dumps(items_missing_id), encoding="utf-8")
        loaded = m2html.load([str(f)])
        self.assertEqual(len(loaded), 3)
        self.assertIn("auto_existing", loaded)

    def test_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "report.html"
        src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

        count1 = m2html.convert([str(src)], str(dest))
        self.assertEqual(count1, 3)
        self.assertTrue(dest.exists())

        # Second call without overwrite must raise FileExistsError
        with self.assertRaises(FileExistsError):
            m2html.convert([str(src)], str(dest), overwrite=False)

        # With overwrite=True it should succeed
        count2 = m2html.convert([str(src)], str(dest), overwrite=True)
        self.assertEqual(count2, 3)

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_memories).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = m2html.load(["-"])
            self.assertEqual(len(loaded), 3)
            self.assertIn("mem_01_work", loaded)

    def test_parse_time_robustness(self):
        self.assertEqual(
            m2html.parse_time("2026-10-02T12:00:00Z"),
            datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(m2html.parse_time("invalid"))
        self.assertIsNone(m2html.parse_time(None))
        self.assertIsNone(m2html.parse_time("9999-12-31T23:59:59-14:00"))

    def test_main_cli_execution(self):
        src = self.tmp / "mems.json"
        dest = self.tmp / "cli_mems.html"
        src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

        ret = m2html.main([str(dest), str(src), "--title", "CLI Test Report"])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        content = dest.read_text(encoding="utf-8")
        self.assertIn("CLI Test Report", content)


if __name__ == "__main__":
    unittest.main()
