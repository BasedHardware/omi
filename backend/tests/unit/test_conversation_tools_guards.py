"""Unit tests for conversation_tools input validation, coercions, and guards."""

from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import AutoMockModule, stub_modules

fake_model_text = AutoMockModule("utils.model_text")
fake_model_text.withheld_note.return_value = ""
fake_model_text.truncation_note.return_value = ""
fake_model_text.none_found.side_effect = lambda entity, scope: f"No {entity} found {scope}"
fake_model_text.format_date.side_effect = lambda dt, clock: str(dt)

fake_chat_scope = AutoMockModule("utils.retrieval.chat_scope")
fake_chat_scope.chat_scope_from_config.return_value = None
fake_chat_scope.apply_chat_scope_dates.side_effect = lambda s, sd, ed: (sd, ed, None)

fake_mcp_transcript_search = AutoMockModule("utils.conversations.mcp_transcript_search")
fake_mcp_transcript_search.chat_transcript_coverage_note.return_value = ""

# Ensure dependencies are stubbed before importing conversation_tools
with stub_modules({
    "database.conversations": AutoMockModule("database.conversations"),
    "database.users": AutoMockModule("database.users"),
    "database.vector_db": AutoMockModule("database.vector_db"),
    "database.auth": AutoMockModule("database.auth"),
    "models.other": AutoMockModule("models.other"),
    "utils.conversations.factory": AutoMockModule("utils.conversations.factory"),
    "utils.conversations.mcp_transcript_search": fake_mcp_transcript_search,
    "utils.conversations.render": AutoMockModule("utils.conversations.render"),
    "utils.conversations.search": AutoMockModule("utils.conversations.search"),
    "utils.metrics": AutoMockModule("utils.metrics"),
    "utils.observability.fallback": AutoMockModule("utils.observability.fallback"),
    "utils.retrieval.chat_scope": fake_chat_scope,
    "utils.retrieval.turn_refs": AutoMockModule("utils.retrieval.turn_refs"),
    "utils.model_text": fake_model_text,
    "utils.user_clock": AutoMockModule("utils.user_clock"),
    "utils.conversations.transcript_for_llm": AutoMockModule("utils.conversations.transcript_for_llm"),
}):
    import utils.retrieval.tools.conversation_tools as conv_module
    from utils.retrieval.tools.conversation_tools import (
        get_conversations_tool,
        search_conversations_tool,
        _safe_int,
        _get_config_and_uid,
    )


class TestConversationToolsGuards:
    """Hermetic tests verifying input validation, guards, and type coercions."""

    def test_safe_int_coercions(self):
        """_safe_int must coerce integers and numeric strings while rejecting booleans, None, and text."""
        assert _safe_int(20, 0) == 20
        assert _safe_int("10", 0) == 10
        assert _safe_int("0", 5) == 0
        assert _safe_int("-1", 0) == -1
        assert _safe_int(5.8, 0) == 5

        # Booleans must fall back to default
        assert _safe_int(True, 20) == 20
        assert _safe_int(False, 20) == 20

        # None and text must fall back to default
        assert _safe_int(None, 20) == 20
        assert _safe_int("abc", 20) == 20
        assert _safe_int([], 20) == 20

    def test_get_config_and_uid_resolution(self):
        """_get_config_and_uid must safely resolve uid from configurable, top-level user_id, or uid."""
        # Top-level user_id
        cfg1, conf1, uid1 = _get_config_and_uid({"user_id": "usr_top"})
        assert uid1 == "usr_top"
        assert conf1 == {}

        # Top-level uid
        cfg2, conf2, uid2 = _get_config_and_uid({"uid": "uid_top"})
        assert uid2 == "uid_top"

        # Nested configurable user_id
        cfg3, conf3, uid3 = _get_config_and_uid({"configurable": {"user_id": "usr_nested"}})
        assert uid3 == "usr_nested"
        assert conf3 == {"user_id": "usr_nested"}

        # Empty config
        cfg4, conf4, uid4 = _get_config_and_uid({})
        assert uid4 is None
        assert conf4 == {}

        # None config with no context var
        cfg5, conf5, uid5 = _get_config_and_uid(None)
        assert uid5 is None
        assert cfg5 is None

    def test_search_query_empty_or_whitespace_or_none(self):
        """search_conversations_tool must reject empty, whitespace, None, or non-string queries."""
        config = {"configurable": {"user_id": "user_123"}}

        # Empty string
        res_empty = search_conversations_tool.invoke({"query": ""}, config=config)
        assert res_empty == "Error: Search query cannot be empty"

        # Whitespace only
        res_ws = search_conversations_tool.invoke({"query": "   \n\t  "}, config=config)
        assert res_ws == "Error: Search query cannot be empty"

        # None query via invoke
        res_none = search_conversations_tool.invoke({"query": None}, config=config)
        assert res_none == "Error: Search query cannot be empty"

        # Direct func call with non-string
        assert search_conversations_tool.func(query=12345, config=config) == "Error: Search query cannot be empty"

    def test_get_conversations_string_limit_and_offset_coercion(self):
        """get_conversations_tool must coerce string limit, offset, and max_transcript_segments without TypeError."""
        config = {"configurable": {"user_id": "user_123"}}

        with patch.object(conv_module.conversations_db, "get_conversations", return_value=[]), \
             patch.object(conv_module, "_cap_conversations_for_llm", return_value=([], 0, False)), \
             patch.object(conv_module, "_withheld_conversation_notes", return_value=""):

            res = get_conversations_tool.invoke({
                "limit": "10",
                "offset": "5",
                "max_transcript_segments": "20",
            }, config=config)

            assert "No conversations found" in res
            conv_module.conversations_db.get_conversations.assert_called_once()
            call_kwargs = conv_module.conversations_db.get_conversations.call_args[1]
            assert call_kwargs["limit"] == 10
            assert call_kwargs["offset"] == 5

    def test_search_conversations_string_limit_coercion(self):
        """search_conversations_tool must coerce string limit and max_transcript_segments without TypeError."""
        config = {"configurable": {"user_id": "user_123"}}

        with patch.object(conv_module, "_parse_exact_search_reference", return_value=None), \
             patch.object(conv_module, "keyword_search_conversation_ids", return_value=[]), \
             patch.object(conv_module.vector_db, "query_vectors", return_value=[]), \
             patch.object(conv_module, "search_chat_transcript_chunks", return_value=MagicMock(searched=False)), \
             patch.object(conv_module, "merge_chat_conversation_ids", return_value=[]), \
             patch.object(conv_module.conversations_db, "get_conversations_by_id", return_value=[]), \
             patch.object(conv_module, "_withheld_conversation_notes", return_value=""):

            res = search_conversations_tool.invoke({
                "query": "project update",
                "limit": "5",
                "max_transcript_segments": "15",
            }, config=config)

            assert "No conversations found" in res

    def test_invalid_date_type_returns_error_not_attribute_error(self):
        """Non-string start_date or end_date must return clear error message instead of crashing with AttributeError."""
        config = {"configurable": {"user_id": "user_123"}}

        # Non-string start_date in get_conversations_tool
        res_get = get_conversations_tool.func(start_date=12345, config=config)
        assert "Error: start_date must be an ISO format string: 12345" in res_get

        # Non-string end_date in get_conversations_tool
        res_get_end = get_conversations_tool.func(end_date=True, config=config)
        assert "Error: end_date must be an ISO format string: True" in res_get_end

        # Non-string start_date in search_conversations_tool
        res_search = search_conversations_tool.func(query="test", start_date=99999, config=config)
        assert "Error: start_date must be an ISO format string: 99999" in res_search

    def test_all_person_ids_resilience_to_none_or_malformed_segments(self):
        """Collection of all_person_ids must not crash when transcript_segments contains None or non-dict items."""
        config = {"configurable": {"user_id": "user_123"}}

        malformed_conv = [{
            "id": "conv_1",
            "is_locked": False,
            "discarded": False,
            "transcript_segments": [
                None,
                "invalid_segment",
                123,
                {"person_id": "p_valid_1"},
            ],
        }]

        with patch.object(conv_module.conversations_db, "get_conversations", return_value=malformed_conv), \
             patch.object(conv_module, "_cap_conversations_for_llm", return_value=(malformed_conv, 1, False)), \
             patch.object(conv_module.users_db, "get_people_by_ids", return_value=[{"id": "p_valid_1", "name": "Alice"}]), \
             patch.object(conv_module, "deserialize_conversation") as mock_deser, \
             patch.object(conv_module, "_render_addressable_conversations", return_value="Conversation rendered successfully"), \
             patch.object(conv_module, "_bounded_result", side_effect=lambda res, *args, **kwargs: res), \
             patch.object(conv_module, "_withheld_conversation_notes", return_value=""):

            mock_conv_obj = MagicMock()
            mock_conv_obj.transcript_segments = []
            mock_conv_obj.id = "conv_1"
            mock_deser.return_value = mock_conv_obj

            res = get_conversations_tool.func(include_transcript=True, config=config)
            assert "Conversation rendered successfully" in res
            conv_module.users_db.get_people_by_ids.assert_called_once_with("user_123", ["p_valid_1"])

    def test_statuses_comma_separated_and_list_support(self):
        """Statuses filter should support comma-separated strings as well as lists/tuples."""
        config = {"configurable": {"user_id": "user_123"}}

        with patch.object(conv_module.conversations_db, "get_conversations", return_value=[]), \
             patch.object(conv_module, "_cap_conversations_for_llm", return_value=([], 0, False)), \
             patch.object(conv_module, "_withheld_conversation_notes", return_value=""):

            # Comma-separated string
            get_conversations_tool.func(statuses="processing, completed", config=config)
            call_statuses1 = conv_module.conversations_db.get_conversations.call_args[1]["statuses"]
            assert call_statuses1 == ["processing", "completed"]

            # List of strings
            get_conversations_tool.func(statuses=["in_progress", "archived"], config=config)
            call_statuses2 = conv_module.conversations_db.get_conversations.call_args[1]["statuses"]
            assert call_statuses2 == ["in_progress", "archived"]

    def test_missing_config_and_uid(self):
        """Missing config or missing uid returns clean informative error."""
        # Config None
        with patch.object(conv_module, "_agent_config", return_value=None):
            assert get_conversations_tool.func(config=None) == "Error: Configuration not available"
            assert search_conversations_tool.func(query="test", config=None) == "Error: Configuration not available"

        # UID missing
        assert get_conversations_tool.func(config={}) == "Error: User ID not found in configuration"
        assert search_conversations_tool.func(query="test", config={}) == "Error: User ID not found in configuration"
