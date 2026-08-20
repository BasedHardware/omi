"""MCP memory surfaces use the universal MemoryService while keeping auth wire contracts."""

from pathlib import Path
from types import SimpleNamespace

import utils.memory.memory_service as service_mod
from utils.memory.default_read_rollout import MemoryReadDecision
from utils.mcp_memories import (
    McpMemoryListResult,
    McpMemorySearchResult,
    list_default_mcp_memories,
    mcp_legacy_read_authorized,
    search_default_mcp_memories,
    search_default_mcp_memories_vector,
)

BACKEND = Path(__file__).resolve().parents[2]


def test_mcp_legacy_read_is_never_authorized_after_universal_cutover():
    assert (
        mcp_legacy_read_authorized(McpMemorySearchResult(memories=[], read_decision=MemoryReadDecision.DENY_MEMORY))
        is False
    )
    assert (
        mcp_legacy_read_authorized(McpMemoryListResult(memories=[], read_decision=MemoryReadDecision.DENY_MEMORY))
        is False
    )


class _Memory:
    def __init__(self, memory_id: str, *, category: str = "manual", reviewed: bool = False):
        self.memory_id = memory_id
        self.category = category
        self.reviewed = reviewed

    def model_dump(self, mode="json"):
        return {
            "id": self.memory_id,
            "content": f"content-{self.memory_id}",
            "category": self.category,
            "reviewed": self.reviewed,
            "manually_added": True,
        }


def test_mcp_compatibility_list_adapter_delegates_arbitrary_uid_to_universal_service(monkeypatch):
    calls = []

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def read(self, uid, **kwargs):
            calls.append((uid, kwargs))
            return [_Memory("m1"), _Memory("m2", category="personal")]

    monkeypatch.setattr(service_mod, "MemoryService", _UniversalService)
    result = list_default_mcp_memories(
        uid="uid-former-cohort",
        limit=10,
        offset=0,
        db_client=SimpleNamespace(),
        categories=["manual"],
    )

    assert result.read_decision == MemoryReadDecision.USE_MEMORY
    assert [item["id"] for item in result.memories] == ["m1"]
    assert calls == [("uid-former-cohort", {"limit": 500, "offset": 0})]


def test_mcp_search_and_vector_adapters_delegate_to_universal_service(monkeypatch):
    calls = []

    class _UniversalService:
        def __init__(self, **_kwargs):
            pass

        def search_mcp(self, uid, query, **kwargs):
            calls.append((uid, query, kwargs))
            return [{"id": "m1", "content": "coffee", "relevance_score": 0.9}]

    monkeypatch.setattr(service_mod, "MemoryService", _UniversalService)
    search = search_default_mcp_memories(
        uid="uid-arbitrary-account", query="coffee", limit=50, db_client=SimpleNamespace(), rollout_capabilities=None
    )
    vector = search_default_mcp_memories_vector(
        uid="uid-arbitrary-account", query="coffee", limit=50, db_client=SimpleNamespace()
    )

    assert search == [{"id": "m1", "content": "coffee", "relevance_score": 0.9}]
    assert vector.read_decision == MemoryReadDecision.USE_MEMORY
    assert vector.memories == search
    assert calls == [
        ("uid-arbitrary-account", "coffee", {"limit": 20}),
        ("uid-arbitrary-account", "coffee", {"limit": 20}),
    ]


def test_mcp_rest_routes_keep_scope_grants_and_use_universal_service():
    source = (BACKEND / "routers/mcp.py").read_text(encoding="utf-8")
    search_route = source[
        source.index('@router.get("/v1/mcp/memories/search"') : source.index('@router.get("/v1/mcp/memories"')
    ]
    list_route = source[source.index('@router.get("/v1/mcp/memories"') : source.index("class SimpleStructured")]

    assert "get_mcp_memory_default_memory_read_context" in search_route
    assert "authorize_memory_external_default_memory_read(auth_context, db_client=db)" in search_route
    assert "memory_service = MemoryService(db_client=db)" in search_route
    assert "memory_service.search_mcp(uid, query, limit=limit)" in search_route
    assert "read_default_read_rollout" not in search_route
    assert "search_default_mcp_memories_vector" not in search_route
    assert "memories_db" not in search_route
    assert "MemoryService(db_client=db).read" in list_route
    assert "collect_filtered_memories" in list_route
    assert "read_default_read_rollout" not in list_route
    assert "memories_db" not in list_route


def test_mcp_sse_memory_tools_keep_scope_grants_and_use_universal_service():
    source = (BACKEND / "routers/mcp_sse.py").read_text(encoding="utf-8")
    get_tool = source[
        source.index('elif tool_name == "get_memories":') : source.index('elif tool_name == "create_memory":')
    ]
    search_tool = source[
        source.index('elif tool_name == "search_memories":') : source.index('elif tool_name == "search_conversations":')
    ]

    assert "auth_context is None" in get_tool
    assert "authorize_memory_external_default_memory_read(auth_context, db_client=db)" in get_tool
    assert "MemoryService(db_client=db).read" in get_tool
    assert "collect_filtered_memories" in get_tool
    assert "read_default_read_rollout" not in get_tool
    assert "memories_db" not in get_tool
    assert "authorize_memory_external_default_memory_read(auth_context, db_client=db)" in search_tool
    assert "MemoryService(db_client=db).search_mcp" in search_tool
    assert "read_default_read_rollout" not in search_tool
    assert "vector_db.find_similar_memories" not in search_tool


def test_mcp_rest_memory_list_uses_single_authorization_context():
    source = (BACKEND / "routers/mcp.py").read_text(encoding="utf-8")
    profile_route = source[source.index('@router.get("/v1/mcp/profile"') : source.index("class CleanerMemory")]
    list_route = source[source.index('@router.get("/v1/mcp/memories"') : source.index("class SimpleStructured")]
    assert 'uid: str = Depends(get_uid_from_mcp_api_key)' in profile_route
    assert 'uid: str = Depends(get_uid_from_mcp_api_key)' not in list_route
    assert (
        "auth_context: ProductAuthorizationContext = Depends(get_mcp_memory_default_memory_read_context)" in list_route
    )
    assert "uid = auth_context.uid" in list_route


def test_mcp_sse_transport_authenticates_full_api_key_context_without_inferred_scopes():
    source = (BACKEND / "routers/mcp_sse.py").read_text(encoding="utf-8")
    assert "def authenticate_api_key_auth_context(authorization: Optional[str])" in source
    assert "def authenticate_mcp_request(authorization: Optional[str])" in source
    assert "mcp_api_key_db.get_api_key_auth_result(token)" in source
    assert 'record_api_key_repairs(key_kind="mcp", operation="auth"' in source
    assert "scopes=tuple(user_data.get(\"scopes\") or ())" in source
    assert "memory_context=_mcp_memory_context_from_auth_data(user_data)" in source
    assert "auth_context = await run_blocking(db_executor, authenticate_mcp_request, authorization)" in source
    assert "user_id = auth_context.uid" in source
