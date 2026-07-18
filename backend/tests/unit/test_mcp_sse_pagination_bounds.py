"""Regression tests for pagination bounds on MCP SSE tools.

Several paginated ``execute_tool`` handlers read ``limit`` / ``offset`` straight from the
JSON-RPC ``arguments`` and passed them to the data layer without the ``parse_mcp_int`` clamp
the sibling tools (``list_memories``, ``search_memories``, ``get_action_items``) already apply.
Two problems followed:

  1. A negative ``offset`` / ``limit`` reached Firestore ``.offset()`` / ``.limit()``
     (``database/conversations.py``, ``database/x_posts.py``), which raises on a negative
     argument. That exception is not a ``ToolExecutionError``, so it escaped ``execute_tool``
     and surfaced as HTTP 500 -- the same failure ``database/memories.py`` documents and
     clamps against.
  2. A non-integer ``limit`` (e.g. ``"abc"``) raised deep in the query layer instead of a
     clean ``-32602`` invalid-params error.

The fix clamps ``get_conversations``, ``search_conversations``, ``search_x_posts`` and
``get_x_posts`` with ``parse_mcp_int`` (the min guards fix the negative-argument crash; the
generous maxes bound abuse without regressing realistic callers). ``search_action_items`` is
intentionally not changed: its helper ``mcp_action_items.search_action_items`` already clamps.

These call the real ``execute_tool`` with only the data layer stubbed (``conftest`` sets a fake
``OPENAI_API_KEY`` before collection, so the router imports cleanly).
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(scope="module")
def mcp():
    from routers import mcp_sse

    return mcp_sse


def test_get_conversations_negative_offset_is_clamped(mcp):
    """offset=-1 must be clamped to 0 before reaching Firestore .offset() (which raises on negative)."""

    def _firestore_like(uid, limit, offset, **kwargs):
        # Mimic Firestore .offset(): a negative argument raises. See the clamp note in
        # database/memories.py. Before the fix, offset=-1 reached here and this raised out of
        # execute_tool as a 500.
        if offset < 0:
            raise ValueError("offset must be non-negative")
        return []

    with patch.object(mcp.conversations_db, "get_conversations", side_effect=_firestore_like) as fake:
        result = mcp.execute_tool("test-uid", "get_conversations", {"offset": -1})

    assert result == {"conversations": []}
    assert fake.call_args.args[2] == 0  # offset clamped to 0, not -1


def test_get_conversations_non_int_limit_returns_invalid_params(mcp):
    """A non-integer limit must return a clean -32602, not crash in the query layer."""
    with patch.object(mcp.conversations_db, "get_conversations", MagicMock(return_value=[])):
        with pytest.raises(mcp.ToolExecutionError) as exc:
            mcp.execute_tool("test-uid", "get_conversations", {"limit": "abc"})

    assert exc.value.code == -32602


def test_search_conversations_negative_limit_is_clamped(mcp):
    """search_conversations must clamp the vector-search k (limit) to at least 1."""
    captured = {}

    def _query_vectors(query, uid, starts_at=None, ends_at=None, k=None):
        captured["k"] = k
        return []

    with patch.object(mcp.vector_db, "query_vectors", side_effect=_query_vectors):
        result = mcp.execute_tool("test-uid", "search_conversations", {"query": "hi", "limit": -5})

    assert result == {"conversations": []}
    assert captured["k"] == 1  # clamped up to the minimum


def test_search_x_posts_non_int_limit_returns_invalid_params(mcp):
    """search_x_posts must reject a non-integer limit with -32602 rather than crashing."""
    with patch.object(mcp.vector_db, "find_similar_x_posts", MagicMock(return_value=[])):
        with pytest.raises(mcp.ToolExecutionError) as exc:
            mcp.execute_tool("test-uid", "search_x_posts", {"query": "hi", "limit": "abc"})

    assert exc.value.code == -32602


def test_get_x_posts_negative_limit_is_clamped(mcp):
    """get_x_posts must clamp a negative limit before it reaches Firestore .limit(limit * 3)."""
    fake = MagicMock(return_value=[])
    with patch.object(mcp.x_posts_db, "get_x_posts", fake):
        result = mcp.execute_tool("test-uid", "get_x_posts", {"limit": -5})

    assert result == {"posts": []}
    assert fake.call_args.kwargs["limit"] == 1  # clamped up to the minimum


def test_get_goals_non_bool_include_inactive_returns_invalid_params(mcp):
    """A non-boolean include_inactive must return a clean -32602, not crash in parse_mcp_bool.

    Sibling boolean flags (create_action_item.completed, get_memories.include_activity) already
    wrap parse_mcp_bool in ToolExecutionError; get_goals did not, so parse_mcp_bool's ValueError
    escaped execute_tool as HTTP 500.
    """
    with pytest.raises(mcp.ToolExecutionError) as exc:
        mcp.execute_tool("test-uid", "get_goals", {"include_inactive": "maybe"})
    assert exc.value.code == -32602


def test_get_screen_activity_non_bool_summary_returns_invalid_params(mcp):
    """A non-boolean summary must return a clean -32602, not crash in parse_mcp_bool (same gap)."""
    with pytest.raises(mcp.ToolExecutionError) as exc:
        mcp.execute_tool("test-uid", "get_screen_activity", {"summary": "maybe"})
    assert exc.value.code == -32602
