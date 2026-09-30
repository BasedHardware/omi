import os
from unittest.mock import patch

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from utils.retrieval.tools.graph_tools import traverse_knowledge_graph_tool


def test_traverse_knowledge_graph_tool_exception_sanitized(caplog):
    sensitive_info = "postgres://superadmin:supersecret@10.0.0.5:5432/production_db"
    exception_message = f"Connection failed to {sensitive_info}"

    with patch(
        "utils.retrieval.tools.graph_tools.traverse_knowledge_graph",
        side_effect=RuntimeError(exception_message),
    ):
        result = traverse_knowledge_graph_tool.invoke(
            {"entity": "Project Orion", "hops": 1},
            config={"configurable": {"user_id": "test_user_42"}},
        )

        assert result == "Error traversing knowledge graph: Unable to complete traversal."
        assert sensitive_info not in result
        assert "supersecret" not in result
        assert "Connection failed" not in result


def test_traverse_knowledge_graph_tool_direct_func_exception_sanitized():
    sensitive_path = "/var/secrets/tokens/admin_token.key"
    exception_message = f"Permission denied accessing {sensitive_path}"

    with patch(
        "utils.retrieval.tools.graph_tools.traverse_knowledge_graph",
        side_effect=IOError(exception_message),
    ):
        result = traverse_knowledge_graph_tool.func(
            entity="Confidential Concept",
            hops=2,
            config={"configurable": {"user_id": "test_user_99"}},
        )

        assert result == "Error traversing knowledge graph: Unable to complete traversal."
        assert sensitive_path not in result
        assert "Permission denied" not in result


def test_traverse_knowledge_graph_tool_missing_uid():
    result = traverse_knowledge_graph_tool.invoke(
        {"entity": "Unknown", "hops": 1},
        config={},
    )
    assert result == "Error: User ID not found in configuration"
