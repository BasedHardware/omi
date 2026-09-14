"""REST retrieval tool services route reads through universal MemoryService."""

from datetime import datetime, timezone
from types import SimpleNamespace

import utils.retrieval.tool_services.memories as memory_services


def test_tools_rest_get_memories_text_uses_universal_service_for_arbitrary_uid(monkeypatch):
    calls = []

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read(self, uid, **kwargs):
            calls.append((uid, kwargs))
            return [SimpleNamespace(created_at=datetime.now(timezone.utc), id="m1", is_locked=False)]

    monkeypatch.setattr(memory_services, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_services.MemoryDB, "get_memories_as_str", lambda memories: "memory-id=m1")

    result = memory_services.get_memories_text(uid="uid-former-cohort", limit=6000, offset=-3)

    assert "memory-id=m1" in result
    assert calls == [("uid-former-cohort", {"limit": 5000, "offset": 0, "now": None})]


def test_tools_rest_get_memories_text_preserves_empty_and_invalid_date_contract(monkeypatch):
    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(memory_services, "MemoryService", _UniversalService)
    assert memory_services.get_memories_text(uid="uid-arbitrary-account") == "No memories found."
    assert memory_services.get_memories_text(uid="uid-arbitrary-account", start_date="bad").startswith("Error: Invalid")


def test_tools_rest_get_memories_text_backfills_after_filtered_first_page(monkeypatch):
    locked = SimpleNamespace(created_at=datetime.now(timezone.utc), id="locked", is_locked=True)
    visible = SimpleNamespace(created_at=datetime.now(timezone.utc), id="visible", is_locked=False)
    calls = []

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read(self, uid, **kwargs):
            calls.append((uid, kwargs))
            return [[locked, locked], [visible], []][len(calls) - 1]

    monkeypatch.setattr(memory_services, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_services.MemoryDB, "get_memories_as_str", lambda memories: memories[0].id)

    assert memory_services.get_memories_text(uid="uid", limit=2) == "User Memories (1 total):\n\nvisible"
    assert calls[:2] == [
        ("uid", {"limit": 2, "offset": 0, "now": None}),
        ("uid", {"limit": 500, "offset": 2, "now": None}),
    ]


def test_tools_rest_search_memories_text_uses_universal_service_and_preserves_format(monkeypatch):
    calls = []
    memory = SimpleNamespace(
        content="coffee preference",
        category=SimpleNamespace(value="interesting"),
        created_at=datetime(2026, 6, 19, tzinfo=timezone.utc),
        is_locked=False,
    )

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def search(self, uid, query, **kwargs):
            calls.append((uid, query, kwargs))
            return [SimpleNamespace(memory=memory, score=0.91)]

    monkeypatch.setattr(memory_services, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_services.notification_db, "get_user_time_zone", lambda _uid: "UTC")

    result = memory_services.search_memories_text(uid="uid-arbitrary-account", query="coffee", limit=100)

    assert "coffee preference" in result
    assert "relevance: 0.91" in result
    assert calls == [("uid-arbitrary-account", "coffee", {"limit": 20})]


def test_tools_rest_search_memories_text_preserves_empty_result(monkeypatch):
    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def search(self, *_args, **_kwargs):
            return []

    monkeypatch.setattr(memory_services, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_services.notification_db, "get_user_time_zone", lambda _uid: "UTC")
    assert (
        memory_services.search_memories_text(uid="uid-arbitrary-account", query="coffee")
        == "No memories found matching 'coffee'."
    )


def test_tools_rest_temporal_list_filters_suppressed_rows_and_sources(monkeypatch):
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    suppressed = SimpleNamespace(
        id="suppressed",
        memory_id="suppressed",
        content="do not use this",
        created_at=now,
        is_locked=False,
        arguments={"memory_use": {"suppressed": True}},
    )
    visible = SimpleNamespace(
        id="visible",
        memory_id="visible",
        content="use this",
        created_at=now,
        is_locked=False,
        arguments={},
    )

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read_page(self, *_args, **_kwargs):
            return SimpleNamespace(memories=[suppressed, visible], next_cursor=None)

    monkeypatch.setattr(memory_services, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_services, "belief_model_enabled", lambda: True)
    monkeypatch.setattr(
        memory_services.MemoryDB, "get_memories_as_str", lambda memories: ",".join(m.id for m in memories)
    )
    sources = []

    result = memory_services.get_memories_text(uid="uid", source_sink=sources)

    assert "suppressed" not in result
    assert "visible" in result
    assert [source["source_id"] for source in sources] == ["visible"]


def test_tools_rest_temporal_list_bounds_empty_continuation_pages(monkeypatch):
    calls = []

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read_page(self, *_args, **_kwargs):
            calls.append(_kwargs)
            return SimpleNamespace(memories=[], next_cursor=f"cursor-{len(calls)}")

    monkeypatch.setattr(memory_services, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_services, "belief_model_enabled", lambda: True)

    result = memory_services.get_memories_text(uid="uid", limit=1)

    assert len(calls) == 10
    assert "bounded scan reached its safety limit" in result


def test_tools_rest_temporal_ranges_use_evidence_date_for_delayed_sources(monkeypatch):
    captured_at = datetime(2026, 7, 10, tzinfo=timezone.utc)
    processed_at = datetime(2026, 9, 14, tzinfo=timezone.utc)
    delayed = SimpleNamespace(
        id='delayed',
        memory_id='delayed',
        content='captured in July, processed in September',
        created_at=processed_at,
        as_of=captured_at,
        is_locked=False,
        arguments={},
    )

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read_page(self, *_args, **_kwargs):
            return SimpleNamespace(memories=[delayed], next_cursor=None)

    monkeypatch.setattr(memory_services, 'MemoryService', _UniversalService)
    monkeypatch.setattr(memory_services, 'belief_model_enabled', lambda: True)
    monkeypatch.setattr(memory_services.MemoryDB, 'get_memories_as_str', lambda memories: memories[0].content)
    sources = []

    result = memory_services.get_memories_text(
        uid='uid',
        view='history',
        start_date='2026-07-01T00:00:00+00:00',
        end_date='2026-07-31T23:59:59+00:00',
        source_sink=sources,
    )

    assert 'captured in July' in result
    assert sources[0]['created_at'].startswith('2026-07-10')
