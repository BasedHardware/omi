"""Tests for Omi conversations full-text search index recipe."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

script_path = Path(__file__).resolve().parent.parent / "examples" / "conversations_search_index.py"
spec = importlib.util.spec_from_file_location("conversations_search_index", script_path)
csi = importlib.util.module_from_spec(spec)
spec.loader.exec_module(csi)


class TestConversationsSearchIndex(unittest.TestCase):
    def test_tokenize_and_stopwords(self):
        text = "The quick brown fox jumps over the lazy dog in Python!"
        tokens = csi.tokenize(text)
        self.assertNotIn("the", tokens)
        self.assertNotIn("in", tokens)
        self.assertIn("quick", tokens)
        self.assertIn("python", tokens)

    def test_extract_conversations(self):
        raw = '[{"id": "conv-1", "title": "Database Tuning"}]'
        res = csi.extract_conversations(raw)
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["id"], "conv-1")

    def test_build_and_search_index(self):
        conv1 = {
            "id": "c-1",
            "title": "PostgreSQL Optimization",
            "structured": {"overview": "Query indexing and vacuum settings"},
            "transcript_segments": [{"text": "We should add a composite index on user_id"}],
        }
        conv2 = {
            "id": "c-2",
            "title": "Design Sprint Kickoff",
            "structured": {"overview": "Figma mockups and user interviews"},
            "transcript_segments": [{"text": "Reviewing Figma components"}],
        }

        index_data = csi.build_index([conv1, conv2])
        self.assertEqual(index_data["metadata"]["total_documents"], 2)

        # Search for database terms
        results1 = csi.search_index(index_data, "postgresql composite index")
        self.assertEqual(len(results1), 1)
        self.assertEqual(results1[0]["id"], "c-1")
        self.assertGreaterEqual(results1[0]["match_score"], 2)

        # Search for design terms
        results2 = csi.search_index(index_data, "figma mockups")
        self.assertEqual(len(results2), 1)
        self.assertEqual(results2[0]["id"], "c-2")

        # Empty / no match
        self.assertEqual(len(csi.search_index(index_data, "blockchain")), 0)


if __name__ == "__main__":
    unittest.main()
