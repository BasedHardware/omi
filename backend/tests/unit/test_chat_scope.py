"""Unit tests for chat retrieval hard-scope (#4515)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from models.chat import PageContext
from utils.retrieval.chat_scope import apply_chat_scope_dates, build_chat_scope
from utils.retrieval.tools import conversation_tools as tools


def test_build_chat_scope_none_without_hard_fields():
    assert build_chat_scope(None) is None
    assert build_chat_scope(PageContext(type="task", id="t1", title="Task")) is None
    assert build_chat_scope(PageContext(type="conversation", title="No id")) is None


def test_build_chat_scope_conversation_and_dates():
    ctx = PageContext(
        type="conversation",
        id="conv-1",
        title="Standup",
        start_date="2026-08-01T00:00:00-07:00",
        end_date="2026-08-01T23:59:59-07:00",
    )
    assert build_chat_scope(ctx) == {
        "conversation_id": "conv-1",
        "start_date": "2026-08-01T00:00:00-07:00",
        "end_date": "2026-08-01T23:59:59-07:00",
    }


def test_page_context_rejects_naive_and_invalid_dates():
    with pytest.raises(ValidationError):
        PageContext(type="recap", title="Today", start_date="2026-08-01T00:00:00")
    with pytest.raises(ValidationError):
        PageContext(type="recap", title="Today", end_date="not-a-date")


def test_apply_chat_scope_dates_intersects():
    scope = {
        "start_date": "2026-08-01T00:00:00+00:00",
        "end_date": "2026-08-07T23:59:59+00:00",
    }
    start, end, err = apply_chat_scope_dates(
        scope,
        "2026-08-03T00:00:00+00:00",
        "2026-08-10T00:00:00+00:00",
    )
    assert err is None
    assert start == "2026-08-03T00:00:00+00:00"
    assert end == "2026-08-07T23:59:59+00:00"


def test_apply_chat_scope_dates_empty_intersection_errors():
    scope = {
        "start_date": "2026-08-01T00:00:00+00:00",
        "end_date": "2026-08-02T00:00:00+00:00",
    }
    start, end, err = apply_chat_scope_dates(
        scope,
        "2026-08-05T00:00:00+00:00",
        "2026-08-06T00:00:00+00:00",
    )
    assert start is None and end is None
    assert err is not None
    assert "outside" in err.lower()


def test_get_conversations_tool_honors_conversation_scope():
    cfg = {
        "configurable": {
            "user_id": "u1",
            "conversations_collected": [],
            "chat_scope": {"conversation_id": "only-me"},
        }
    }
    conv = {
        "id": "only-me",
        "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
        "started_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 8, 1, 1, tzinfo=timezone.utc),
        "structured": {"title": "Scoped", "overview": "hi", "emoji": "🙂", "category": "other"},
        "transcript_segments": [],
        "discarded": False,
        "is_locked": False,
        "status": "completed",
    }
    with (
        patch.object(tools.conversations_db, "get_conversations_by_id", return_value=[conv]) as get_one,
        patch.object(tools.conversations_db, "get_conversations") as get_many,
        patch.object(
            tools,
            "deserialize_conversation",
            side_effect=lambda d: MagicMock(
                model_dump=lambda: dict(d),
                transcript_segments=[],
            ),
        ),
        patch.object(tools, "conversations_to_string", return_value="SCOPED_ONLY"),
        patch.object(tools.notification_db, "get_user_time_zone", return_value="UTC"),
    ):
        out = tools.get_conversations_tool.invoke({}, config=cfg)
    assert "SCOPED_ONLY" in out
    get_one.assert_called_once_with("u1", ["only-me"], include_discarded=True)
    get_many.assert_not_called()


def test_get_conversations_tool_hides_discarded_under_scope():
    cfg = {
        "configurable": {
            "user_id": "u1",
            "conversations_collected": [],
            "chat_scope": {"conversation_id": "gone"},
        }
    }
    conv = {
        "id": "gone",
        "discarded": True,
        "is_locked": False,
        "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }
    with (
        patch.object(tools.conversations_db, "get_conversations_by_id", return_value=[conv]),
        patch.object(tools.conversations_db, "get_conversations") as get_many,
    ):
        out = tools.get_conversations_tool.invoke({}, config=cfg)
    assert "no accessible conversation" in out.lower()
    get_many.assert_not_called()


def test_get_conversations_tool_fail_closed_on_timeframe_scope():
    cfg = {
        "configurable": {
            "user_id": "u1",
            "conversations_collected": [],
            "chat_scope": {
                "conversation_id": "only-me",
                "start_date": "2026-08-01T00:00:00+00:00",
                "end_date": "2026-08-01T23:59:59+00:00",
            },
        }
    }
    conv = {
        "id": "only-me",
        "created_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "started_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 7, 1, 1, tzinfo=timezone.utc),
        "structured": {"title": "Old", "overview": "hi", "emoji": "🙂", "category": "other"},
        "transcript_segments": [],
        "discarded": False,
        "is_locked": False,
        "status": "completed",
    }
    with (
        patch.object(tools.conversations_db, "get_conversations_by_id", return_value=[conv]),
        patch.object(tools, "conversation_matches_date_range", return_value=False),
        patch.object(tools.conversations_db, "get_conversations") as get_many,
        patch.object(tools.notification_db, "get_user_time_zone", return_value="UTC"),
    ):
        out = tools.get_conversations_tool.invoke({}, config=cfg)
    assert "outside the active chat timeframe" in out.lower()
    get_many.assert_not_called()


def test_search_conversations_tool_rejects_other_exact_reference_under_scope():
    cfg = {
        "configurable": {
            "user_id": "u1",
            "conversations_collected": [],
            "chat_scope": {"conversation_id": "only-me"},
        }
    }
    with patch.object(tools, "parse_exact_conversation_reference", return_value="other-id"):
        out = tools.search_conversations_tool.invoke(
            {"query": "https://h.omi.me/c/other-id"},
            config=cfg,
        )
    assert "scoped to conversation only-me" in out.lower()


def test_search_conversations_tool_refilters_hydrated_hits_to_timeframe():
    """Stale index IDs must not leak conversations outside the hard chat window."""
    cfg = {
        "configurable": {
            "user_id": "u1",
            "conversations_collected": [],
            "chat_scope": {
                "start_date": "2026-08-09T00:00:00+00:00",
                "end_date": "2026-08-09T23:59:59+00:00",
            },
        }
    }
    stale = {
        "id": "stale",
        "created_at": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "is_locked": False,
        "discarded": False,
        "structured": {"title": "Old", "overview": "hi", "emoji": "🙂", "category": "other"},
        "transcript_segments": [],
    }
    with (
        patch.object(tools, "parse_exact_conversation_reference", return_value=None),
        patch.object(tools, "keyword_search_conversation_ids", return_value=["stale"]),
        patch.object(tools.vector_db, "query_vectors", return_value=[]),
        patch.object(tools.conversations_db, "get_conversations_by_id", return_value=[stale]),
        patch.object(tools, "conversations_to_string") as render,
        patch.object(tools.notification_db, "get_user_time_zone", return_value="UTC"),
    ):
        out = tools.search_conversations_tool.invoke({"query": "standup"}, config=cfg)
    assert "no conversations found" in out.lower()
    render.assert_not_called()


def test_get_action_items_tool_forces_conversation_scope():
    import utils.retrieval.tools.action_item_tools as action_tools

    cfg = {
        "configurable": {
            "user_id": "u1",
            "chat_scope": {"conversation_id": "only-me"},
        }
    }
    with patch.object(action_tools.action_items_db, "get_action_items", return_value=[]) as get_items:
        out = action_tools.get_action_items_tool.invoke({}, config=cfg)
    assert get_items.call_args.kwargs.get("conversation_id") == "only-me"
    assert "no action items found" in out.lower()


def test_get_action_items_tool_rejects_foreign_conversation_under_scope():
    import utils.retrieval.tools.action_item_tools as action_tools

    cfg = {
        "configurable": {
            "user_id": "u1",
            "chat_scope": {"conversation_id": "only-me"},
        }
    }
    with patch.object(action_tools.action_items_db, "get_action_items") as get_items:
        out = action_tools.get_action_items_tool.invoke({"conversation_id": "other"}, config=cfg)
    assert "scoped to conversation only-me" in out.lower()
    get_items.assert_not_called()


def test_search_memories_tool_filters_matches_to_timeframe_scope():
    import utils.retrieval.tools.memory_tools as memory_tools
    from models.memories import MemoryCategory

    cfg = {
        "configurable": {
            "user_id": "u1",
            "chat_scope": {
                "start_date": "2026-08-09T00:00:00+00:00",
                "end_date": "2026-08-09T23:59:59+00:00",
            },
        }
    }

    in_scope = MagicMock()
    in_scope.memory.is_locked = False
    in_scope.memory.created_at = datetime(2026, 8, 9, 12, tzinfo=timezone.utc)
    in_scope.memory.content = "IN_SCOPE_FACT"
    in_scope.memory.category = MemoryCategory.interesting
    in_scope.score = 0.9

    leaked = MagicMock()
    leaked.memory.is_locked = False
    leaked.memory.created_at = datetime(2026, 7, 1, tzinfo=timezone.utc)
    leaked.memory.content = "LEAKED"
    leaked.memory.category = MemoryCategory.interesting
    leaked.score = 0.95

    service = MagicMock()
    service.search.return_value = [leaked, in_scope]
    with (
        patch.object(memory_tools, "MemoryService", return_value=service),
        patch.object(memory_tools.notification_db, "get_user_time_zone", return_value="UTC"),
    ):
        out = memory_tools.search_memories_tool.invoke({"query": "dogs"}, config=cfg)
    assert "IN_SCOPE_FACT" in out
    assert "LEAKED" not in out


def test_search_memories_tool_excludes_untimed_matches_under_timeframe_scope():
    import utils.retrieval.tools.memory_tools as memory_tools
    from models.memories import MemoryCategory

    cfg = {
        "configurable": {
            "user_id": "u1",
            "chat_scope": {
                "start_date": "2026-08-09T00:00:00+00:00",
                "end_date": "2026-08-09T23:59:59+00:00",
            },
        }
    }

    untimed = MagicMock()
    untimed.memory.is_locked = False
    untimed.memory.created_at = None
    untimed.memory.content = "UNTIMED"
    untimed.memory.category = MemoryCategory.interesting
    untimed.score = 0.99

    service = MagicMock()
    service.search.return_value = [untimed]
    with (
        patch.object(memory_tools, "MemoryService", return_value=service),
        patch.object(memory_tools.notification_db, "get_user_time_zone", return_value="UTC"),
    ):
        out = memory_tools.search_memories_tool.invoke({"query": "dogs"}, config=cfg)
    assert "UNTIMED" not in out
    assert "no memories found" in out.lower()


def test_get_conversations_tool_rejects_missing_status_under_scope():
    cfg = {
        "configurable": {
            "user_id": "u1",
            "conversations_collected": [],
            "chat_scope": {"conversation_id": "only-me"},
        }
    }
    conv = {
        "id": "only-me",
        "discarded": False,
        "is_locked": False,
        "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
    }
    with (
        patch.object(tools.conversations_db, "get_conversations_by_id", return_value=[conv]),
        patch.object(tools.conversations_db, "get_conversations") as get_many,
    ):
        out = tools.get_conversations_tool.invoke({"statuses": "completed"}, config=cfg)
    assert "no accessible conversation" in out.lower()
    get_many.assert_not_called()


def test_get_conversations_tool_scoped_offset_does_not_repeat_the_conversation():
    cfg = {
        "configurable": {
            "user_id": "u1",
            "conversations_collected": [],
            "chat_scope": {"conversation_id": "only-me"},
        }
    }
    conv = {
        "id": "only-me",
        "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
        "started_at": datetime(2026, 8, 1, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 8, 1, 1, tzinfo=timezone.utc),
        "structured": {"title": "Scoped", "overview": "hi", "emoji": "🙂", "category": "other"},
        "transcript_segments": [],
        "discarded": False,
        "is_locked": False,
        "status": "completed",
    }
    with (
        patch.object(tools.conversations_db, "get_conversations_by_id", return_value=[conv]),
        patch.object(tools.conversations_db, "get_conversations") as get_many,
        patch.object(tools.notification_db, "get_user_time_zone", return_value="UTC"),
    ):
        out = tools.get_conversations_tool.invoke({"offset": 1}, config=cfg)
    assert out.startswith("No conversations found")
    get_many.assert_not_called()
