import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

SENSITIVE_LEAK = "Sensitive connection leak postgres://user:pass_secret_123@db.internal:5432/omi"


@pytest.fixture
def client_with_auth(monkeypatch):
    from routers import task_integrations as ti
    from utils.other import endpoints as auth

    app = FastAPI()
    app.include_router(ti.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: "test-uid-123"

    # Default valid integration data
    valid_data = {
        "connected": True,
        "access_token": "valid_token_xyz",
    }

    async def mock_run_blocking(executor, func, *args, **kwargs):
        return valid_data

    async def mock_ensure_valid_oauth_token(uid, app_key, data):
        return data

    monkeypatch.setattr(ti, "run_blocking", mock_run_blocking)
    monkeypatch.setattr(ti, "ensure_valid_oauth_token", mock_ensure_valid_oauth_token)

    return TestClient(app)


def test_asana_workspaces_sanitizes_exception(client_with_auth, monkeypatch):
    from routers import task_integrations as ti

    async def mock_perform_request(*args, **kwargs):
        raise RuntimeError(SENSITIVE_LEAK)

    monkeypatch.setattr(ti, "perform_request_with_token_retry", mock_perform_request)

    resp = client_with_auth.get("/v1/task-integrations/asana/workspaces")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to fetch Asana workspaces"
    assert SENSITIVE_LEAK not in resp.text


def test_asana_projects_sanitizes_exception(client_with_auth, monkeypatch):
    from routers import task_integrations as ti

    async def mock_perform_request(*args, **kwargs):
        raise RuntimeError(SENSITIVE_LEAK)

    monkeypatch.setattr(ti, "perform_request_with_token_retry", mock_perform_request)

    resp = client_with_auth.get("/v1/task-integrations/asana/projects/ws-test-1")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to fetch Asana projects"
    assert SENSITIVE_LEAK not in resp.text


def test_clickup_teams_sanitizes_exception(client_with_auth, monkeypatch):
    from routers import task_integrations as ti

    async def mock_perform_request(*args, **kwargs):
        raise RuntimeError(SENSITIVE_LEAK)

    monkeypatch.setattr(ti, "perform_request_with_token_retry", mock_perform_request)

    resp = client_with_auth.get("/v1/task-integrations/clickup/teams")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to fetch ClickUp teams"
    assert SENSITIVE_LEAK not in resp.text


def test_clickup_spaces_sanitizes_exception(client_with_auth, monkeypatch):
    from routers import task_integrations as ti

    async def mock_perform_request(*args, **kwargs):
        raise RuntimeError(SENSITIVE_LEAK)

    monkeypatch.setattr(ti, "perform_request_with_token_retry", mock_perform_request)

    resp = client_with_auth.get("/v1/task-integrations/clickup/spaces/team-test-1")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to fetch ClickUp spaces"
    assert SENSITIVE_LEAK not in resp.text


def test_clickup_lists_sanitizes_exception(client_with_auth, monkeypatch):
    from routers import task_integrations as ti

    async def mock_perform_request(*args, **kwargs):
        raise RuntimeError(SENSITIVE_LEAK)

    monkeypatch.setattr(ti, "perform_request_with_token_retry", mock_perform_request)

    resp = client_with_auth.get("/v1/task-integrations/clickup/lists/space-test-1")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "Failed to fetch ClickUp lists"
    assert SENSITIVE_LEAK not in resp.text


def test_preserves_explicit_http_exceptions(client_with_auth, monkeypatch):
    from routers import task_integrations as ti

    async def mock_perform_request(*args, **kwargs):
        raise HTTPException(status_code=403, detail="Forbidden by third-party API")

    monkeypatch.setattr(ti, "perform_request_with_token_retry", mock_perform_request)

    resp = client_with_auth.get("/v1/task-integrations/asana/workspaces")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden by third-party API"
