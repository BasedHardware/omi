import pytest
from datetime import datetime, timedelta, timezone

from utils.mcp_memories import (
    collect_filtered_memories,
    filter_and_sort_memories,
    is_activity_memory,
    is_sensitive_memory,
    parse_mcp_bool,
    parse_mcp_int,
)


def test_activity_memory_detection_uses_tags_source_and_obvious_prefixes():
    assert is_activity_memory({"tags": ["focus"]})
    assert is_activity_memory({"source": "screen_activity"})
    assert is_activity_memory({"content": "Focused on writing tests"})
    assert not is_activity_memory({"content": "User prefers concise status updates"})


def test_sensitive_memory_detection_uses_data_protection_level():
    assert is_sensitive_memory({"data_protection_level": "enhanced"})
    assert not is_sensitive_memory({"data_protection_level": "standard"})
    assert not is_sensitive_memory({})


def test_filter_and_sort_memories_defaults_exclude_activity_but_keep_sensitive_for_compatibility():
    recent = datetime.now(timezone.utc)
    memories = [
        {"id": "activity", "content": "Focused on Unknown App", "updated_at": recent},
        {"id": "sensitive", "content": "Durable fact", "data_protection_level": "enhanced", "updated_at": recent},
    ]

    result = filter_and_sort_memories(memories)

    assert [memory["id"] for memory in result] == ["sensitive"]


def test_filter_and_sort_memories_supports_review_manual_updated_and_sort():
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=2)
    memories = [
        {"id": "old", "reviewed": True, "manually_added": True, "updated_at": old, "created_at": old},
        {"id": "new", "reviewed": True, "manually_added": True, "updated_at": now, "created_at": now},
        {"id": "unreviewed", "reviewed": False, "manually_added": True, "updated_at": now, "created_at": now},
    ]

    result = filter_and_sort_memories(
        memories,
        reviewed=True,
        manually_added=True,
        updated_after=old + timedelta(hours=1),
        sort="updated_desc",
    )

    assert [memory["id"] for memory in result] == ["new"]


def test_argument_parsers_handle_agent_string_inputs():
    assert parse_mcp_bool("false", "include_sensitive", default=True) is False
    assert parse_mcp_bool("true", "include_sensitive", default=False) is True
    assert parse_mcp_int("12", "limit", default=1, minimum=1, maximum=500) == 12
    with pytest.raises(ValueError):
        parse_mcp_bool("maybe", "include_sensitive", default=True)
    with pytest.raises(ValueError):
        parse_mcp_int("abc", "limit", default=1, minimum=1, maximum=500)


def test_filter_and_sort_memories_handles_naive_and_aware_timestamps():
    result = filter_and_sort_memories(
        [{"id": "match", "updated_at": "2026-06-06T12:30:00Z"}],
        updated_after=datetime(2026, 6, 6, 12, 0, 0),
    )

    assert [memory["id"] for memory in result] == ["match"]


def test_collect_filtered_memories_continues_batches_until_page_is_full():
    rows = [
        {"id": "activity-1", "content": "Focused on email"},
        {"id": "activity-2", "content": "Viewing browser"},
        {"id": "durable-1", "content": "User prefers concise updates"},
        {"id": "durable-2", "content": "User works on Omi"},
    ]

    def fetch_batch(offset, limit):
        return rows[offset : offset + limit]

    result = collect_filtered_memories(fetch_batch, limit=2, offset=0)

    assert [memory["id"] for memory in result["memories"]] == ["durable-1", "durable-2"]
    assert result["has_more"] is False


def test_collect_filtered_memories_global_sorts_created_desc_across_batches():
    now = datetime.now(timezone.utc)
    rows = [
        {"id": "older-high-score", "created_at": now - timedelta(days=3)},
        {"id": "oldest-high-score", "created_at": now - timedelta(days=5)},
        {"id": "newest-low-score", "created_at": now},
    ]

    def fetch_batch(offset, limit):
        return rows[offset : offset + limit]

    result = collect_filtered_memories(fetch_batch, limit=1, offset=0, sort="created_desc")

    assert [memory["id"] for memory in result["memories"]] == ["newest-low-score"]
    assert result["has_more"] is True
