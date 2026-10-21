"""Unit tests verifying defensive user_id extraction, limit/offset coercion, and input validation in action_item_tools.py.

Ensures that:
1. Top-level user_id in config and None configurable mappings are handled gracefully
   without raising AttributeError or returning format errors.
2. String or invalid limit and offset arguments are defensively coerced and clamped to [1, 500]
   and >= 0, preventing TypeError comparisons.
3. Empty or None descriptions in create_action_item_tool and action_item_id in update_action_item_tool
   are validated and rejected immediately.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure scratch workspace is on sys.path
TEST_DIR = Path(__file__).resolve().parent
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

# Create dummy modules for imports if not present
from types import ModuleType
for mod_name in [
    "langchain_core", "langchain_core.tools", "langchain_core.runnables",
    "config", "config.action_item_reminder_triggers",
    "database", "database.action_items",
    "utils", "utils.messaging", "utils.messaging.undo", "utils.messaging.projection", "utils.messaging.turn_context",
    "utils.notifications", "utils.model_text", "utils.user_clock",
    "utils.retrieval", "utils.retrieval.chat_scope", "utils.retrieval.turn_refs"
]:
    if mod_name not in sys.modules:
        m = ModuleType(mod_name)
        sys.modules[mod_name] = m

# Mock specific functions
sys.modules["langchain_core.tools"].tool = lambda f: f
sys.modules["langchain_core.runnables"].RunnableConfig = dict
sys.modules["utils.messaging.undo"].record_write = MagicMock()
sys.modules["utils.messaging.projection"].surface_runtime = MagicMock(get=MagicMock(return_value=None))
sys.modules["utils.messaging.turn_context"].phone_reminder_confirmation = MagicMock()
sys.modules["config.action_item_reminder_triggers"].action_item_write_affects_reminder = MagicMock(return_value=False)
sys.modules["database.action_items"].get_action_items = MagicMock(return_value=[])
sys.modules["database.action_items"].get_action_item = MagicMock(return_value={"id": "item1", "description": "test"})
sys.modules["database.action_items"].create_action_item = MagicMock(return_value={"id": "new1"})
sys.modules["database.action_items"].update_action_item = MagicMock(return_value={"id": "item1"})
sys.modules["utils.notifications"].send_action_item_completed_notification = MagicMock()
sys.modules["utils.notifications"].send_action_item_created_notification = MagicMock()
sys.modules["utils.notifications"].send_action_item_data_message = MagicMock()
sys.modules["utils.notifications"].sync_action_item_reminder = MagicMock()
sys.modules["utils.model_text"].count_header = MagicMock(return_value="Action Items (0)")
sys.modules["utils.model_text"].format_date = MagicMock(return_value="2026-10-21")
sys.modules["utils.model_text"].format_instant = MagicMock(return_value="2026-10-21 12:00")
sys.modules["utils.model_text"].truncation_note = MagicMock(return_value="")
sys.modules["utils.user_clock"].clock_for_config = MagicMock()
sys.modules["utils.retrieval.chat_scope"].apply_chat_scope_dates = MagicMock(return_value=(None, None, None))
sys.modules["utils.retrieval.chat_scope"].chat_scope_from_config = MagicMock(return_value=None)
sys.modules["utils.retrieval.turn_refs"].register_record_ref = MagicMock()
sys.modules["utils.retrieval.turn_refs"].resolve_edit_ref = MagicMock(return_value=("item1", None))

from action_item_tools import (
    _extract_user_context,
    get_action_items_tool,
    create_action_item_tool,
    update_action_item_tool,
)


class TestActionItemToolsHardening(unittest.TestCase):
    """Test user context extraction, limit/offset coercion, and input validation."""

    def test_extract_user_context_nested(self):
        cfg = {"configurable": {"user_id": "nested_user_123"}}
        uid, conf, err = _extract_user_context(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "nested_user_123")
        self.assertEqual(conf.get("user_id"), "nested_user_123")

    def test_extract_user_context_top_level(self):
        cfg = {"user_id": "top_level_user_456"}
        uid, conf, err = _extract_user_context(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "top_level_user_456")
        self.assertIsInstance(conf, dict)

    def test_extract_user_context_none_configurable(self):
        cfg = {"configurable": None, "user_id": "fallback_user_789"}
        uid, conf, err = _extract_user_context(cfg)
        self.assertIsNone(err)
        self.assertEqual(uid, "fallback_user_789")
        self.assertIsInstance(conf, dict)

    def test_extract_user_context_missing_uid(self):
        cfg = {"configurable": {}}
        uid, conf, err = _extract_user_context(cfg)
        self.assertIsNotNone(err)
        self.assertIn("User ID not found in configuration", err)

    def test_extract_user_context_none_cfg(self):
        uid, conf, err = _extract_user_context(None)
        self.assertIsNotNone(err)
        self.assertIn("Configuration not available", err)

    def test_get_action_items_string_limit_offset(self):
        # Should coerce string limit and offset without TypeError: '>' not supported
        res = get_action_items_tool(
            limit="50",  # string type
            offset="10", # string type
            config={"configurable": {"user_id": "user1"}}
        )
        self.assertNotIn("Error", res)

    def test_get_action_items_clamped_bounds(self):
        # Limit > 500 clamped to 500, negative limit clamped to 1
        res = get_action_items_tool(
            limit=9999,
            offset=-5,
            config={"user_id": "user1"}
        )
        self.assertNotIn("Error", res)

    def test_create_action_item_validation(self):
        # Missing or empty description rejected
        self.assertIn("Description is required", create_action_item_tool(None, config={"user_id": "u1"}))
        self.assertIn("Description is required", create_action_item_tool("   ", config={"user_id": "u1"}))

    def test_update_action_item_validation(self):
        # Missing or empty action_item_id rejected
        self.assertIn("action_item_id is required", update_action_item_tool(None, config={"user_id": "u1"}))
        self.assertIn("action_item_id is required", update_action_item_tool("  ", config={"user_id": "u1"}))


if __name__ == "__main__":
    unittest.main()
