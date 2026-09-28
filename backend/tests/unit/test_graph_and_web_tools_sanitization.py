"""Unit tests verifying exception sanitization in knowledge graph and web retrieval tools.

Failure-Class: none
Ensures internal traversal errors and raw exceptions are sanitized and never leaked to callers.
"""

from unittest.mock import patch
from utils.retrieval.tools import graph_tools, web_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_traverse_knowledge_graph_tool_exception_sanitized():
    with patch(
        "utils.retrieval.tools.graph_tools.graph_db.get_node_edges",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = graph_tools.traverse_knowledge_graph_tool(
            node_id="node-123", config={"configurable": {"user_id": "test-uid-123"}}
        )
    assert SENTINEL_ERROR not in res
    assert "Error traversing knowledge graph: Failed to traverse knowledge graph." in res


def test_fetch_url_tool_exception_sanitized():
    with patch("utils.retrieval.tools.web_tools.httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = RuntimeError(SENTINEL_ERROR)
        res = web_tools.fetch_url_tool(url="https://example.com/page")
    assert SENTINEL_ERROR not in res
    assert "Error: Failed to fetch the URL." in res
