"""Unit tests for chat retrieval hard-scope (#4515)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

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
    }
    with (
        patch.object(tools.conversations_db, "get_conversation", return_value=conv) as get_one,
        patch.object(tools.conversations_db, "get_conversations") as get_many,
        patch.object(tools, "deserialize_conversation", side_effect=lambda d: MagicMock(
            model_dump=lambda: dict(d),
            transcript_segments=[],
        )),
        patch.object(tools, "conversations_to_string", return_value="SCOPED_ONLY"),
        patch.object(tools.notification_db, "get_user_time_zone", return_value="UTC"),
    ):
        out = tools.get_conversations_tool.invoke({}, config=cfg)
    assert "SCOPED_ONLY" in out
    get_one.assert_called_once_with("u1", "only-me")
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
