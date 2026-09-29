"""Unit tests verifying exception sanitization in knowledge graph and web retrieval tools.

Failure-Class: none
Ensures internal traversal errors and raw exceptions are sanitized and never leaked to callers.
"""

import asyncio
from unittest.mock import patch
from utils.retrieval.tools import graph_tools, web_tools

SENTINEL_ERROR = "SENTINEL_INTERNAL_LEAK_PG_CONN_127_0_0_1_PWD_SECRET"


def test_traverse_knowledge_graph_tool_exception_sanitized():
    with patch(
        "utils.retrieval.tools.graph_tools.traverse_knowledge_graph",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = graph_tools.traverse_knowledge_graph_tool.func(
            entity="test-entity",
            config={"configurable": {"user_id": "test-uid-123"}},
        )
    assert SENTINEL_ERROR not in res
    assert res == "Error traversing knowledge graph. Please try again later."


def test_fetch_url_tool_exception_sanitized():
    with patch(
        "utils.retrieval.tools.web_tools._fetch_page",
        side_effect=RuntimeError(SENTINEL_ERROR),
    ):
        res = asyncio.run(web_tools.fetch_url_tool.coroutine(url="https://example.com/page"))
    assert SENTINEL_ERROR not in res
    assert res == "Error: Failed to fetch the URL. Please try again later."
