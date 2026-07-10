"""Task integration route and external-call seam coverage."""

import asyncio
import json

import httpx


def _todoist_task_payload(title="E2E task"):
    return {
        "title": title,
        "description": "from hermetic test",
        "due_date": "2026-01-02T00:00:00Z",
    }


def _save_todoist_integration(client, auth_headers, **overrides):
    payload = {"connected": True, "access_token": "todoist-token"}
    payload.update(overrides)
    response = client.put("/v1/task-integrations/todoist", json=payload, headers=auth_headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"status": "ok", "app_key": "todoist"}
    return payload


def _get_todoist_integration(client, auth_headers):
    response = client.get("/v1/task-integrations", headers=auth_headers)
    assert response.status_code == 200, response.text
    return response.json()["integrations"].get("todoist")


def _patch_todoist_transport(monkeypatch, handler):
    import utils.task_integrations_ops as task_integrations_ops

    fake_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(task_integrations_ops, "http_client", fake_client)
    return fake_client


def _close_async_client(fake_client):
    asyncio.run(fake_client.aclose())


def test_task_integration_crud_default_and_todoist_task_creation(client, auth_headers, monkeypatch):
    _save_todoist_integration(client, auth_headers)

    listed = client.get("/v1/task-integrations", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    body = listed.json()
    assert body["integrations"]["todoist"]["connected"] is True
    assert body["default_app"] is None

    default = client.put("/v1/task-integrations/default", json={"app_key": "todoist"}, headers=auth_headers)
    assert default.status_code == 200, default.text
    assert default.json() == {"default_app": "todoist"}

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(201, json={"id": "todo-123"})

    fake_client = _patch_todoist_transport(monkeypatch, handler)

    try:
        created = client.post(
            "/v1/task-integrations/todoist/tasks",
            json=_todoist_task_payload(),
            headers=auth_headers,
        )
    finally:
        _close_async_client(fake_client)

    assert created.status_code == 200, created.text
    assert created.json() == {"success": True, "external_task_id": "todo-123", "error": None}
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://api.todoist.com/rest/v2/tasks"
    assert request.headers["authorization"] == "Bearer todoist-token"
    payload = json.loads(request.content)
    assert payload["content"] == "E2E task"
    assert payload["description"] == "from hermetic test"
    assert payload["due_string"] == "2026-01-02"

    delete = client.delete("/v1/task-integrations/todoist", headers=auth_headers)
    assert delete.status_code == 204, delete.text

    after_delete = client.get("/v1/task-integrations", headers=auth_headers)
    assert after_delete.status_code == 200, after_delete.text
    assert "todoist" not in after_delete.json()["integrations"]
    assert after_delete.json()["default_app"] is None

    delete_missing = client.delete("/v1/task-integrations/todoist", headers=auth_headers)
    assert delete_missing.status_code == 404, delete_missing.text
    assert delete_missing.json()["detail"] == "Task integration not found"


def test_task_creation_returns_not_connected_for_disconnected_integration(client, auth_headers):
    _save_todoist_integration(client, auth_headers, connected=False)

    response = client.post(
        "/v1/task-integrations/todoist/tasks",
        json=_todoist_task_payload("Disconnected task"),
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not connected to todoist"


def test_task_creation_returns_no_access_token_for_connected_integration_without_token(client, auth_headers):
    _save_todoist_integration(client, auth_headers, access_token=None)

    response = client.post(
        "/v1/task-integrations/todoist/tasks",
        json=_todoist_task_payload("Tokenless task"),
        headers=auth_headers,
    )

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "No access token for todoist"


def test_todoist_provider_500_returns_failure_without_disconnect(client, auth_headers, monkeypatch):
    requests = []
    _save_todoist_integration(client, auth_headers)

    def handler(request):
        requests.append(request)
        return httpx.Response(500, json={"error": "upstream unavailable"})

    fake_client = _patch_todoist_transport(monkeypatch, handler)

    try:
        response = client.post(
            "/v1/task-integrations/todoist/tasks",
            json=_todoist_task_payload("Provider 500 task"),
            headers=auth_headers,
        )
    finally:
        _close_async_client(fake_client)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "success": False,
        "external_task_id": None,
        "error": "Todoist API error: 500",
    }
    assert len(requests) == 1
    assert _get_todoist_integration(client, auth_headers)["connected"] is True


def test_todoist_provider_401_marks_integration_disconnected(client, auth_headers, monkeypatch):
    _save_todoist_integration(client, auth_headers, access_token="expired-todoist-token")

    def handler(request):
        return httpx.Response(401, json={"error": "unauthorized"})

    fake_client = _patch_todoist_transport(monkeypatch, handler)

    try:
        response = client.post(
            "/v1/task-integrations/todoist/tasks",
            json=_todoist_task_payload("Expired token task"),
            headers=auth_headers,
        )
    finally:
        _close_async_client(fake_client)

    assert response.status_code == 200, response.text
    assert response.json()["success"] is False
    assert response.json()["error"] == "Todoist API error: 401"
    stored = _get_todoist_integration(client, auth_headers)
    assert stored["connected"] is False
    assert stored["access_token"] == "expired-todoist-token"


def test_todoist_timeout_returns_failure_without_real_network(client, auth_headers, monkeypatch):
    _save_todoist_integration(client, auth_headers)

    def handler(request):
        raise httpx.ConnectTimeout("deterministic Todoist timeout")

    fake_client = _patch_todoist_transport(monkeypatch, handler)

    try:
        response = client.post(
            "/v1/task-integrations/todoist/tasks",
            json=_todoist_task_payload("Timeout task"),
            headers=auth_headers,
        )
    finally:
        _close_async_client(fake_client)

    assert response.status_code == 200, response.text
    assert response.json() == {
        "success": False,
        "external_task_id": None,
        "error": "deterministic Todoist timeout",
    }
