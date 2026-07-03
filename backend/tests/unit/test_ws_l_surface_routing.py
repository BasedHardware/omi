"""WS-L surface routing: cohort pinning, shared canonical filter, memory≠cohort guard."""

from __future__ import annotations

import os
import sys
import types
import importlib
from datetime import datetime, timedelta, timezone
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock

import pytest

os.environ.setdefault(
    "ENCRYPTION_SECRET",
    "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv",
)

from models.memory_evidence import ArtifactPreservationState, MemoryEvidence, SourceState
from models.product_memory import (
    MemoryAccessPolicy,
    MemoryItemStatus,
    MemoryTier,
    ProcessingState,
    MemoryItem,
)

from tests.unit.memory_import_isolation import ensure_utils_memory_packages_importable

ensure_utils_memory_packages_importable()
from utils.memory.canonical_visibility_filter import filter_canonical_default_visible_items


def _refresh_memory_system_bindings():
    memory_system_mod = importlib.import_module("utils.memory.memory_system")
    globals()["MemorySystem"] = memory_system_mod.MemorySystem
    globals()["resolve_memory_system"] = memory_system_mod.resolve_memory_system
    return memory_system_mod


_refresh_memory_system_bindings()


class _AutoMockModule(ModuleType):
    def __getattr__(self, name):
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


def _load_mcp_sse_module():
    """Import MCP SSE router with the same heavy-dep stubs used by other MCP unit tests."""
    for mod_name in [
        "database._client",
        "database.redis_db",
        "database.conversations",
        "database.memories",
        "database.vector_db",
        "database.mcp_api_key",
        "database.users",
        "database.action_items",
        "database.goals",
        "database.chat",
        "database.screen_activity",
        "database.daily_summaries",
        "database.x_posts",
        "firebase_admin",
        "firebase_admin.auth",
        "google.cloud.firestore",
        "pinecone",
        "utils.other.endpoints",
        "utils.other.storage",
        "utils.executors",
        "utils.apps",
        "utils.llm.memories",
        "utils.conversations.render",
        "utils.subscription",
    ]:
        existing = sys.modules.get(mod_name)
        if not isinstance(existing, _AutoMockModule):
            sys.modules[mod_name] = _AutoMockModule(mod_name)

    sys.modules["utils.other.endpoints"].check_rate_limit_inline = MagicMock()
    sys.modules["utils.other.endpoints"].with_rate_limit = MagicMock(side_effect=lambda dependency, _policy: dependency)
    sys.modules["utils.executors"].db_executor = MagicMock()
    sys.modules["utils.executors"].postprocess_executor = MagicMock()
    sys.modules["utils.apps"].update_personas_async = MagicMock()
    sys.modules["utils.llm.memories"].identify_category_for_memory = MagicMock(return_value="other")

    if "routers.mcp_sse" in sys.modules:
        return sys.modules["routers.mcp_sse"]

    from routers import mcp_sse

    return mcp_sse


class _Snapshot:
    def __init__(self, data=None, *, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        if self._data is None:
            return None
        return dict(self._data)


class _DocumentRef:
    def __init__(self, db_client, path):
        self._db_client = db_client
        self.path = path

    def get(self, timeout=None):
        if self.path not in self._db_client.docs:
            return _Snapshot(None, exists=False)
        return _Snapshot(self._db_client.docs[self.path], exists=True)


class _FirestoreFake:
    def __init__(self, docs=None):
        self.docs = docs or {}

    def document(self, path):
        return _DocumentRef(self, path)


@pytest.fixture(autouse=True)
def _clear_canonical_cohort(monkeypatch):
    from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort

    _refresh_memory_system_bindings()
    clear_canonical_cohort(monkeypatch)
    monkeypatch.delenv("MEMORY_MODE", raising=False)
    monkeypatch.delenv("MEMORY_ENABLED_USERS", raising=False)


def _processed_short_term_item(*, memory_id: str = "mem-st") -> MemoryItem:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    evidence = MemoryEvidence(
        evidence_id="ev1",
        source_type="conversation",
        source_id="conv-1",
        source_version="v1",
        conversation_id="conv-1",
        artifact_preservation=ArtifactPreservationState.preserved,
    )
    return MemoryItem(
        memory_id=memory_id,
        uid="uid-canonical",
        version=1,
        tier=MemoryTier.short_term,
        status=MemoryItemStatus.active,
        processing_state=ProcessingState.processed,
        content="Fresh short-term extraction",
        evidence=[evidence],
        source_state=SourceState.active,
        sensitivity_labels=[],
        visibility="private",
        user_asserted=False,
        captured_at=now,
        updated_at=now,
        expires_at=now + timedelta(days=30),
        ledger_commit_id="commit_1",
        ledger_sequence=1,
        source_commit_id="commit_1",
        source_commit_sequence=1,
        content_hash="hash1",
    )


class TestSharedCanonicalVisibilityFilter:
    def test_processed_short_term_stays_default_visible(self):
        item = _processed_short_term_item()
        policy = MemoryAccessPolicy.for_omi_chat(archive_capability=False)
        now = datetime(2026, 6, 15, tzinfo=timezone.utc)

        visible = filter_canonical_default_visible_items([item], policy=policy, now=now)

        assert len(visible) == 1
        assert visible[0].memory_id == "mem-st"


class TestResolveMemorySystemIgnoresMemoryFlags:
    def test_memory_read_dogfood_stays_legacy_cohort(self, monkeypatch):
        monkeypatch.setenv("MEMORY_MODE", "read")
        monkeypatch.setenv("MEMORY_ENABLED_USERS", "uid-memory")
        db = _FirestoreFake(
            {
                "users/uid-memory/memory_control/state": {
                    "mode": "read",
                    "fallback_projection_ready": True,
                }
            }
        )
        assert resolve_memory_system("uid-memory", db_client=db) == MemorySystem.LEGACY

    def test_canonical_cohort_pins_without_memory_flags(self, monkeypatch):
        from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

        set_canonical_cohort(monkeypatch, "uid-canonical")
        assert resolve_memory_system("uid-canonical", db_client=_FirestoreFake()) == MemorySystem.CANONICAL
        assert resolve_memory_system("uid-legacy", db_client=_FirestoreFake()) == MemorySystem.LEGACY


LEGACY_SSE_UID = "uid-sse-legacy-ws-l"


def _sse_full_memory_doc(*, memory_id: str, content: str) -> dict:
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    return {
        "id": memory_id,
        "uid": LEGACY_SSE_UID,
        "content": content,
        "category": "interesting",
        "created_at": now,
        "updated_at": now,
        "scoring": "01_00_1736899200",
        "visibility": "private",
        "manually_added": False,
        "is_locked": False,
        "user_review": None,
    }


class TestMcpSseLegacySearchParity:
    def test_legacy_sse_search_uses_vector_order_and_full_firestore_docs(self, monkeypatch):
        """SSE legacy search must NOT use REST MCP search_mcp (RRF + slim dict)."""
        from utils.memory import default_read_rollout as rollout

        mcp_sse = _load_mcp_sse_module()
        firestore_fake = _FirestoreFake()

        assert resolve_memory_system(LEGACY_SSE_UID, db_client=firestore_fake) == MemorySystem.LEGACY

        legacy_rollout = rollout.legacy_safe_default_read_rollout_decision(
            uid=LEGACY_SSE_UID,
            source_path="test/ws-l",
            consumer="mcp",
            reason="ws_l_sse_legacy_parity",
        )
        legacy_vector = SimpleNamespace(
            read_decision=rollout.MemoryReadDecision.USE_LEGACY_SAFE,
            memories=[],
            fallback_reason="ws_l_sse_legacy_parity",
        )
        allowed_auth = SimpleNamespace(allowed=True, observability={})

        monkeypatch.setattr(mcp_sse, "db", firestore_fake)
        monkeypatch.setattr(mcp_sse, "read_default_read_rollout", lambda **_: legacy_rollout)
        monkeypatch.setattr(mcp_sse, "search_default_mcp_memories_vector", lambda **_: legacy_vector)
        monkeypatch.setattr(mcp_sse, "authorize_memory_external_default_memory_read", lambda *_, **__: allowed_auth)

        rrf_mock = MagicMock(side_effect=lambda _query, candidates, _limit, k=60: list(reversed(candidates)))
        monkeypatch.setattr("utils.retrieval.hybrid.rrf_rerank", rrf_mock)

        vector_matches = [
            {"memory_id": "mem-low", "score": 0.55},
            {"memory_id": "mem-high", "score": 0.95},
        ]
        find_similar = MagicMock(return_value=vector_matches)
        monkeypatch.setattr(mcp_sse.vector_db, "find_similar_memories", find_similar)
        monkeypatch.setattr(
            mcp_sse.memories_db,
            "get_memories_by_ids",
            MagicMock(
                return_value=[
                    _sse_full_memory_doc(memory_id="mem-low", content="lower vector score"),
                    _sse_full_memory_doc(memory_id="mem-high", content="higher vector score"),
                ]
            ),
        )

        auth_context = mcp_sse.ProductAuthorizationContext(
            uid=LEGACY_SSE_UID,
            consumer="mcp",
            surface="mcp_sse",
            app_id="test-app",
            key_id="test-key",
            scopes=("memories.read",),
        )
        result = mcp_sse.execute_tool(
            LEGACY_SSE_UID,
            "search_memories",
            {"query": "vector match", "limit": 10},
            auth_context=auth_context,
        )

        memories = result["memories"]
        assert [memory["id"] for memory in memories] == ["mem-high", "mem-low"]
        assert memories[0]["relevance_score"] == 0.95
        assert "created_at" in memories[0]
        assert "scoring" in memories[0]
        assert "visibility" in memories[0]
        assert set(memories[0].keys()) != {"id", "content", "category", "relevance_score"}
        find_similar.assert_called_once_with(LEGACY_SSE_UID, "vector match", threshold=0.0, limit=30)
        rrf_mock.assert_not_called()


class TestMemorySystemRequestPinning:
    def test_pin_stable_when_underlying_resolver_would_flip(self, monkeypatch):
        from utils.memory.memory_system_pin import (
            clear_memory_system_pin,
            pin_memory_system,
            resolve_pinned_memory_system,
        )
        import utils.memory.memory_system_pin as memory_system_pin

        uid = "uid-pin-flip"
        calls = {"count": 0}

        def flipping_resolve(_uid, *, db_client=None):
            calls["count"] += 1
            return MemorySystem.CANONICAL if calls["count"] == 1 else MemorySystem.LEGACY

        monkeypatch.setattr(memory_system_pin, "resolve_memory_system", flipping_resolve)

        assert pin_memory_system(uid) == MemorySystem.CANONICAL
        assert resolve_pinned_memory_system(uid) == MemorySystem.CANONICAL
        assert resolve_pinned_memory_system(uid) == MemorySystem.CANONICAL
        assert calls["count"] == 1

        clear_memory_system_pin()
        assert resolve_pinned_memory_system(uid) == MemorySystem.LEGACY
        assert calls["count"] == 2

    def test_request_scope_resets_pin_after_block(self, monkeypatch):
        from utils.memory.memory_system_pin import (
            get_pinned_memory_system,
            memory_system_request_scope,
            resolve_pinned_memory_system,
        )

        from tests.unit.canonical_cohort_test_helpers import set_canonical_cohort

        set_canonical_cohort(monkeypatch, "uid-scope")
        with memory_system_request_scope("uid-scope") as pinned:
            assert pinned == MemorySystem.CANONICAL
            assert get_pinned_memory_system(uid="uid-scope") == MemorySystem.CANONICAL
        assert get_pinned_memory_system(uid="uid-scope") is None
        assert resolve_pinned_memory_system("uid-scope") == MemorySystem.CANONICAL

    def test_unpinned_resolve_matches_static_legacy_and_canonical(self, monkeypatch):
        from utils.memory.memory_system_pin import clear_memory_system_pin, resolve_pinned_memory_system

        from tests.unit.canonical_cohort_test_helpers import clear_canonical_cohort, set_canonical_cohort

        clear_memory_system_pin()
        clear_canonical_cohort(monkeypatch)
        assert resolve_pinned_memory_system("uid-legacy") == MemorySystem.LEGACY

        set_canonical_cohort(monkeypatch, "uid-canonical")
        assert resolve_pinned_memory_system("uid-canonical") == MemorySystem.CANONICAL
        assert resolve_pinned_memory_system("uid-other") == MemorySystem.LEGACY
