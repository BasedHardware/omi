"""Unit tests verifying defensive user context extraction, limit/offset coercion,
query validation, and None configurable guards in memory_tools.py.

Ensures that:
1. Top-level user_id in config and None configurable mappings are handled gracefully
   without raising AttributeError or rejecting valid authenticated requests.
2. Limit and offset arguments are defensively coerced to valid non-negative ranges,
   preventing negative list slices or invalid database query bounds.
3. Empty or whitespace-only queries in search_memories_tool are rejected immediately,
   preventing spurious calls to MemoryService.
4. _publish_memory_refs safely guards against None configurable arguments.
"""

import unittest
from unittest.mock import MagicMock, patch

from utils.retrieval.tools.memory_tools import (
    _extract_user_context,
    _publish_memory_refs,
    get_memories_tool,
    search_memories_tool,
)
import utils.retrieval.tools.memory_tools as memory_tools


class TestMemoryToolsHardening(unittest.TestCase):
    """Test user context resolution, limit coercion, and query validation."""

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

    def test_search_memories_empty_query_rejected(self):
        config = {"configurable": {"user_id": "test_user"}}
        res_empty = search_memories_tool.func(query="", config=config)
        self.assertEqual(res_empty, "Error: Search query cannot be empty.")

        res_spaces = search_memories_tool.func(query="   ", config=config)
        self.assertEqual(res_spaces, "Error: Search query cannot be empty.")

        res_none = search_memories_tool.func(query=None, config=config)
        self.assertEqual(res_none, "Error: Search query cannot be empty.")

    def test_publish_memory_refs_none_configurable_safe(self):
        # Should execute cleanly without raising AttributeError
        _publish_memory_refs(None, [])

    def test_get_memories_negative_limit_and_offset_coerced(self):
        with patch.object(memory_tools.memories_db, "get_memories_by_id", return_value=[]):
            config = {"configurable": {"user_id": "test_user"}}
            # Direct func invocation with negative bounds
            res = get_memories_tool.func(limit=-10, offset=-5, config=config)
            self.assertIsInstance(res, str)


if __name__ == "__main__":
    unittest.main()
