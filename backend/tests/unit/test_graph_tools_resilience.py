import os
from unittest.mock import patch, MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.retrieval.tools.graph_tools import traverse_knowledge_graph_tool, _resolve_uid


def test_resolve_uid_variants():
    # 1. Standard configurable.user_id
    assert _resolve_uid({"configurable": {"user_id": "user_1"}}) == "user_1"

    # 2. Configurable.uid alias
    assert _resolve_uid({"configurable": {"uid": "user_2"}}) == "user_2"

    # 3. Top-level user_id
    assert _resolve_uid({"user_id": "user_3"}) == "user_3"

    # 4. Top-level uid alias
    assert _resolve_uid({"uid": "user_4"}) == "user_4"

    # 5. Non-dict or empty
    assert _resolve_uid(None) is None
    assert _resolve_uid({}) is None
    assert _resolve_uid("string_config") is None
    assert _resolve_uid(12345) is None


def test_traverse_knowledge_graph_tool_empty_or_invalid_entity():
    # Empty string
    res = traverse_knowledge_graph_tool.func("", hops=1, config={"user_id": "u1"})
    assert res == "Error: Entity name must be a non-empty string"

    # Whitespace only
    res = traverse_knowledge_graph_tool.func("   ", hops=1, config={"user_id": "u1"})
    assert res == "Error: Entity name must be a non-empty string"

    # None
    res = traverse_knowledge_graph_tool.func(None, hops=1, config={"user_id": "u1"})
    assert res == "Error: Entity name must be a non-empty string"

    # Non-string object
    res = traverse_knowledge_graph_tool.func({"entity": "bad"}, hops=1, config={"user_id": "u1"})
    assert res == "Error: Entity name must be a non-empty string"


def test_traverse_knowledge_graph_tool_missing_uid():
    res = traverse_knowledge_graph_tool.func("Project Orion", hops=1, config={})
    assert res == "Error: User ID not found in configuration"


@patch("utils.retrieval.tools.graph_tools.traverse_knowledge_graph")
@patch("utils.retrieval.tools.graph_tools.format_traversal_result")
def test_traverse_knowledge_graph_tool_hops_coercion_and_clamping(mock_format, mock_traverse):
    mock_traverse.return_value = {"nodes": [], "edges": []}
    mock_format.return_value = "Formatted graph"

    # String hops "2" coerced to integer 2
    res = traverse_knowledge_graph_tool.func("Project Orion", hops="2", config={"uid": "user_1"})
    assert res == "Formatted graph"
    mock_traverse.assert_called_with("user_1", "Project Orion", hops=2)

    # String hops "invalid" coerced to fallback 1
    mock_traverse.reset_mock()
    res = traverse_knowledge_graph_tool.func("Project Orion", hops="not_a_number", config={"uid": "user_1"})
    assert res == "Formatted graph"
    mock_traverse.assert_called_with("user_1", "Project Orion", hops=1)

    # Large hops clamped to max 2
    mock_traverse.reset_mock()
    res = traverse_knowledge_graph_tool.func("Project Orion", hops=10, config={"uid": "user_1"})
    assert res == "Formatted graph"
    mock_traverse.assert_called_with("user_1", "Project Orion", hops=2)

    # Negative / 0 hops clamped to min 1
    mock_traverse.reset_mock()
    res = traverse_knowledge_graph_tool.func("Project Orion", hops=0, config={"uid": "user_1"})
    assert res == "Formatted graph"
    mock_traverse.assert_called_with("user_1", "Project Orion", hops=1)


@patch("utils.retrieval.tools.graph_tools.traverse_knowledge_graph")
@patch("utils.retrieval.tools.graph_tools.format_traversal_result")
def test_traverse_knowledge_graph_tool_strips_entity_whitespace(mock_format, mock_traverse):
    mock_traverse.return_value = {"nodes": [], "edges": []}
    mock_format.return_value = "Formatted graph"

    res = traverse_knowledge_graph_tool.func("  Project Mars \n\t ", hops=1, config={"user_id": "u1"})
    assert res == "Formatted graph"
    mock_traverse.assert_called_with("u1", "Project Mars", hops=1)


@patch("utils.retrieval.tools.graph_tools.traverse_knowledge_graph")
def test_traverse_knowledge_graph_tool_exception_handling(mock_traverse):
    mock_traverse.side_effect = RuntimeError("Database down")
    res = traverse_knowledge_graph_tool.func("Project Venus", hops=1, config={"user_id": "u1"})
    assert res == "Error traversing knowledge graph: Unable to complete traversal."
