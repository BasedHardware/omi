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
