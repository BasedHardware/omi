"""Exercise the served contract with real FastAPI validation and fake storage."""

from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config.mcp_scopes import CONNECTOR_ACCESS_REGISTRY, MCP_READ_ONLY_API_KEY_SCOPES, MCP_SUPPORTED_SCOPES
from models.connector_access import connector_access
from routers import api_key_management as keys
from routers import mcp


def test_connector_rows_are_supported_and_do_not_imply_writes():
    assert set(CONNECTOR_ACCESS_REGISTRY) == {"chatgpt", "mcp_api_key", "claude"}
    for name in CONNECTOR_ACCESS_REGISTRY:
        contract = connector_access(name)
        for scopes in (contract.required_scopes, contract.default_scopes):
            assert set(scopes) <= set(MCP_SUPPORTED_SCOPES)
            assert all(scope.endswith(".read") for scope in scopes)
    assert connector_access("claude").required_scopes == []
    assert MCP_READ_ONLY_API_KEY_SCOPES == connector_access("mcp_api_key").default_scopes


def test_grants_and_key_endpoints_serve_registry_even_without_grants_or_keys(monkeypatch):
    app = FastAPI()
    app.include_router(mcp.router)
    app.include_router(keys.mcp_router)
    app.dependency_overrides[keys.get_current_user_id] = lambda: "test-user"
    monkeypatch.setattr(mcp.mcp_oauth_db, "list_user_grants", lambda uid: [])
    monkeypatch.setattr(keys.mcp_api_key_db, "get_mcp_keys_for_user_with_repair_info", lambda uid: ([], []))
    persisted = keys.McpApiKey(
        id="key-1", name="test", key_prefix="omi_mcp_test", created_at=datetime.now(timezone.utc), scopes=["goals.read"]
    )
    monkeypatch.setattr(keys.mcp_api_key_db, "create_mcp_key", lambda *args, **kwargs: ("raw-test-key", persisted))
    expected = {
        name: {field: list(values) for field, values in row.items()} for name, row in CONNECTOR_ACCESS_REGISTRY.items()
    }
    with TestClient(app) as client:
        grants = client.get("/v1/mcp/oauth/grants")
        assert grants.status_code == 200
        assert grants.json() == {"grants": [], "connector_access": expected}
        # Released key lists stay arrays. The scope contract works before the first key exists.
        assert client.get("/v1/mcp/keys").json() == []
        contract = client.get("/v1/mcp/keys/scopes")
        assert contract.status_code == 200
        assert contract.json() == expected["mcp_api_key"]
        created = client.post("/v1/mcp/keys", json={"name": "test", "scopes": ["goals.read"]})
        assert created.status_code == 200
        assert created.json()["connector_access"] == expected["mcp_api_key"]
        assert created.json()["scopes"] == ["goals.read"]


def test_grants_response_decodes_without_connector_access_from_older_clients():
    # Older clients and recorded responses predate the field; it must stay optional.
    assert "connector_access" not in mcp.McpOauthGrantsResponse.model_json_schema().get("required", [])
    assert mcp.McpOauthGrantsResponse(grants=[]).connector_access == {}
