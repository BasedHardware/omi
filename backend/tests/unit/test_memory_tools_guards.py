"""Unit tests for memory_tools input coercion, guards, and UID resolution."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import load_module_fresh

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(scope="module")
def mt_module():
    """Load memory_tools hermetically with load_module_fresh."""
    return load_module_fresh(
        "utils.retrieval.tools._memory_tools_guards_test",
        str(BACKEND_DIR / "utils" / "retrieval" / "tools" / "memory_tools.py"),
    )


class TestMemoryToolsGuards:
    """Hermetic unit tests verifying input validation, guards, and UID resolution."""

    def test_safe_int_coercions(self, mt_module):
        """_safe_int safely coerces ints and numeric strings while rejecting invalid types."""
        _safe_int = mt_module._safe_int
        assert _safe_int(10, 50) == 10
        assert _safe_int("25", 50) == 25
        assert _safe_int("0", 50) == 0
        assert _safe_int(None, 50) == 50
        assert _safe_int(True, 50) == 50
        assert _safe_int(False, 50) == 50
        assert _safe_int("invalid", 50) == 50
        assert _safe_int({}, 50) == 50

    def test_get_config_and_uid_resolution(self, mt_module):
        """_get_config_and_uid resolves user ID from configurable, top-level user_id, or uid."""
        _get_config_and_uid = mt_module._get_config_and_uid

        # Configurable nested
        cfg1, conf1, uid1 = _get_config_and_uid({"configurable": {"user_id": "usr_nested"}})
        assert uid1 == "usr_nested"
        assert conf1 == {"user_id": "usr_nested"}

        # Top-level user_id
        cfg2, conf2, uid2 = _get_config_and_uid({"user_id": "usr_top"})
        assert uid2 == "usr_top"
        assert conf2 == {}

        # Top-level uid
        cfg3, conf3, uid3 = _get_config_and_uid({"uid": "uid_top"})
        assert uid3 == "uid_top"

        # None config
        cfg4, conf4, uid4 = _get_config_and_uid(None)
        assert cfg4 is None
        assert conf4 == {}
        assert uid4 is None

    def test_missing_config_and_uid_errors(self, mt_module):
        """Missing config or user_id returns clear error message."""
        get_memories_tool = mt_module.get_memories_tool
        search_memories_tool = mt_module.search_memories_tool

        # Direct call with config=None
        assert get_memories_tool.func(config=None) == "Error: Configuration not available"
        assert search_memories_tool.func(query="test", config=None) == "Error: Configuration not available"

        # Call with empty config
        assert get_memories_tool.invoke({}, config={}) == "Error: User ID not found in configuration"
        assert search_memories_tool.invoke({"query": "test"}, config={}) == "Error: User ID not found in configuration"

    def test_get_memories_string_limit_and_offset_coercion(self, mt_module):
        """get_memories_tool coerces string limit/offset and calls MemoryService.read cleanly."""
        config = {"user_id": "user_123"}
        mock_service = MagicMock()
        mock_service.read.return_value = []

        with patch.object(mt_module, "MemoryService", return_value=mock_service), patch.object(
            mt_module, "omit_channel_private", side_effect=lambda items, cfg: items
        ), patch.object(
            mt_module, "cap_items_for_llm", side_effect=lambda items, m: (items, len(items), False)
        ), patch.object(
            mt_module, "_channel_empty_memories", return_value=None
        ), patch.object(
            mt_module, "apply_chat_scope_dates", return_value=(None, None, None)
        ), patch.object(
            mt_module, "chat_scope_from_config", return_value=None
        ), patch.object(
            mt_module, "clock_for_config", return_value=MagicMock()
        ):

            res = mt_module.get_memories_tool.invoke(
                {
                    "limit": "25",
                    "offset": "10",
                },
                config=config,
            )

            assert "No memories found" in res
            # offset 10 + limit 25 = target_end 35
            mock_service.read.assert_called_once_with("user_123", limit=35, offset=0)

    def test_get_memories_invalid_dates_handled_safely(self, mt_module):
        """Non-string start_date or end_date returns validation error instead of crashing on .replace()."""
        config = {"user_id": "user_123"}
        with patch.object(
            mt_module, "apply_chat_scope_dates", side_effect=lambda s, st, en: (st, en, None)
        ), patch.object(mt_module, "chat_scope_from_config", return_value=None), patch.object(
            mt_module, "clock_for_config", return_value=MagicMock()
        ):

            res_start = mt_module.get_memories_tool.func(start_date=12345, config=config)
            assert "Error: Invalid start_date format" in res_start

            res_end = mt_module.get_memories_tool.func(end_date=True, config=config)
            assert "Error: Invalid end_date format" in res_end

    def test_search_memories_empty_or_none_query(self, mt_module):
        """search_memories_tool rejects empty, whitespace, None, and non-string queries."""
        config = {"configurable": {"user_id": "user_123"}}
        search_memories_tool = mt_module.search_memories_tool

        # Empty string
        assert search_memories_tool.invoke({"query": ""}, config=config) == "Error: Search query cannot be empty"

        # Whitespace only
        assert (
            search_memories_tool.invoke({"query": "   \n\t  "}, config=config) == "Error: Search query cannot be empty"
        )

        # None query
        assert search_memories_tool.invoke({"query": None}, config=config) == "Error: Search query cannot be empty"

        # Non-string query via func
        assert search_memories_tool.func(query=12345, config=config) == "Error: Search query cannot be empty"

    def test_search_memories_string_limit_coercion(self, mt_module):
        """search_memories_tool coerces string limit and searches without TypeError in min()."""
        config = {"user_id": "user_123"}
        mock_service = MagicMock()
        mock_service.search.return_value = []

        with patch.object(mt_module, "MemoryService", return_value=mock_service), patch.object(
            mt_module, "_channel_empty_memories", return_value=None
        ), patch.object(mt_module, "apply_chat_scope_dates", return_value=(None, None, None)), patch.object(
            mt_module, "chat_scope_from_config", return_value=None
        ), patch.object(
            mt_module, "clock_for_config", return_value=MagicMock()
        ):

            res = mt_module.search_memories_tool.invoke(
                {
                    "query": "favorite coffee",
                    "limit": "15",
                },
                config=config,
            )

            assert "No memories found matching 'favorite coffee'" in res
            mock_service.search.assert_called_once_with("user_123", "favorite coffee", limit=15)
