"""Hermetic credential introspection contract tests."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from scripts import export_openapi


@pytest.fixture
def boundary(monkeypatch):
    original_env = dict(os.environ)
    monkeypatch.syspath_prepend(str(export_openapi.E2E_DIR))
    export_openapi.configure_hermetic_environment()
    try:
        with export_openapi.record_and_block_outbound_network():
            export_openapi.install_hermetic_dependency_patches()
            from routers import developer_key
            from utils.other import endpoints

            monkeypatch.setattr(endpoints, "_enforce_rate_limit", lambda *args, **kwargs: None)
            app = FastAPI()
            app.include_router(developer_key.router)
            yield app, developer_key
    finally:
        os.environ.clear()
        os.environ.update(original_env)


@pytest.mark.parametrize("scopes", [["goals:write"], [], None])
def test_only_calling_key_metadata_is_returned(boundary, monkeypatch, scopes):
    app, module = boundary
    app.dependency_overrides[module.get_api_key_auth] = lambda: module.ApiKeyAuth(
        uid="owner", scopes=scopes, app_id="developer_api", key_id="calling-key"
    )
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    calls = []
    raw = {
        "user_id": "owner",
        "name": "Narrow key",
        "key_prefix": "omi_dev_123456",
        "created_at": now,
        "hashed_key": "private-hash",
        "content": "private-content",
        "scopes": scopes,
    }
    snapshot = SimpleNamespace(id="calling-key", exists=True, to_dict=lambda: raw)

    class FakeStore:
        def collection(self, name):
            calls.append(name)
            return self

        def document(self, key_id):
            calls.append(key_id)
            return self

        def get(self):
            return snapshot

    monkeypatch.setattr(module, "get_firestore_client", lambda: FakeStore())
    response = TestClient(app).get("/v1/dev/key")
    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "id",
        "name",
        "key_prefix",
        "scopes",
        "created_at",
        "last_used_at",
    }
    assert payload["id"] == "calling-key"
    assert payload["scopes"] == (module.READ_ONLY_SCOPES if scopes is None else scopes)
    assert "private" not in response.text
    assert calls == ["dev_api_keys", "calling-key"]


def test_invalid_key_is_unauthorized(boundary, monkeypatch):
    app, module = boundary
    import dependencies

    monkeypatch.setattr(
        dependencies.dev_api_key_db,
        "get_api_key_auth_result",
        lambda token: SimpleNamespace(context=None, repairs=frozenset()),
    )
    monkeypatch.setattr(
        module,
        "get_firestore_client",
        lambda: pytest.fail("Unauthorized database read"),
    )
    response = TestClient(app).get("/v1/dev/key", headers={"Authorization": "Bearer omi_dev_" + "a" * 32})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"


def test_rate_limiter_unavailable_does_not_fetch_metadata(boundary, monkeypatch):
    app, module = boundary
    from utils.other import endpoints

    app.dependency_overrides[module.get_api_key_auth] = lambda: module.ApiKeyAuth(
        uid="owner", scopes=[], app_id="developer_api", key_id="calling-key"
    )

    def deny(key, policy, *, fail_closed=False):
        assert key == "app:developer_api:key:calling-key"
        assert policy == "dev:key_read"
        assert fail_closed is True
        raise HTTPException(status_code=503, detail="Rate limiter unavailable")

    monkeypatch.setattr(endpoints, "_enforce_rate_limit", deny)
    monkeypatch.setattr(
        module,
        "get_firestore_client",
        lambda: pytest.fail("Rate-limited database read"),
    )
    assert TestClient(app).get("/v1/dev/key").status_code == 503


@pytest.mark.parametrize("raw", [None, {"user_id": "another-owner"}])
def test_missing_or_wrong_owner_key_is_unauthorized(boundary, monkeypatch, raw):
    app, module = boundary
    app.dependency_overrides[module.get_api_key_auth] = lambda: module.ApiKeyAuth(
        uid="owner", scopes=[], app_id="developer_api", key_id="calling-key"
    )
    snapshot = SimpleNamespace(exists=raw is not None, to_dict=lambda: raw)
    store = SimpleNamespace(
        collection=lambda name: SimpleNamespace(document=lambda key: SimpleNamespace(get=lambda: snapshot))
    )
    monkeypatch.setattr(module, "get_firestore_client", lambda: store)
    assert TestClient(app).get("/v1/dev/key").status_code == 401
