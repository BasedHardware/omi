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


@pytest.fixture(scope="module")
def conversations_db():
    # Patch the handler's own module binding: test_mcp_search_date_utc's
    # sys.modules stub isolation can leave the router and the handler holding
    # different `database` objects in a combined run.
    from utils.mcp_server.handlers import conversations as mcp_conversations

    return mcp_conversations.mcp_conversation_pages


def test_get_conversations_negative_offset_is_clamped(mcp, conversations_db):
    """offset=-1 must be clamped to 0 before it can reach Firestore (which raises on negative)."""
    page = MagicMock(return_value=([], None))
    legacy = MagicMock(return_value=[])
    with (
        patch.object(conversations_db, "get_mcp_conversation_cards_page", page),
        patch.object(conversations_db, "get_mcp_conversation_cards", legacy),
    ):
        result = mcp.execute_tool("test-uid", "get_conversations", {"offset": -1})

    assert result == {"conversations": []}
    page.assert_called_once()
    assert page.call_args.kwargs["after"] is None
    legacy.assert_not_called()


def test_get_conversations_non_int_limit_returns_invalid_params(mcp, conversations_db):
    """A non-integer limit must return a clean -32602, not crash in the query layer."""
    with patch.object(conversations_db, "get_mcp_conversation_cards_page", MagicMock(return_value=([], None))):
        with pytest.raises(mcp.ToolExecutionError) as exc:
            mcp.execute_tool("test-uid", "get_conversations", {"limit": "abc"})

    assert exc.value.code == -32602


def test_get_conversations_oversized_limit_is_clamped_to_card_budget(mcp, conversations_db):
    with patch.object(conversations_db, "get_mcp_conversation_cards_page", MagicMock(return_value=([], None))) as fake:
        result = mcp.execute_tool("test-uid", "get_conversations", {"limit": 10_000})

    assert result == {"conversations": []}
    assert fake.call_args.args[1] == 100


def test_get_conversations_explicit_offset_uses_legacy_offset_path(mcp, conversations_db):
    """An explicit non-zero offset keeps the original raw-offset list semantics."""
    legacy = MagicMock(return_value=[])
    page = MagicMock(return_value=([], None))
    with (
        patch.object(conversations_db, "get_mcp_conversation_cards", legacy),
        patch.object(conversations_db, "get_mcp_conversation_cards_page", page),
    ):
        result = mcp.execute_tool("test-uid", "get_conversations", {"offset": 40, "limit": 10})

    assert result == {"conversations": []}
    legacy.assert_called_once()
    assert legacy.call_args.args[1] == 10
    assert legacy.call_args.args[2] == 40
    page.assert_not_called()


def test_search_conversations_negative_limit_is_clamped(mcp):
    """search_conversations must clamp the vector-search k (limit) to at least 1."""
    captured = {}

    def _resolve(uid, query, *, limit, starts_at=None, ends_at=None, **kwargs):
        captured["limit"] = limit
        return []

    from utils.mcp_server.handlers import conversations as mcp_conversations

    with patch.object(mcp_conversations, "resolve_mcp_conversation_search_ids", side_effect=_resolve):
        result = mcp.execute_tool("test-uid", "search_conversations", {"query": "hi", "limit": -5})

    assert result == {"conversations": []}
    assert captured["limit"] == 1  # clamped up to the minimum


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
