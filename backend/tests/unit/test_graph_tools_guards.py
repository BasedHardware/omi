"""Unit tests for graph_tools input validation, hops clamping, and UID resolution."""

from unittest.mock import MagicMock, patch
import pytest

from testing.import_isolation import AutoMockModule, stub_modules

with stub_modules({
    "utils.memory.kg_graph_traversal": AutoMockModule("utils.memory.kg_graph_traversal"),
    "utils.log_sanitizer": AutoMockModule("utils.log_sanitizer"),
}):
    import utils.retrieval.tools.graph_tools as gt_module
    from utils.retrieval.tools.graph_tools import (
        _resolve_uid,
        traverse_knowledge_graph_tool,
    )


class TestGraphToolsGuards:
    """Hermetic unit tests for graph_tools."""

    def test_resolve_uid_nested(self):
        """Resolves user_id or uid from nested configurable."""
        assert _resolve_uid({"configurable": {"user_id": "usr_1"}}) == "usr_1"
        assert _resolve_uid({"configurable": {"uid": "usr_2"}}) == "usr_2"

    def test_resolve_uid_top_level_fallback(self):
        """Resolves user_id or uid from top-level config dict."""
        assert _resolve_uid({"user_id": "usr_top"}) == "usr_top"
        assert _resolve_uid({"uid": "uid_top"}) == "uid_top"

    def test_resolve_uid_contextvar_fallback(self):
        """Resolves user ID from agent_config_context when config is None."""
        with patch.object(gt_module, "_agent_config", return_value={"configurable": {"user_id": "ctx_user"}}):
            assert _resolve_uid(None) == "ctx_user"

    def test_resolve_uid_missing_or_invalid(self):
        """Returns None when no valid user ID exists."""
        with patch.object(gt_module, "_agent_config", return_value=None):
            assert _resolve_uid(None) is None
            assert _resolve_uid({}) is None
            assert _resolve_uid({"configurable": None}) is None
            assert _resolve_uid({"configurable": {}}) is None
            assert _resolve_uid({"configurable": {"user_id": ""}}) is None
            assert _resolve_uid({"configurable": {"user_id": 12345}}) is None

    def test_traverse_missing_uid_returns_error(self):
        """Returns clean error string when user ID is missing."""
        res = traverse_knowledge_graph_tool.func(entity="Project X", config=None)
        assert res == "Error: User ID not found in configuration"

    def test_traverse_invalid_entity_guards(self):
        """Guards against None, empty, whitespace, or non-string entity."""
        cfg = {"configurable": {"user_id": "usr_valid"}}

        res_none = traverse_knowledge_graph_tool.func(entity=None, config=cfg)
        assert res_none == "Error: entity must be a non-empty string."

        res_empty = traverse_knowledge_graph_tool.func(entity="", config=cfg)
        assert res_empty == "Error: entity must be a non-empty string."

        res_ws = traverse_knowledge_graph_tool.func(entity="   ", config=cfg)
        assert res_ws == "Error: entity must be a non-empty string."

        res_type = traverse_knowledge_graph_tool.func(entity=123, config=cfg)
        assert res_type == "Error: entity must be a non-empty string."

    def test_traverse_hops_coercion_and_clamping(self):
        """Coerces string hops and clamps hops to [1, 2]."""
        cfg = {"configurable": {"user_id": "usr_valid"}}

        with patch.object(gt_module, "traverse_knowledge_graph", return_value={"nodes": []}) as mock_traverse, \
             patch.object(gt_module, "format_traversal_result", return_value="Formatted Graph"):

            # Hops above 2 clamped to 2
            traverse_knowledge_graph_tool.func(entity="Project Alpha", hops=5, config=cfg)
            mock_traverse.assert_called_with("usr_valid", "Project Alpha", hops=2)

            # String hops "2" coerced to 2
            traverse_knowledge_graph_tool.func(entity="Project Alpha", hops="2", config=cfg)
            mock_traverse.assert_called_with("usr_valid", "Project Alpha", hops=2)

            # Hops below 1 clamped to 1
            traverse_knowledge_graph_tool.func(entity="Project Alpha", hops=0, config=cfg)
            mock_traverse.assert_called_with("usr_valid", "Project Alpha", hops=1)

            # None hops defaults to 1
            traverse_knowledge_graph_tool.func(entity="Project Alpha", hops=None, config=cfg)
            mock_traverse.assert_called_with("usr_valid", "Project Alpha", hops=1)

            # Invalid string hops defaults to 1
            traverse_knowledge_graph_tool.func(entity="Project Alpha", hops="invalid", config=cfg)
            mock_traverse.assert_called_with("usr_valid", "Project Alpha", hops=1)

    def test_traverse_truncates_oversized_entity(self):
        """Truncates entity longer than 256 characters."""
        cfg = {"configurable": {"user_id": "usr_valid"}}
        long_entity = "A" * 300

        with patch.object(gt_module, "traverse_knowledge_graph", return_value={}) as mock_traverse, \
             patch.object(gt_module, "format_traversal_result", return_value="Result"):

            traverse_knowledge_graph_tool.func(entity=long_entity, config=cfg)
            mock_traverse.assert_called_with("usr_valid", "A" * 256, hops=1)

    def test_traverse_exception_handling(self):
        """Catches traversal exceptions and returns user-friendly error message."""
        cfg = {"configurable": {"user_id": "usr_valid"}}

        with patch.object(gt_module, "traverse_knowledge_graph", side_effect=RuntimeError("DB query timeout")):
            res = traverse_knowledge_graph_tool.func(entity="Project X", config=cfg)
            assert res == "Error traversing knowledge graph: Unable to complete traversal."
