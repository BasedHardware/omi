"""Agent VM promotes local_kg_* sync batches to backend knowledge graph."""

from __future__ import annotations

import asyncio
import importlib
import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "agent_vm"


def load_app(tmp_path: Path):
    import os

    os.environ["AUTH_TOKEN"] = "test-token"
    os.environ["DB_PATH"] = str(tmp_path / "omi.db")
    sys.path.insert(0, str(SERVICE))
    sys.modules.pop("main", None)
    module = importlib.import_module("main")
    return module.app, module


def test_sync_promotes_local_kg_nodes_to_backend(tmp_path, monkeypatch) -> None:
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute(
        "CREATE TABLE local_kg_nodes (id INTEGER PRIMARY KEY, nodeId TEXT, label TEXT, nodeType TEXT, aliasesJson TEXT, createdAt TEXT, updatedAt TEXT)"
    )
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    captured: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "table": "local_kg_nodes",
                "merged": 1,
                "skipped": 0,
                "nodes_evicted": 0,
                "edges_evicted": 0,
            }

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return Response()

    module.runtime.firebase_token = "firebase-token"
    module.runtime.backend_url = "https://api.test"
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_: Client())

    rows = [{"nodeId": "node-1", "label": "Omi", "nodeType": "org", "aliasesJson": "[]"}]
    with TestClient(app) as client:
        response = client.post(
            "/sync", headers={"Authorization": "Bearer test-token"}, json={"table": "local_kg_nodes", "rows": rows}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["applied"] == 1
    assert body["table"] == "local_kg_nodes"
    assert body["promotion"]["merged"] == 1
    assert captured["url"] == "https://api.test/v1/knowledge-graph/sync"
    assert captured["headers"] == {"Authorization": "Bearer firebase-token"}
    assert captured["json"] == {"table": "local_kg_nodes", "rows": rows}


def test_sync_omits_promotion_without_firebase_token(tmp_path) -> None:
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute(
        "CREATE TABLE local_kg_edges (id INTEGER PRIMARY KEY, edgeId TEXT, sourceNodeId TEXT, targetNodeId TEXT, label TEXT, createdAt TEXT)"
    )
    connection.commit()
    connection.close()
    assert module.runtime.open_database()
    module.runtime.firebase_token = None

    with TestClient(app) as client:
        response = client.post(
            "/sync",
            headers={"Authorization": "Bearer test-token"},
            json={
                "table": "local_kg_edges",
                "rows": [
                    {
                        "edgeId": "edge-1",
                        "sourceNodeId": "a",
                        "targetNodeId": "b",
                        "label": "knows",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert response.json()["applied"] == 1
    assert "promotion" not in response.json()


def test_promote_local_kg_skips_without_firebase_token(tmp_path) -> None:
    _, module = load_app(tmp_path)
    module.runtime.firebase_token = None
    result = asyncio.run(
        module.promote_local_kg_to_backend(
            "local_kg_nodes",
            [{"nodeId": "n1", "label": "Test"}],
        )
    )
    assert result is None


def test_promote_local_kg_raises_on_backend_error(tmp_path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    module.runtime.firebase_token = "firebase-token"

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            raise module.httpx.HTTPError("backend unavailable")

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_: Client())
    with pytest.raises(module.HTTPException) as error:
        asyncio.run(
            module.promote_local_kg_to_backend(
                "local_kg_nodes",
                [{"nodeId": "n1", "label": "Test"}],
            )
        )
    assert error.value.status_code == 502


def test_sync_fails_when_local_kg_promotion_fails(tmp_path, monkeypatch) -> None:
    app, module = load_app(tmp_path)
    connection = sqlite3.connect(module.runtime.db_path)
    connection.execute(
        "CREATE TABLE local_kg_edges (id INTEGER PRIMARY KEY, edgeId TEXT, sourceNodeId TEXT, targetNodeId TEXT, label TEXT, createdAt TEXT)"
    )
    connection.commit()
    connection.close()
    assert module.runtime.open_database()

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            raise module.httpx.ConnectError("backend unavailable")

    module.runtime.firebase_token = "firebase-token"
    module.runtime.backend_url = "https://api.test"
    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_: Client())

    with TestClient(app) as client:
        response = client.post(
            "/sync",
            headers={"Authorization": "Bearer test-token"},
            json={
                "table": "local_kg_edges",
                "rows": [
                    {
                        "edgeId": "edge-1",
                        "sourceNodeId": "a",
                        "targetNodeId": "b",
                        "label": "knows",
                    }
                ],
            },
        )

    assert response.status_code == 502


def test_promote_local_kg_skips_canonical_conflict(tmp_path, monkeypatch) -> None:
    _, module = load_app(tmp_path)
    module.runtime.firebase_token = "firebase-token"
    module.runtime.backend_url = "https://api.test"

    class Response:
        status_code = 409

        def raise_for_status(self):
            raise module.httpx.HTTPStatusError(
                "conflict",
                request=module.httpx.Request("POST", "https://api.test/v1/knowledge-graph/sync"),
                response=module.httpx.Response(409),
            )

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def post(self, *_args, **_kwargs):
            return Response()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_: Client())
    result = asyncio.run(
        module.promote_local_kg_to_backend(
            "local_kg_nodes",
            [{"nodeId": "n1", "label": "Test"}],
        )
    )
    assert result is None
