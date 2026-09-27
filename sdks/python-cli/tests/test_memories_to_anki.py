"""Hermetic unit tests for the memories to Anki flashcards (.tsv) exporter (#19360).

Pins TSV formatting, card prompts, tags normalization, envelope unwrapping,
category and tag filtering, deduplication, and safe file overwrite guarantees.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "memories_to_anki.py"
spec = importlib.util.spec_from_file_location("memories_to_anki", script_path)
m2anki = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m2anki)


class TestMemoriesToAnki(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.sample_memories = [
            {
                "id": "mem_01_learnings",
                "category": "learnings",
                "content": "KiCad library table nicknames require escaping double quotes.",
                "tags": ["electronics", "eda tool"],
                "created_at": "2026-09-17T09:00:00Z",
            },
            {
                "id": "mem_02_skills",
                "category": "skills",
                "content": "Proficient in Python standard library and FastAPI backend design.",
                "tags": ["python", "fastapi"],
                "created_at": "2026-09-16T14:15:00Z",
            },
            {
                "id": "mem_03_work",
                "category": "work",
                "content": "Prefers asynchronous communication for pull request reviews.",
                "tags": ["workflow", "management"],
                "created_at": "2025-05-10T12:00:00Z",
            },
        ]

    def tearDown(self):
        self._tmp.cleanup()

    def test_basic_tsv_export(self):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps(self.sample_memories, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "deck.tsv"

        count = m2anki.convert([str(source)], str(destination))
        self.assertEqual(count, 3)

        lines = destination.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 3)

        # Verify TSV columns: Front \t Back \t Tags
        front, back, tags = lines[0].split("\t")
        self.assertEqual(front, "What did I record regarding Learnings?")
        self.assertEqual(back, "KiCad library table nicknames require escaping double quotes.")
        self.assertIn("omi", tags)
        self.assertIn("learnings", tags)
        self.assertIn("electronics", tags)
        self.assertIn("eda_tool", tags)  # Spaces in tags replaced with underscore
        self.assertIn("year_2026", tags)

    def test_custom_prompt_template(self):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps([self.sample_memories[0]], ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "deck.tsv"

        m2anki.convert(
            [str(source)],
            str(destination),
            prompt_template="What key insight did I note about {category}?",
        )

        content = destination.read_text(encoding="utf-8").strip()
        front, _, _ = content.split("\t")
        self.assertEqual(front, "What key insight did I note about Learnings?")

    def test_broken_prompt_template_falls_back_safely(self):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps([self.sample_memories[0]], ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "deck.tsv"

        m2anki.convert(
            [str(source)],
            str(destination),
            prompt_template="Invalid template {missing_key}",
        )

        content = destination.read_text(encoding="utf-8").strip()
        front, _, _ = content.split("\t")
        self.assertEqual(front, "What did I record regarding Learnings?")

    def test_category_filter(self):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps(self.sample_memories, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "deck.tsv"

        count = m2anki.convert([str(source)], str(destination), category_filter="SKILLS")
        self.assertEqual(count, 1)

        lines = destination.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 1)
        self.assertIn("Proficient in Python", lines[0])

    def test_tag_filter(self):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps(self.sample_memories, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "deck.tsv"

        count = m2anki.convert([str(source)], str(destination), tag_filter="eda tool")
        self.assertEqual(count, 1)

        lines = destination.read_text(encoding="utf-8").strip().split("\n")
        self.assertEqual(len(lines), 1)
        self.assertIn("KiCad", lines[0])

    def test_envelope_unwrapping(self):
        destination = self.tmp / "deck.tsv"

        for key in ("memories", "items", "data", "results"):
            source = self.tmp / f"wrapped_{key}.json"
            source.write_text(json.dumps({key: self.sample_memories[:1]}), encoding="utf-8")
            dest = self.tmp / f"out_{key}.tsv"
            count = m2anki.convert([str(source)], str(dest))
            self.assertEqual(count, 1)

        # Single memory item
        single_source = self.tmp / "single.json"
        single_source.write_text(json.dumps(self.sample_memories[0]), encoding="utf-8")
        dest_single = self.tmp / "out_single.tsv"
        count_single = m2anki.convert([str(single_source)], str(dest_single))
        self.assertEqual(count_single, 1)

    def test_empty_memories_export(self):
        source = self.tmp / "empty.json"
        source.write_text(json.dumps({"memories": []}), encoding="utf-8")
        destination = self.tmp / "empty.tsv"

        count = m2anki.convert([str(source)], str(destination))
        self.assertEqual(count, 0)
        self.assertTrue(destination.exists())
        self.assertEqual(destination.read_text(encoding="utf-8"), "")

    def test_multi_source_deduplication(self):
        src1 = self.tmp / "p1.json"
        src2 = self.tmp / "p2.json"
        src1.write_text(json.dumps([self.sample_memories[0], self.sample_memories[1]]), encoding="utf-8")
        src2.write_text(json.dumps([self.sample_memories[1], self.sample_memories[2]]), encoding="utf-8")
        destination = self.tmp / "dedup.tsv"

        count = m2anki.convert([str(src1), str(src2)], str(destination))
        self.assertEqual(count, 3)

    def test_overwrite_protection_and_force(self):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps(self.sample_memories), encoding="utf-8")
        destination = self.tmp / "deck.tsv"
        destination.write_text("existing content", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            m2anki.convert([str(source)], str(destination), force=False)

        self.assertEqual(destination.read_text(encoding="utf-8"), "existing content")

        # Overwrite with force=True
        count = m2anki.convert([str(source)], str(destination), force=True)
        self.assertEqual(count, 3)
        self.assertIn("KiCad", destination.read_text(encoding="utf-8"))

    def test_bad_payload_leaves_no_file(self):
        bad_source = self.tmp / "bad.json"
        bad_source.write_text('{"unknown_root": 123}', encoding="utf-8")
        destination = self.tmp / "should_not_exist.tsv"

        with self.assertRaises(ValueError):
            m2anki.convert([str(bad_source)], str(destination))

        self.assertFalse(destination.exists())

    def test_cli_execution_success(self):
        source = self.tmp / "memories.json"
        source.write_text(json.dumps(self.sample_memories, ensure_ascii=False), encoding="utf-8")
        destination = self.tmp / "cli_out.tsv"

        result = subprocess.run(
            [sys.executable, str(script_path), str(destination), str(source)],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("Exported 3 Anki flashcard(s)", result.stdout)
        self.assertTrue(destination.exists())

    def test_cli_execution_failure(self):
        destination = self.tmp / "cli_out.tsv"
        result = subprocess.run(
            [sys.executable, str(script_path), str(destination), str(self.tmp / "nonexistent.json")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("Export failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
