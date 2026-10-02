"""Tests for the memories_to_digest recipe."""

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

RECIPE_PATH = Path(__file__).resolve().parent.parent / "examples" / "memories_to_digest.py"
spec = importlib.util.spec_from_file_location("memories_to_digest", RECIPE_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load recipe from {RECIPE_PATH}")
m2digest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2digest)


class TestMemoriesToDigest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.now = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
        self.sample_memories = [
            {
                "id": "mem_01_work",
                "content": "Deliver quarterly performance metrics report",
                "category": "work",
                "tags": ["roadmap", "q3"],
                "visibility": "private",
                "created_at": "2026-09-20T10:00:00Z",
            },
            {
                "id": "mem_02_learning",
                "content": "Learned Rust zero-cost abstractions and ownership patterns",
                "category": "learnings",
                "tags": ["rust", "systems"],
                "visibility": "public",
                "created_at": "2026-09-22T14:30:00+02:00",
            },
            {
                "id": "mem_03_skills",
                "content": "Mastered async concurrency in Go and Python",
                "category": "skills",
                "tags": ["python", "go"],
                "visibility": "public",
                "created_at": "2026-10-01T08:15:00Z",
            },
            {
                "id": "mem_04_untagged",
                "content": "Spoke with design team about mobile UI refresh",
                "category": "work",
                "tags": None,
                "visibility": "public",
                "created_at": "2026-10-01T16:00:00Z",
            },
        ]

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_parse_offset_boundaries(self):
        self.assertEqual(m2digest.parse_offset("+09:00"), timedelta(hours=9))
        self.assertEqual(m2digest.parse_offset("-05:30"), timedelta(hours=-5, minutes=-30))
        self.assertEqual(m2digest.parse_offset("+14:00"), timedelta(hours=14))
        self.assertEqual(m2digest.parse_offset("-14:00"), timedelta(hours=-14))
        with self.assertRaises(ValueError):
            m2digest.parse_offset("invalid")
        with self.assertRaises(ValueError):
            m2digest.parse_offset("+15:00")
        with self.assertRaises(ValueError):
            m2digest.parse_offset("+05:70")

    def test_parse_time_robustness(self):
        self.assertEqual(
            m2digest.parse_time("2026-10-02T12:00:00Z"),
            datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            m2digest.parse_time("2026-10-02T14:00:00+02:00"),
            datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.assertIsNone(m2digest.parse_time("invalid"))
        self.assertIsNone(m2digest.parse_time(None))

    def test_extract_tags(self):
        self.assertEqual(m2digest.extract_tags(["rust", "systems!"]), ["rust", "systems"])
        self.assertEqual(m2digest.extract_tags("python, fast-api, ai#"), ["python", "fast-api", "ai"])
        self.assertEqual(m2digest.extract_tags(None), [])
        # Test deduplication per item
        self.assertEqual(m2digest.extract_tags(["work", "work", "ops"]), ["work", "ops"])
        self.assertEqual(m2digest.extract_tags("work, work, ops"), ["work", "ops"])

    def test_clean_markdown_cell(self):
        self.assertEqual(m2digest.clean_markdown_cell("Simple text"), "Simple text")
        self.assertEqual(m2digest.clean_markdown_cell("Pipe | inside"), "Pipe \\| inside")
        self.assertEqual(m2digest.clean_markdown_cell("Line\nBreak"), "Line Break")
        self.assertEqual(m2digest.clean_markdown_cell(None), "")
        self.assertEqual(
            m2digest.clean_markdown_cell("Bold *text* & `#tag`"),
            "Bold \\*text\\* & \\`\\#tag\\`",
        )

    def test_load_and_envelope_unwrapping(self):
        for key in ("memories", "items", "data", "results"):
            envelope = {key: self.sample_memories}
            f = self.tmp / f"env_{key}.json"
            f.write_text(json.dumps(envelope), encoding="utf-8")
            loaded = m2digest.load([str(f)])
            self.assertEqual(len(loaded), 4)

        # Bare dict
        bare_f = self.tmp / "bare.json"
        bare_f.write_text(json.dumps({"id": "single", "content": "Single memory"}), encoding="utf-8")
        loaded_bare = m2digest.load([str(bare_f)])
        self.assertEqual(len(loaded_bare), 1)
        self.assertIn("single", loaded_bare)

        # Unrecognized non-memory objects must be ignored without phantom rows
        err_f = self.tmp / "err.json"
        err_f.write_text(json.dumps({"error": "Unauthorized", "status_code": 401}), encoding="utf-8")
        loaded_err = m2digest.load([str(err_f)])
        self.assertEqual(len(loaded_err), 0)

        # Numeric id coercion
        num_f = self.tmp / "num.json"
        num_f.write_text(json.dumps([{"id": 42, "content": "Numeric id memory"}]), encoding="utf-8")
        loaded_num = m2digest.load([str(num_f)])
        self.assertIn("42", loaded_num)

    def test_digest_metrics_and_categories(self):
        items_dict = {it["id"]: it for it in self.sample_memories}
        md = m2digest.build_digest(items_dict, now=self.now)

        self.assertIn("# Omi Memories Digest", md)
        self.assertIn("**Total Memories:** 4", md)
        self.assertIn("**Categories:** 3", md)
        self.assertIn("**Tagged:** 3 (75.0%)", md)
        self.assertIn("**Private:** 1 (25.0%)", md)

        # Check Category Breakdown
        self.assertIn("💼 Work", md)
        self.assertIn("🧠 Learnings", md)
        self.assertIn("🎯 Skills", md)

        # Check Top Knowledge Tags
        self.assertIn("## Top Knowledge Tags", md)
        self.assertIn("`#roadmap`", md)
        self.assertIn("`#rust`", md)
        self.assertIn("`#python`", md)

        # Check Recent Highlights
        self.assertIn("## Recent Memory Highlights", md)
        self.assertIn("Spoke with design team about mobile UI refresh", md)
        self.assertIn("mem_04_untagged", md)

    def test_unknown_category_and_highlight_truncation(self):
        long_content = "A" * 150
        item = {
            "id": "mem_special",
            "content": long_content,
            "category": "my_custom|cat*",
            "tags": ["deep-learning"],
            "created_at": "2026-10-02T10:00:00Z",
        }
        md = m2digest.build_digest({"mem_special": item}, now=self.now)
        # Category label must be sanitized
        self.assertIn("My Custom\\|Cat\\*", md)
        # Highlight preview must be truncated to <= 120 chars with ...
        self.assertIn("A" * 117 + "...", md)
        self.assertNotIn("A" * 150, md)

    def test_empty_export_handling(self):
        md = m2digest.build_digest({})
        self.assertIn("_No memories found matching the export criteria._", md)

    def test_category_filtering(self):
        items_dict = {it["id"]: it for it in self.sample_memories}
        work_md = m2digest.build_digest(items_dict, category_filter="work", now=self.now)
        self.assertIn("**Total Memories:** 2", work_md)
        self.assertIn("**Categories:** 1", work_md)
        self.assertNotIn("Learned Rust zero-cost", work_md)

    def test_exclusive_creation_and_atomic_overwrite(self):
        src = self.tmp / "input.json"
        dest = self.tmp / "digest.md"
        src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

        count = m2digest.convert([str(src)], destination=str(dest))
        self.assertEqual(count, 4)
        self.assertTrue(dest.exists())

        # Second call without overwrite must fail
        with self.assertRaises(FileExistsError):
            m2digest.convert([str(src)], destination=str(dest), overwrite=False)

        # Overwrite=True succeeds
        count2 = m2digest.convert([str(src)], destination=str(dest), overwrite=True)
        self.assertEqual(count2, 4)

    def test_failed_write_cleans_up_destination(self):
        src = self.tmp / "input_err.json"
        dest = self.tmp / "digest_err.md"
        src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

        real_open = Path.open

        def failing_open(self_path, *args, **kwargs):
            handle = real_open(self_path, *args, **kwargs)
            mode = kwargs.get("mode", args[0] if args else "r")
            if "xb" in mode and str(self_path) == str(dest):
                handle.write = unittest.mock.Mock(side_effect=OSError("Disk full"))
            return handle

        with patch.object(Path, "open", autospec=True, side_effect=failing_open):
            with self.assertRaises(OSError):
                m2digest.convert([str(src)], destination=str(dest), overwrite=False)
        self.assertFalse(dest.exists())

    def test_stdin_input_stream(self):
        payload = json.dumps(self.sample_memories).encode("utf-8")
        with patch("sys.stdin.buffer.read", return_value=payload):
            loaded = m2digest.load(["-"])
            self.assertEqual(len(loaded), 4)

    def test_main_cli_execution(self):
        src = self.tmp / "cli_input.json"
        dest = self.tmp / "cli_digest.md"
        src.write_text(json.dumps(self.sample_memories), encoding="utf-8")

        ret = m2digest.main([str(src), "-o", str(dest), "--utc-offset", "+09:00"])
        self.assertEqual(ret, 0)
        self.assertTrue(dest.exists())
        content = dest.read_text(encoding="utf-8")
        self.assertIn("# Omi Memories Digest", content)


if __name__ == "__main__":
    unittest.main()
