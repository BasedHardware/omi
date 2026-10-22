"""Unit tests for edit_tools input validation, guards, and owner UID resolution."""

from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import AutoMockModule, stub_modules

# Ensure dependencies are stubbed before importing edit_tools
with stub_modules({
    "database.conversations": AutoMockModule("database.conversations"),
    "database.users": AutoMockModule("database.users"),
    "database.chat_edits": AutoMockModule("database.chat_edits"),
    "utils.memory.memory_service": AutoMockModule("utils.memory.memory_service"),
    "utils.memory.memory_system": AutoMockModule("utils.memory.memory_system"),
    "utils.memory.canonical_memory_adapter": AutoMockModule("utils.memory.canonical_memory_adapter"),
    "utils.messaging.undo": AutoMockModule("utils.messaging.undo"),
    "utils.mcp_server": AutoMockModule("utils.mcp_server"),
    "utils.mcp_server.handlers": AutoMockModule("utils.mcp_server.handlers"),
    "utils.mcp_server.handlers.other": AutoMockModule("utils.mcp_server.handlers.other"),
    "utils.retrieval.turn_refs": AutoMockModule("utils.retrieval.turn_refs"),
}):
    import utils.retrieval.tools.edit_tools as et_module
    from utils.retrieval.tools.edit_tools import (
        owner,
        _get_configurable,
        update_conversation,
        rename_person,
        edit_memory,
        delete_memory,
    )


class TestEditToolsGuards:
    """Hermetic unit tests verifying input validation, guards, and owner UID resolution."""

    def test_owner_uid_resolution(self):
        """owner() extracts uid from nested configurable, top-level user_id, or top-level uid."""
        # Nested configurable user_id
        assert owner({"configurable": {"user_id": "usr_nested"}}) == "usr_nested"

        # Top-level user_id
        assert owner({"user_id": "usr_top"}) == "usr_top"

        # Top-level uid
        assert owner({"uid": "uid_top"}) == "uid_top"

        # Configurable takes precedence
        assert owner({"user_id": "usr_top", "configurable": {"user_id": "usr_nested"}}) == "usr_nested"

    def test_owner_missing_raises_permission_error(self):
        """owner() raises PermissionError when config is missing or lacks user ID."""
        with pytest.raises(PermissionError, match="Authenticated owner required"):
            owner(None)

        with pytest.raises(PermissionError, match="Authenticated owner required"):
            owner({})

        with pytest.raises(PermissionError, match="Authenticated owner required"):
            owner({"configurable": {}})

        with pytest.raises(PermissionError, match="Authenticated owner required"):
            owner({"configurable": None})

    def test_get_configurable_resilience(self):
        """_get_configurable safely returns dict even when configurable is None or invalid."""
        assert _get_configurable(None) == {}
        assert _get_configurable({}) == {}
        assert _get_configurable({"configurable": None}) == {}
        assert _get_configurable({"configurable": "not_dict"}) == {}
        assert _get_configurable({"configurable": {"key": "val"}}) == {"key": "val"}

    def test_update_conversation_guards(self):
        """update_conversation validates correction, title, overview, and length limits."""
        config = {"configurable": {"user_id": "user_123"}}

        with patch.object(et_module, "resolve_edit_ref", return_value=("conv_123", None)), \
             patch.object(et_module, "tool_error", side_effect=lambda code, msg: f"Error [{code}]: {msg}"):

            # Empty or whitespace correction
            res_no_corr = update_conversation.func(
                conversation_id="conv_123",
                correction="",
                title="New Title",
                config=config,
            )
            assert "invalid_correction" in res_no_corr

            # None correction
            res_none_corr = update_conversation.func(
                conversation_id="conv_123",
                correction=None,
                title="New Title",
                config=config,
            )
            assert "invalid_correction" in res_none_corr

            # Correction provided but neither title nor overview
            res_neither = update_conversation.func(
                conversation_id="conv_123",
                correction="User asked to fix title",
                title=None,
                overview=None,
                config=config,
            )
            assert "invalid_correction" in res_neither

            # Empty title
            res_empty_title = update_conversation.func(
                conversation_id="conv_123",
                correction="Fix title",
                title="   ",
                config=config,
            )
            assert "invalid_title" in res_empty_title

            # Empty overview
            res_empty_overview = update_conversation.func(
                conversation_id="conv_123",
                correction="Fix overview",
                overview="   ",
                config=config,
            )
            assert "invalid_overview" in res_empty_overview

    def test_rename_person_guards(self):
        """rename_person requires non-empty person_id and name."""
        config = {"configurable": {"user_id": "user_123"}}

        # Missing person_id
        assert rename_person.func(person_id=None, name="Alice", config=config) == "Error: person_id is required."
        assert rename_person.func(person_id="", name="Alice", config=config) == "Error: person_id is required."
        assert rename_person.func(person_id="   ", name="Alice", config=config) == "Error: person_id is required."

        # Missing name
        assert rename_person.func(person_id="p_123", name=None, config=config) == "Error: name is required."
        assert rename_person.func(person_id="p_123", name="", config=config) == "Error: name is required."
        assert rename_person.func(person_id="p_123", name="   ", config=config) == "Error: name is required."

    def test_edit_memory_guards(self):
        """edit_memory requires non-empty memory_id and content."""
        config = {"configurable": {"user_id": "user_123"}}

        # Missing memory_id
        assert edit_memory.func(memory_id=None, content="New content", config=config) == "Error: memory_id is required."
        assert edit_memory.func(memory_id="", content="New content", config=config) == "Error: memory_id is required."
        assert edit_memory.func(memory_id="   ", content="New content", config=config) == "Error: memory_id is required."

        # Missing content
        assert edit_memory.func(memory_id="mem_123", content=None, config=config) == "Error: memory content must contain 1 to 20000 characters."
        assert edit_memory.func(memory_id="mem_123", content="", config=config) == "Error: memory content must contain 1 to 20000 characters."
        assert edit_memory.func(memory_id="mem_123", content="   ", config=config) == "Error: memory content must contain 1 to 20000 characters."

    def test_delete_memory_guards(self):
        """delete_memory requires non-empty memory_id."""
        config = {"configurable": {"user_id": "user_123"}}

        # Missing memory_id
        assert delete_memory.func(memory_id=None, config=config) == "Error: memory_id is required."
        assert delete_memory.func(memory_id="", config=config) == "Error: memory_id is required."
        assert delete_memory.func(memory_id="   ", config=config) == "Error: memory_id is required."

    def test_config_with_none_configurable_resilience(self):
        """Tools handle config with {'configurable': None} without raising AttributeError."""
        config_none_configurable = {"configurable": None, "user_id": "user_top"}

        with patch.object(et_module, "resolve_edit_ref", return_value=("ref_123", None)):
            # update_conversation with top-level user_id and None configurable
            res = update_conversation.func(
                conversation_id="conv_1",
                correction="",
                title="T",
                config=config_none_configurable,
            )
            # Should reach validation without crashing on config.get('configurable').get('user_id')
            assert res is not None

            # rename_person with top-level user_id and None configurable
            with patch.object(et_module.users, "get_person", return_value=None):
                res_rename = rename_person.func(
                    person_id="p_1",
                    name="Bob",
                    config=config_none_configurable,
                )
                assert res_rename == "Error: person not found."
