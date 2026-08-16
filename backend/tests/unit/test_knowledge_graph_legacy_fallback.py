"""GET /v1/knowledge-graph must not fail when the canonical read is unavailable.

#11617 follow-up: `5724a10084` repointed this route at the canonical (v3) graph
and deleted the legacy read in the same commit. Production fences canonical
intake (`MEMORY_MODE=off`), so `users/{uid}/memory_state/head` is never written
and the canonical read raises for essentially every account — the route returned
503 `knowledge_graph_unavailable` to all of them for two days while their graph
sat intact in the legacy store.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import knowledge_graph as kg_db
from routers import knowledge_graph as kg_router
from utils.memory import canonical_graph as kg
from utils.other import endpoints as auth

UID = "uid-kg-fallback"

LEGACY_GRAPH = {
    "nodes": [{"id": "n1", "label": "Ada"}, {"id": "n2", "label": "Lovelace"}],
    "edges": [{"source_id": "n1", "target_id": "n2", "label": "knows"}],
    "truncated": False,
    "node_count": 2,
    "edge_count": 1,
    "node_limit": 500,
    "edge_limit": 500,
}


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def _canonical_unavailable(*_args, **_kwargs):
    raise kg.CanonicalGraphReadUnavailable("missing_state_head")


def test_serves_the_legacy_graph_when_canonical_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _canonical_unavailable)
    monkeypatch.setattr(kg_db, "get_knowledge_graph", lambda uid: dict(LEGACY_GRAPH))

    response = client.get("/v1/knowledge-graph")

    assert response.status_code == 200
    body = response.json()
    assert [node["id"] for node in body["nodes"]] == ["n1", "n2"]
    assert body["edge_count"] == 1
    assert body["node_count"] == 2


def test_an_account_with_no_legacy_graph_gets_an_empty_graph_not_a_503(client, monkeypatch):
    # A user who genuinely has no graph must see an empty one, never an error.
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _canonical_unavailable)
    monkeypatch.setattr(
        kg_db,
        "get_knowledge_graph",
        lambda uid: {"nodes": [], "edges": [], "truncated": False},
    )

    response = client.get("/v1/knowledge-graph")

    assert response.status_code == 200
    assert response.json()["nodes"] == []
    assert response.json()["edges"] == []


def test_canonical_still_wins_when_it_is_available(client, monkeypatch):
    # The fallback must not shadow a working canonical read.
    class _Page:
        nodes = [{"id": "c1"}]
        edges = []
        has_more = False
        next_cursor = None

    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", lambda *a, **k: _Page())

    def _must_not_be_called(uid):  # pragma: no cover - asserts absence
        raise AssertionError("legacy reader called while canonical was available")

    monkeypatch.setattr(kg_db, "get_knowledge_graph", _must_not_be_called)

    response = client.get("/v1/knowledge-graph")

    assert response.status_code == 200
    assert [node["id"] for node in response.json()["nodes"]] == ["c1"]


def test_the_explicit_canonical_route_still_reports_unavailable(client, monkeypatch):
    # /canonical is the caller asking for canonical specifically; silently
    # serving legacy there would misrepresent which store answered.
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _canonical_unavailable)

    response = client.get("/v1/knowledge-graph/canonical")

    assert response.status_code == 503
    assert response.json()["detail"] == "canonical_graph_unavailable"
