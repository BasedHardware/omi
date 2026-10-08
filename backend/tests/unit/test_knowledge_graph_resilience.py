"""Unit tests for knowledge graph resilience and error boundaries."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from database import knowledge_graph as kg_db
from routers import knowledge_graph as kg_router
from utils.memory import canonical_graph as kg
from utils.other import endpoints as auth

UID = "uid-resilience-test"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(auth, "_enforce_rate_limit", lambda *args, **kwargs: None)
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    return TestClient(app, raise_server_exceptions=False)


def _canonical_unavailable(*_args, **_kwargs):
    raise kg.CanonicalGraphReadUnavailable("missing_state_head")


def test_get_knowledge_graph_legacy_read_failure_returns_500(client, monkeypatch):
    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _canonical_unavailable)
    monkeypatch.setattr(
        kg_db, "get_knowledge_graph", lambda uid: (_ for _ in ()).throw(RuntimeError("Firestore connection failed"))
    )

    response = client.get("/v1/knowledge-graph")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve knowledge graph"


def test_get_knowledge_graph_unexpected_exception_returns_500(client, monkeypatch):
    def _unexpected_error(*_args, **_kwargs):
        raise ValueError("Corrupted memory page decoding error")

    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _unexpected_error)

    response = client.get("/v1/knowledge-graph")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve knowledge graph"


def test_get_canonical_knowledge_graph_unexpected_exception_returns_500(client, monkeypatch):
    def _unexpected_error(*_args, **_kwargs):
        raise RuntimeError("Firestore stream timeout")

    monkeypatch.setattr(kg, "get_canonical_knowledge_graph", _unexpected_error)

    response = client.get("/v1/knowledge-graph/canonical")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to retrieve canonical knowledge graph"


def test_delete_knowledge_graph_db_failure_returns_500_with_proper_detail(client, monkeypatch):
    monkeypatch.setattr(kg_router, "_require_legacy_graph_mutation", lambda uid: None)
    monkeypatch.setattr(
        kg_db, "delete_knowledge_graph", lambda uid: (_ for _ in ()).throw(RuntimeError("Firestore delete failed"))
    )

    response = client.delete("/v1/knowledge-graph")

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to delete knowledge graph"
