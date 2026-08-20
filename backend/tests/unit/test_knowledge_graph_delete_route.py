"""DELETE /v1/knowledge-graph DB-outcome paths with a mocked deletion call.

Covers the delete handler in `routers/knowledge_graph.py`: a successful mocked
`kg_db.delete_knowledge_graph` returns 200 with `status=deleted`, and a raised
DB error surfaces as HTTP 500. The handler has no try/except around the delete,
so Starlette turns the uncaught error into a 500.

Canonical mutation gate cases (409/503) stay in
`test_knowledge_graph_canonical_mutation_routes.py`.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import knowledge_graph as kg_db
from routers import knowledge_graph as kg_router
from utils.memory import canonical_graph as kg
from utils.memory.v3.account_generation_source import (
    V3AccountGenerationFailureReason as Reason,
    V3TrustedAccountGenerationResult as TrustedHead,
)
from utils.other import endpoints as auth

UID = "uid-delete-route"
HEAD_PATH = f"users/{UID}/memory_state/head"


def _legacy_principal(monkeypatch) -> None:
    """No memory_state/head, no assertions — unlocks the legacy delete path."""
    monkeypatch.setattr(kg, "get_firestore_client", lambda: object())
    monkeypatch.setattr(kg_router, "get_firestore_client", lambda: object())
    monkeypatch.setattr(
        kg,
        "read_memory_v3_trusted_account_generation",
        lambda **_kw: TrustedHead(uid=UID, source_path=HEAD_PATH, read_error_reason=Reason.MISSING_STATE_HEAD),
    )
    monkeypatch.setattr(kg_db, "has_stored_memory_graph_assertions", lambda uid, **_kw: False)


def _delete_client(monkeypatch) -> TestClient:
    monkeypatch.setattr(auth, "_enforce_rate_limit", lambda *args, **kwargs: None)
    monkeypatch.setattr(kg_router, "record_fallback", lambda **_kwargs: None)
    app = FastAPI()
    app.include_router(kg_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: UID
    # Uncaught DB errors must become HTTP 500 rather than re-raising in the test client.
    return TestClient(app, raise_server_exceptions=False)


def test_delete_knowledge_graph_returns_200_when_db_delete_succeeds(monkeypatch):
    _legacy_principal(monkeypatch)
    deleted = []
    monkeypatch.setattr(kg_db, "delete_knowledge_graph", lambda uid, **_kw: deleted.append(uid))

    response = _delete_client(monkeypatch).delete("/v1/knowledge-graph")

    assert response.status_code == 200
    assert response.json() == {"status": "deleted"}
    assert deleted == [UID]


def test_delete_knowledge_graph_returns_500_when_db_delete_raises(monkeypatch):
    _legacy_principal(monkeypatch)

    def _boom(uid, **_kw):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(kg_db, "delete_knowledge_graph", _boom)

    response = _delete_client(monkeypatch).delete("/v1/knowledge-graph")

    assert response.status_code == 500
