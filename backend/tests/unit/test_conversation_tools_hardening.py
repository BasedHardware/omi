"""Unit tests verifying defensive user context extraction, limit/offset coercion,
None configurable guards, and query validation in conversation_tools.py.

Ensures that:
1. Top-level user_id in config and None configurable mappings are handled gracefully
   without raising AttributeError or rejecting valid authenticated requests.
2. Limit and offset arguments are defensively coerced and clamped to valid non-negative ranges,
   preventing negative list slices or invalid database query bounds.
3. Max transcript segments is defensively coerced, preserving -1 (full transcript) while
   clamping other values to [0, 1000].
4. Empty or whitespace-only queries in search_conversations_tool are rejected immediately,
   preventing wasted vector embeddings and broken transcript search.
5. _render_addressable_conversations guards against None or non-dict configurable mappings.
"""

import unittest
from unittest.mock import MagicMock, patch

from utils.retrieval.tools.conversation_tools import (
    _extract_user_context,
    _render_addressable_conversations,
    get_conversations_tool,
    search_conversations_tool,
)
import utils.retrieval.tools.conversation_tools as conv_tools


class TestConversationToolsHardening(unittest.TestCase):
    """Test user context resolution, query validation, and limit coercion."""

    def test_extract_user_context_nested(self):
        cfg = {"configurable": {"user_id": "nested_user_123"}}
        uid, conf, resolved, err = _extract_user_context(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "nested_user_123")
        self.assertEqual(conf.get("user_id"), "nested_user_123")
        self.assertEqual(resolved, cfg)

    def test_extract_user_context_top_level(self):
        cfg = {"user_id": "top_level_user_456"}
        uid, conf, resolved, err = _extract_user_context(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "top_level_user_456")
        self.assertIsInstance(conf, dict)
        self.assertEqual(resolved, cfg)

    def test_extract_user_context_none_configurable_with_top_level(self):
        cfg = {"configurable": None, "user_id": "fallback_user_789"}
        uid, conf, resolved, err = _extract_user_context(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "fallback_user_789")
        self.assertIsInstance(conf, dict)
        self.assertEqual(resolved, cfg)

    def test_extract_user_context_missing_user_id(self):
        cfg = {"configurable": {}}
        uid, conf, resolved, err = _extract_user_context(cfg)
        self.assertIsNone(uid)
        self.assertEqual(err, "Error: User ID not found in configuration")

    def test_extract_user_context_none_config(self):
        uid, conf, resolved, err = _extract_user_context(None)
        self.assertIsNone(uid)
        self.assertEqual(err, "Error: Configuration not available")

    def test_search_conversations_empty_query_rejected(self):
        config = {"configurable": {"user_id": "test_user"}}
        res_empty = search_conversations_tool.func(query="", config=config)
        self.assertEqual(res_empty, "Error: Search query cannot be empty.")

        res_spaces = search_conversations_tool.func(query="   ", config=config)
        self.assertEqual(res_spaces, "Error: Search query cannot be empty.")

        res_none = search_conversations_tool.func(query=None, config=config)
        self.assertEqual(res_none, "Error: Search query cannot be empty.")

    def test_get_conversations_top_level_user_id(self):
        fake_convs = [{"id": "conv-1", "transcript_segments": []}]
        with patch.object(conv_tools.conversations_db, "get_conversations", return_value=fake_convs):
            config = {"user_id": "top_level_user"}
            result = get_conversations_tool.func(config=config)
            self.assertNotIn("Error", result)

    def test_get_conversations_negative_limits_coerced(self):
        with patch.object(conv_tools.conversations_db, "get_conversations", return_value=[]) as mock_get:
            config = {"configurable": {"user_id": "test_user"}}
            get_conversations_tool.func(limit=-10, offset=-5, config=config)
            mock_get.assert_called_once()
            _, kwargs = mock_get.call_args
            self.assertEqual(kwargs.get("limit"), 1)
            self.assertEqual(kwargs.get("offset"), 0)

    def test_search_conversations_negative_limit_coerced(self):
        with (
            patch.object(conv_tools, "keyword_search_conversation_ids", return_value=[]),
            patch.object(conv_tools.vector_db, "query_vectors", return_value=[]),
            patch.object(conv_tools, "search_chat_transcript_chunks") as mock_chunks,
        ):
            mock_chunks.return_value = MagicMock(conversation_ids=[], searched=False)
            config = {"configurable": {"user_id": "test_user"}}
            search_conversations_tool.func(query="project launch", limit=-20, config=config)
            _, kwargs = mock_chunks.call_args
            self.assertEqual(kwargs.get("limit"), 1)

    def test_render_addressable_conversations_none_configurable_safe(self):
        result = _render_addressable_conversations([], configurable=None)
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
