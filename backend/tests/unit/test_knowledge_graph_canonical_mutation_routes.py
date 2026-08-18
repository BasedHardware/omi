"""Graph mutation routes must gate on real per-account canonical state.

`165c041a93` gated rebuild/delete on a per-account predicate: canonical state
established, or stored memory-graph assertions. `5724a10084` replaced that body
with an unconditional `return True`, so every account got

    409 Canonical knowledge graph state is derived from canonical memories and
    cannot be deleted or rebuilt directly.

including accounts with no `memory_state/head` at all — canonical intake is
fenced in production, and the convergence shipped no backfill, so there was no
derived state to protect. Mobile rendered the 409 body straight to the screen.
`fbb005c15b` restored the GET fallback; this suite covers the mutation side.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import knowledge_graph as kg_db
from routers import knowledge_graph as kg_router
from utils.memory import canonical_graph as kg
from utils.other import endpoints as auth

UID = "uid-arbitrary-account"


class _Page:
    nodes: List[Dict[str, Any]] = [{"id": "c1", "label": "Ada"}]
    edges: List[Dict[str, Any]] = []
    has_more = False
    next_cursor = None
    catalog_nodes: List[Dict[str, Any]] = []


def _canonical_unavailable(*_args: Any, **_kwargs: Any):
    raise kg.CanonicalGraphReadUnavailable("missing_state_head")


@pytest.fixture
def client(monkeypatch):
    # Rate limiting is not under test here and its counters leak across cases.
    monkeypatch.setattr(auth, "_enforce_rate_limit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


@pytest.fixture
def deleted(monkeypatch):
    """Record legacy graph deletions and keep them out of Firestore."""
    calls: List[str] = []
    monkeypatch.setattr(kg_db, "delete_knowledge_graph", lambda uid, **_kw: calls.append(uid))
    monkeypatch.setattr(kg_router, "get_user_name", lambda uid: "Ada")
    return calls


def _legacy_principal(monkeypatch) -> None:
    """No memory_state/head, no assertions — the unmigrated majority."""
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _canonical_unavailable)
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: False)


def test_legacy_principal_can_rebuild(client, monkeypatch, deleted):
    _legacy_principal(monkeypatch)
    scheduled: List[Any] = []
    # TestClient runs background tasks inline; the task itself has its own tests.
    monkeypatch.setattr(kg_router, "_rebuild_graph_task", lambda uid, user_name: scheduled.append((uid, user_name)))

    response = client.post("/v1/knowledge-graph/rebuild")

    assert response.status_code == 200
    assert response.json()["status"] == "rebuilding"
    assert deleted == [UID]
    assert scheduled == [(UID, "Ada")]


def test_legacy_principal_can_delete(client, monkeypatch, deleted):
    _legacy_principal(monkeypatch)

    response = client.delete("/v1/knowledge-graph")

    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    assert deleted == [UID]


def test_established_canonical_state_still_conflicts(client, monkeypatch, deleted):
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", lambda *a, **k: _Page())

    rebuild = client.post("/v1/knowledge-graph/rebuild")
    delete = client.delete("/v1/knowledge-graph")

    assert rebuild.status_code == 409
    assert delete.status_code == 409
    assert rebuild.json()["detail"] == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
    assert delete.json()["detail"] == kg_router.CANONICAL_GRAPH_MUTATION_CONFLICT
    assert deleted == []


def test_stored_assertions_still_conflict_without_a_state_head(client, monkeypatch, deleted):
    # Assertion-backed graphs are derived state even when the canonical read
    # cannot serve them; they must not be rebuilt or deleted through here.
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _canonical_unavailable)
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: True)

    rebuild = client.post("/v1/knowledge-graph/rebuild")
    delete = client.delete("/v1/knowledge-graph")

    assert rebuild.status_code == 409
    assert delete.status_code == 409
    assert deleted == []


def test_predicate_is_per_account_not_a_constant(monkeypatch):
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _canonical_unavailable)
    monkeypatch.setattr(
        kg_db,
        "has_stored_memory_graph_assertions",
        lambda uid, **_kw: uid == "uid-assertion-backed",
    )

    assert kg_router._is_assertion_backed_graph_account("uid-assertion-backed") is True
    assert kg_router._is_assertion_backed_graph_account("uid-arbitrary-account") is False


def test_rebuild_task_feeds_unlocked_memories_to_the_legacy_rebuild(monkeypatch):
    _legacy_principal(monkeypatch)

    class _Memory:
        def __init__(self, memory_id: str, content: str, is_locked: bool = False):
            self.id = memory_id
            self.content = content
            self.is_locked = is_locked

    class _Service:
        def __init__(self, **_kwargs: Any):
            pass

        def read(self, uid: str, **_kwargs: Any):
            return [_Memory("m1", "one"), _Memory("m2", "locked", is_locked=True)]

    captured: Dict[str, Any] = {}
    monkeypatch.setattr(kg_router, "MemoryService", _Service)
    monkeypatch.setattr(
        kg_router,
        "_run_rebuild_knowledge_graph",
        lambda uid, memories, user_name: captured.update(uid=uid, memories=memories, user_name=user_name),
    )

    kg_router._rebuild_graph_task(UID, "Ada")

    assert captured["memories"] == [{"id": "m1", "content": "one"}]
    assert captured["user_name"] == "Ada"


def test_rebuild_task_is_a_noop_for_an_assertion_backed_account(monkeypatch):
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _canonical_unavailable)
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: True)

    def _must_not_run(*_args: Any, **_kwargs: Any):  # pragma: no cover - asserts absence
        raise AssertionError("legacy rebuild ran for an assertion-backed account")

    monkeypatch.setattr(kg_router, "_run_rebuild_knowledge_graph", _must_not_run)

    kg_router._rebuild_graph_task(UID, "Ada")
