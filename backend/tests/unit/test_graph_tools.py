import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.retrieval.tools.graph_tools import _resolve_uid, traverse_knowledge_graph_tool


def test_resolve_uid_nested():
    cfg = {"configurable": {"user_id": "nested_user_123"}}
    assert _resolve_uid(cfg) == "nested_user_123"


def test_resolve_uid_top_level():
    cfg = {"user_id": "top_level_user_456"}
    assert _resolve_uid(cfg) == "top_level_user_456"


def test_resolve_uid_none_configurable_with_fallback():
    cfg = {"configurable": None, "user_id": "fallback_user_789"}
    assert _resolve_uid(cfg) == "fallback_user_789"


def test_resolve_uid_missing():
    assert _resolve_uid(None) is None
    assert _resolve_uid({}) is None
    assert _resolve_uid({"configurable": {}}) is None


def test_entity_validation_empty_or_none():
    cfg = {"configurable": {"user_id": "test_user"}}
    assert (
        traverse_knowledge_graph_tool.invoke({"entity": None, "hops": 1}, config=cfg)
        == "Error: Entity name must not be empty"
    )
    assert (
        traverse_knowledge_graph_tool.invoke({"entity": "", "hops": 1}, config=cfg)
        == "Error: Entity name must not be empty"
    )
    assert (
        traverse_knowledge_graph_tool.invoke({"entity": "   ", "hops": 1}, config=cfg)
        == "Error: Entity name must not be empty"
    )


def test_hops_coercion_string_input():
    cfg = {"configurable": {"user_id": "test_user"}}
    with patch(
        "utils.retrieval.tools.graph_tools.traverse_knowledge_graph",
        return_value={"nodes": ["A", "B"]},
    ) as mock_traverse, patch(
        "utils.retrieval.tools.graph_tools.format_traversal_result",
        return_value="Connected Subgraph: A -> B",
    ):
        res = traverse_knowledge_graph_tool.invoke(
            {"entity": "Apple", "hops": "2"}, config=cfg
        )
        assert "Connected Subgraph" in res
        mock_traverse.assert_called_once_with("test_user", "Apple", hops=2)


def test_hops_clamping_bounds():
    cfg = {"configurable": {"user_id": "test_user"}}
    with patch(
        "utils.retrieval.tools.graph_tools.traverse_knowledge_graph",
        return_value={"nodes": []},
    ) as mock_traverse, patch(
        "utils.retrieval.tools.graph_tools.format_traversal_result",
        return_value="Connected Subgraph",
    ):
        # hops > 2 clamped to 2
        traverse_knowledge_graph_tool.invoke(
            {"entity": "ProjectX", "hops": 5}, config=cfg
        )
        mock_traverse.assert_called_with("test_user", "ProjectX", hops=2)

        # hops < 1 clamped to 1
        traverse_knowledge_graph_tool.invoke(
            {"entity": "ProjectX", "hops": -3}, config=cfg
        )
        mock_traverse.assert_called_with("test_user", "ProjectX", hops=1)


def test_direct_func_invocation():
    cfg = {"configurable": {"user_id": "test_user"}}
    with patch(
        "utils.retrieval.tools.graph_tools.traverse_knowledge_graph",
        return_value={"nodes": ["X"]},
    ) as mock_traverse, patch(
        "utils.retrieval.tools.graph_tools.format_traversal_result",
        return_value="Connected Subgraph: X",
    ):
        res = traverse_knowledge_graph_tool.func(
            entity="Concept", hops=1, config=cfg
        )
        assert "Connected Subgraph: X" in res
        mock_traverse.assert_called_with("test_user", "Concept", hops=1)
