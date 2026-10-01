"""Tests for conversations to Jupyter notebook exporter (.ipynb).

Validates nbformat v4 output structure, metadata, cells, cell IDs, transcript evaluation literal,
envelope unwrapping, collision resolution, overwrite behavior, float safety, and UTF-8 handling.
"""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_to_jupyter.py"
spec = importlib.util.spec_from_file_location("conversations_to_jupyter", script_path)
assert spec is not None and spec.loader is not None
c2j = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2j)


class TestConversationsToJupyter(unittest.TestCase):
    def test_single_conversation_cells_generation(self):
        conv = {
            "id": "conv-12345",
            "started_at": "2026-10-01T15:30:00Z",
            "source": "omi",
            "structured": {
                "title": "Quarterly Planning",
                "category": "work",
                "overview": "Discussed roadmap and KPIs.",
                "action_items": [
                    {"description": "Send proposal to client", "completed": True},
                    {"description": "Schedule follow-up call", "completed": False},
                ],
            },
            "transcript_segments": [
                {"speaker": 0, "start": 0.0, "end": 4.5, "text": "Let's review Q4 goals."},
                {"speaker": "Alice", "start": 5.0, "end": 10.2, "text": "We exceeded targets."},
            ],
        }

        cells = c2j.conversation_to_notebook_cells(conv)
        self.assertEqual(len(cells), 2)

        # Markdown cell check
        md_cell = cells[0]
        self.assertEqual(md_cell["cell_type"], "markdown")
        self.assertIn("id", md_cell)
        md_text = "".join(md_cell["source"])
        self.assertIn("## Quarterly Planning", md_text)
        self.assertIn("Discussed roadmap and KPIs.", md_text)
        self.assertIn("- [x] Send proposal to client", md_text)
        self.assertIn("- [ ] Schedule follow-up call", md_text)

        # Code cell check
        code_cell = cells[1]
        self.assertEqual(code_cell["cell_type"], "code")
        self.assertIn("id", code_cell)
        code_text = "".join(code_cell["source"])
        self.assertIn("transcript = [", code_text)
        self.assertIn("len(transcript)", code_text)

        # Parse and execute/evaluate the python code literal
        parsed = ast.parse(code_text)
        self.assertEqual(len(parsed.body), 2)  # Assign statement + Expr statement
        stmt = parsed.body[0]
        assert isinstance(stmt, ast.Assign)
        transcript_literal = ast.literal_eval(stmt.value)
        self.assertIsInstance(transcript_literal, list)
        self.assertEqual(len(transcript_literal), 2)
        self.assertEqual(transcript_literal[0]["speaker"], "Speaker 0")
        self.assertEqual(transcript_literal[1]["speaker"], "Alice")
        self.assertEqual(transcript_literal[1]["text"], "We exceeded targets.")

    def test_build_notebook_structure(self):
        cells = [c2j.create_markdown_cell("# Title")]
        nb = c2j.build_notebook(cells)

        self.assertEqual(nb["nbformat"], 4)
        self.assertEqual(nb["nbformat_minor"], 5)
        self.assertIn("metadata", nb)
        self.assertEqual(nb["metadata"]["language_info"]["name"], "python")
        self.assertEqual(len(nb["cells"]), 1)
        self.assertIn("id", nb["cells"][0])

    def test_export_notebooks_directory_mode_and_collision(self):
        conv1 = {
            "id": "1111-aaaa-bbbb",
            "started_at": "2026-10-01T10:00:00Z",
            "structured": {"title": "Strategy Session", "overview": "First note content for meeting A"},
        }
        conv2 = {
            "id": "1111-aaaa-cccc",
            "started_at": "2026-10-01T11:00:00Z",
            "structured": {"title": "Strategy Session", "overview": "Second note content for meeting B"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            exported = c2j.export_notebooks([conv1, conv2], output_dir=out_dir)

            self.assertEqual(len(exported), 2)
            file1 = out_dir / "2026-10-01_strategy_session_1111-aaa.ipynb"
            file2 = out_dir / "2026-10-01_strategy_session_1111-aaa_2.ipynb"

            self.assertTrue(file1.exists())
            self.assertTrue(file2.exists())

            nb1 = json.loads(file1.read_text(encoding="utf-8"))
            nb2 = json.loads(file2.read_text(encoding="utf-8"))
            self.assertEqual(nb1["nbformat"], 4)
            self.assertEqual(nb2["nbformat"], 4)

            # Assert content is segregated to the correct files
            content1 = file1.read_text(encoding="utf-8")
            content2 = file2.read_text(encoding="utf-8")
            self.assertIn("First note content for meeting A", content1)
            self.assertIn("1111-aaaa-bbbb", content1)
            self.assertNotIn("Second note content for meeting B", content1)

            self.assertIn("Second note content for meeting B", content2)
            self.assertIn("1111-aaaa-cccc", content2)
            self.assertNotIn("First note content for meeting A", content2)

    def test_overwrite_flag_in_export_notebooks(self):
        conv = {
            "id": "2222-bbbb-cccc",
            "started_at": "2026-10-01T10:00:00Z",
            "structured": {"title": "Team Sync", "overview": "Updated sync note"},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            target_file = out_dir / "2026-10-01_team_sync_2222-bbb.ipynb"
            target_file.write_text("{\"old\": true}", encoding="utf-8")

            # Without overwrite -> creates _2
            exported = c2j.export_notebooks([conv], output_dir=out_dir, overwrite=False)
            self.assertEqual(len(exported), 1)
            disambiguated = out_dir / "2026-10-01_team_sync_2222-bbb_2.ipynb"
            self.assertTrue(disambiguated.exists())
            self.assertEqual(target_file.read_text(encoding="utf-8"), "{\"old\": true}")

            # With overwrite -> replaces target_file
            exported_ow = c2j.export_notebooks([conv], output_dir=out_dir, overwrite=True)
            self.assertEqual(exported_ow[0], target_file)
            nb = json.loads(target_file.read_text(encoding="utf-8"))
            self.assertEqual(nb["nbformat"], 4)
            self.assertIn("Updated sync note", target_file.read_text(encoding="utf-8"))

    def test_non_finite_floats_sanitized(self):
        conv = {
            "id": "nan-test",
            "transcript_segments": [
                {"speaker": 1, "start": float("nan"), "end": float("inf"), "text": "Valid text segment"},
            ],
        }

        cells = c2j.conversation_to_notebook_cells(conv)
        code_text = "".join(cells[1]["source"])
        self.assertNotIn(": NaN", code_text)
        self.assertNotIn(": Infinity", code_text)
        self.assertNotIn(": null", code_text)

        # Must parse as valid strict JSON
        nb = c2j.build_notebook(cells)
        nb_json = json.dumps(nb, allow_nan=False)
        self.assertIsInstance(json.loads(nb_json), dict)

    def test_extract_conversations_envelopes(self):
        item = {"id": "123", "structured": {"title": "Test"}}

        # Bare list
        self.assertEqual(len(c2j.extract_conversations([item])), 1)

        # Envelopes
        self.assertEqual(len(c2j.extract_conversations({"conversations": [item]})), 1)
        self.assertEqual(len(c2j.extract_conversations({"items": [item]})), 1)
        self.assertEqual(len(c2j.extract_conversations({"data": [item]})), 1)
        self.assertEqual(len(c2j.extract_conversations({"results": [item]})), 1)

        # Single object
        self.assertEqual(len(c2j.extract_conversations(item)), 1)

        # Invalid
        self.assertEqual(len(c2j.extract_conversations({})), 0)
        self.assertEqual(len(c2j.extract_conversations(123)), 0)

    def test_format_timestamp(self):
        self.assertEqual(c2j.format_timestamp(0), "00:00")
        self.assertEqual(c2j.format_timestamp(65), "01:05")
        self.assertEqual(c2j.format_timestamp(3665), "01:01:05")
        self.assertEqual(c2j.format_timestamp(None), "00:00")
        self.assertEqual(c2j.format_timestamp("invalid"), "00:00")
        self.assertEqual(c2j.format_timestamp(float("nan")), "00:00")

    def test_slugify(self):
        self.assertEqual(c2j.slugify("Hello World! 2026"), "hello_world_2026")
        self.assertEqual(c2j.slugify(""), "conversation")

    def test_unicode_and_special_characters_preserved(self):
        conv = {
            "id": "unicode-test",
            "started_at": "2026-10-01T12:00:00Z",
            "structured": {
                "title": "Reunião de Alinhamento - Cosméticos & Botox Capilar 🇧🇷",
                "overview": "Tratamento de queratina e lissage brésilien.",
            },
            "transcript_segments": [
                {"speaker": "João", "start": 0.0, "end": 2.0, "text": "Olá, tudo bem com você?"},
                {"speaker": "Élise", "start": 2.5, "end": 5.0, "text": "Très bien, merci! C'est parfait."},
            ],
        }

        cells = c2j.conversation_to_notebook_cells(conv)
        md_text = "".join(cells[0]["source"])
        code_text = "".join(cells[1]["source"])

        self.assertIn("Botox Capilar 🇧🇷", md_text)
        self.assertIn("lissage brésilien", md_text)
        self.assertIn("Olá, tudo bem com você?", code_text)
        self.assertIn("Très bien, merci!", code_text)


if __name__ == "__main__":
    unittest.main()
