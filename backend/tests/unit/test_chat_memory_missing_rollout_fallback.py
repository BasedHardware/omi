"""Chat retrieval tools use universal MemoryService for every account."""

from types import SimpleNamespace

import utils.retrieval.tool_services.memories as memory_service_tools
import utils.retrieval.tools.memory_tools as memory_tools


class _Memory:
    created_at = None
    content = "Universal memory"
    category = SimpleNamespace(value="interesting")
    id = "m1"
    is_locked = False


def test_get_memories_tool_reads_arbitrary_uid_through_universal_service(monkeypatch):
    calls = []

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read(self, uid, **kwargs):
            calls.append((uid, kwargs))
            return [_Memory()]

    monkeypatch.setattr(memory_tools, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_tools.MemoryDB, "get_memories_as_str", lambda memories: "Universal memory")

    result = memory_tools.get_memories_tool.invoke(
        {"limit": 10, "offset": 0}, config={"configurable": {"user_id": "uid-former-cohort"}}
    )

    assert "Universal memory" in result
    assert calls == [("uid-former-cohort", {"limit": 10, "offset": 0})]


def test_search_memories_tool_reads_arbitrary_uid_through_universal_service(monkeypatch):
    calls = []
    match = SimpleNamespace(memory=_Memory(), score=0.91)

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def search(self, uid, query, **kwargs):
            calls.append((uid, query, kwargs))
            return [match]

    monkeypatch.setattr(memory_tools, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_tools.notification_db, "get_user_time_zone", lambda _uid: "UTC")

    result = memory_tools.search_memories_tool.invoke(
        {"query": "coffee"}, config={"configurable": {"user_id": "uid-arbitrary-account"}}
    )

    assert "Universal memory" in result
    assert calls == [("uid-arbitrary-account", "coffee", {"limit": 5})]


def test_rest_tool_service_reads_arbitrary_uid_through_universal_service(monkeypatch):
    calls = []

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read(self, uid, **kwargs):
            calls.append((uid, kwargs))
            return [_Memory()]

    monkeypatch.setattr(memory_service_tools, "MemoryService", _UniversalService)
    monkeypatch.setattr(memory_service_tools.MemoryDB, "get_memories_as_str", lambda memories: "Universal memory")

    result = memory_service_tools.get_memories_text(uid="uid-arbitrary-account", limit=10, offset=0)

    assert "Universal memory" in result
    assert calls == [("uid-arbitrary-account", {"limit": 10, "offset": 0, "now": None})]


def test_retrieval_surfaces_contain_no_cohort_or_legacy_selector():
    for module in (memory_tools, memory_service_tools):
        source = open(module.__file__, encoding="utf-8").read()
        assert "pin_memory_system" not in source
        assert "resolve_memory_system" not in source
        assert "database.memories" not in source
