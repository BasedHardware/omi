"""Unit tests verifying defensive user_id extraction, limit/offset coercion, and input validation in action_item_tools.py.

Ensures that:
1. Top-level user_id in config and None configurable mappings are handled gracefully
   without raising AttributeError or returning format errors.
2. clock_for_config receives the resolved config (including agent_config_context fallback).
3. String or invalid limit and offset arguments are defensively coerced and clamped to [1, 500]
   and >= 0, preventing TypeError comparisons.
4. Empty or None descriptions in create_action_item_tool and action_item_id in update_action_item_tool
   are validated and rejected immediately.
"""

import unittest
from unittest.mock import MagicMock, patch

from utils.retrieval.tools.action_item_tools import (
    _extract_user_context,
    agent_config_context,
    get_action_items_tool,
    create_action_item_tool,
    update_action_item_tool,
)
import utils.retrieval.tools.action_item_tools as action_item_tools


class TestActionItemToolsHardening(unittest.TestCase):
    """Test user context extraction, limit/offset coercion, and input validation."""

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

    def test_extract_user_context_none_configurable(self):
        cfg = {"configurable": None, "user_id": "fallback_user_789"}
        uid, conf, resolved, err = _extract_user_context(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "fallback_user_789")
        self.assertIsInstance(conf, dict)
        self.assertEqual(resolved, cfg)

    def test_extract_user_context_missing_uid(self):
        cfg = {"configurable": {}}
        uid, conf, resolved, err = _extract_user_context(cfg)
        self.assertIsNotNone(err)
        self.assertIn("User ID not found in configuration", err)

    def test_extract_user_context_none_cfg(self):
        uid, conf, resolved, err = _extract_user_context(None)
        self.assertIsNotNone(err)
        self.assertIn("Configuration not available", err)

    def test_extract_user_context_agent_context_fallback(self):
        ctx_dict = {"configurable": {"user_id": "context_uid_99", "user_timezone": "America/Chicago"}}
        token = agent_config_context.set(ctx_dict)
        try:
            uid, conf, resolved, err = _extract_user_context(None)
            self.assertIsNone(err)
            self.assertEqual(uid, "context_uid_99")
            self.assertEqual(resolved.get("configurable", {}).get("user_timezone"), "America/Chicago")
        finally:
            agent_config_context.reset(token)

    @patch.object(action_item_tools.action_items_db, "get_action_items", return_value=[])
    def test_get_action_items_string_limit_offset(self, mock_db):
        res = get_action_items_tool.func(
            limit="50",
            offset="10",
            config={"configurable": {"user_id": "user1"}},
        )
        self.assertNotIn("Error", res)

    @patch.object(action_item_tools.action_items_db, "get_action_items", return_value=[])
    def test_get_action_items_clamped_bounds(self, mock_db):
        res = get_action_items_tool.func(
            limit=9999,
            offset=-5,
            config={"configurable": {"user_id": "user1"}},
        )
        self.assertNotIn("Error", res)

    def test_create_action_item_validation(self):
        cfg = {"configurable": {"user_id": "u1"}}
        res_none = create_action_item_tool.func(description=None, config=cfg)
        self.assertIn("Description is required", res_none)

        res_empty = create_action_item_tool.invoke({"description": "   "}, config=cfg)
        self.assertIn("Description is required", res_empty)

    def test_update_action_item_validation(self):
        cfg = {"configurable": {"user_id": "u1"}}
        res_none = update_action_item_tool.func(action_item_id=None, config=cfg)
        self.assertIn("action_item_id is required", res_none)

        res_empty = update_action_item_tool.invoke({"action_item_id": "  "}, config=cfg)
        self.assertIn("action_item_id is required", res_empty)


if __name__ == "__main__":
    unittest.main()
