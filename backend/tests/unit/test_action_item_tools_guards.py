"""Unit tests for action_item_tools input coercion, guards, and UID resolution."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import AutoMockModule, stub_modules

# Ensure dependencies are stubbed before importing action_item_tools
with stub_modules({
    "utils.messaging.undo": AutoMockModule("utils.messaging.undo"),
    "utils.messaging.projection": AutoMockModule("utils.messaging.projection"),
    "utils.messaging.turn_context": AutoMockModule("utils.messaging.turn_context"),
    "config.action_item_reminder_triggers": AutoMockModule("config.action_item_reminder_triggers"),
    "database.action_items": AutoMockModule("database.action_items"),
    "utils.notifications": AutoMockModule("utils.notifications"),
    "utils.model_text": AutoMockModule("utils.model_text"),
    "utils.user_clock": AutoMockModule("utils.user_clock"),
    "utils.retrieval.chat_scope": AutoMockModule("utils.retrieval.chat_scope"),
    "utils.retrieval.turn_refs": AutoMockModule("utils.retrieval.turn_refs"),
}):
    import utils.retrieval.tools.action_item_tools as ait_module
    from utils.retrieval.tools.action_item_tools import (
        get_action_items_tool,
        create_action_item_tool,
        update_action_item_tool,
        _safe_int,
        _get_config_and_uid,
    )


class TestActionItemToolsGuards:
    """Hermetic unit tests verifying input validation, guards, and UID resolution."""

    def test_safe_int_coercion(self):
        """_safe_int must coerce numeric strings and ints, rejecting booleans, None, and invalid types."""
        assert _safe_int(10, 50) == 10
        assert _safe_int("25", 50) == 25
        assert _safe_int("0", 50) == 0
        assert _safe_int(None, 50) == 50
        assert _safe_int(True, 50) == 50
        assert _safe_int(False, 50) == 50
        assert _safe_int("invalid", 50) == 50
        assert _safe_int([], 50) == 50

    def test_get_config_and_uid_fallbacks(self):
        """_get_config_and_uid resolves uid from configurable, top-level user_id, or uid."""
        # Configurable nested
        cfg1, conf1, uid1 = _get_config_and_uid({"configurable": {"user_id": "user_nested"}})
        assert uid1 == "user_nested"
        assert conf1 == {"user_id": "user_nested"}

        # Top-level user_id
        cfg2, conf2, uid2 = _get_config_and_uid({"user_id": "user_top"})
        assert uid2 == "user_top"
        assert conf2 == {}

        # Top-level uid
        cfg3, conf3, uid3 = _get_config_and_uid({"uid": "uid_top"})
        assert uid3 == "uid_top"

        # None config
        cfg4, conf4, uid4 = _get_config_and_uid(None)
        assert cfg4 is None
        assert conf4 == {}
        assert uid4 is None

    def test_get_action_items_config_errors(self):
        """Missing config or user_id returns clear error message."""
        # Direct call with config=None
        assert get_action_items_tool.func(config=None) == "Error: Configuration not available"

        # Call with empty config
        assert get_action_items_tool.invoke({}, config={}) == "Error: User ID not found in configuration"

    def test_get_action_items_coercion_and_resolution(self):
        """get_action_items_tool safely coerces limit/offset and retrieves tasks with top-level config."""
        config = {"user_id": "user_123"}
        with patch.object(ait_module.action_items_db, "get_action_items", return_value=[]) as mock_get, \
             patch.object(ait_module, "apply_chat_scope_dates", return_value=(None, None, None)), \
             patch.object(ait_module, "chat_scope_from_config", return_value=None), \
             patch.object(ait_module, "clock_for_config", return_value=MagicMock()):

            res = get_action_items_tool.invoke({
                "limit": "20",
                "offset": "5",
            }, config=config)
            assert "No action items found" in res
            mock_get.assert_called_once_with(
                uid="user_123",
                conversation_id=None,
                completed=None,
                start_date=None,
                end_date=None,
                due_start_date=None,
                due_end_date=None,
                limit=20,
                offset=5,
            )

    def test_get_action_items_date_guards(self):
        """Non-string date arguments return validation error rather than raising AttributeError."""
        config = {"user_id": "user_123"}
        with patch.object(ait_module, "apply_chat_scope_dates", side_effect=lambda s, st, en: (st, en, None)), \
             patch.object(ait_module, "chat_scope_from_config", return_value=None), \
             patch.object(ait_module, "clock_for_config", return_value=MagicMock()):

            res_start = get_action_items_tool.func(start_date=12345, config=config)
            assert "Error: Invalid start_date format" in res_start

            res_end = get_action_items_tool.func(end_date=True, config=config)
            assert "Error: Invalid end_date format" in res_end

            res_due_start = get_action_items_tool.func(due_start_date=12345, config=config)
            assert "Error: Invalid due_start_date format" in res_due_start

            res_due_end = get_action_items_tool.func(due_end_date=True, config=config)
            assert "Error: Invalid due_end_date format" in res_due_end

    def test_create_action_item_description_guards(self):
        """create_action_item_tool validates description presence and string type."""
        config = {"configurable": {"user_id": "user_123"}}

        # Empty description
        assert create_action_item_tool.invoke({"description": ""}, config=config) == "Error: Description is required to create an action item."

        # Whitespace description
        assert create_action_item_tool.invoke({"description": "   \n\t  "}, config=config) == "Error: Description is required to create an action item."

        # None description
        assert create_action_item_tool.invoke({"description": None}, config=config) == "Error: Description is required to create an action item."

        # Non-string description
        assert create_action_item_tool.func(description=98765, config=config) == "Error: Description is required to create an action item."

    def test_create_action_item_due_at_guards(self):
        """Non-string due_at returns validation error instead of crashing."""
        config = {"user_id": "user_123"}
        with patch.object(ait_module, "clock_for_config", return_value=MagicMock()):
            res = create_action_item_tool.func(description="Buy milk", due_at=12345, config=config)
            assert "Error: Invalid due_at format" in res

    def test_update_action_item_id_and_description_guards(self):
        """update_action_item_tool guards against missing action_item_id and empty description update."""
        config = {"configurable": {"user_id": "user_123"}}

        # Missing or empty action_item_id
        assert update_action_item_tool.invoke({"action_item_id": ""}, config=config) == "Error: action_item_id is required to update an action item."
        assert update_action_item_tool.invoke({"action_item_id": None}, config=config) == "Error: action_item_id is required to update an action item."
        assert update_action_item_tool.func(action_item_id=1234, config=config) == "Error: action_item_id is required to update an action item."

        # Non-string due_at
        with patch.object(ait_module, "resolve_edit_ref", return_value=("task_1", None)), \
             patch.object(ait_module.action_items_db, "get_action_item", return_value={"id": "task_1", "description": "Existing"}), \
             patch.object(ait_module, "clock_for_config", return_value=MagicMock()):

            res_due = update_action_item_tool.func(action_item_id="task_1", due_at=12345, config=config)
            assert "Error: Invalid due_at format" in res_due

            # Empty description update
            res_desc_empty = update_action_item_tool.invoke({
                "action_item_id": "task_1",
                "description": "",
            }, config=config)
            assert res_desc_empty == "Error: Description cannot be empty."

            res_desc_ws = update_action_item_tool.invoke({
                "action_item_id": "task_1",
                "description": "   \n  ",
            }, config=config)
            assert res_desc_ws == "Error: Description cannot be empty."
