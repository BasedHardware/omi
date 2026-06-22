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


def _patch_integration_lookup(monkeypatch, integration=None, set_calls=None):
    import routers.task_integrations as task_integrations

    data = integration if integration is not None else {"connected": True, "access_token": "todoist-token"}
    monkeypatch.setattr(
        task_integrations.users_db,
        "get_task_integration",
        lambda uid, app_key: data if app_key == "todoist" else None,
    )
    if set_calls is not None:
        monkeypatch.setattr(
            task_integrations.users_db,
            "set_task_integration",
            lambda uid, app_key, payload: set_calls.append((uid, app_key, payload.copy())),
        )


def _patch_todoist_transport(monkeypatch, handler):
    import routers.task_integrations as task_integrations

    fake_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(task_integrations, "http_client", fake_client)
    return fake_client


def _close_async_client(fake_client):
    asyncio.run(fake_client.aclose())


def test_task_integration_crud_default_and_todoist_task_creation(client, auth_headers, monkeypatch):
    save = client.put(
        "/v1/task-integrations/todoist",
        json={"connected": True, "access_token": "todoist-token"},
        headers=auth_headers,
    )
    assert save.status_code == 200, save.text
    assert save.json() == {"status": "ok", "app_key": "todoist"}

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
    _patch_integration_lookup(monkeypatch)

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

    # Delete is intentionally not asserted here: fake-firestore's nested-subcollection
    # delete path raises KeyError for this shape even though list/default writes work.


def test_task_creation_returns_not_connected_for_disconnected_integration(client, auth_headers, monkeypatch):
    _patch_integration_lookup(monkeypatch, integration={"connected": False, "access_token": "todoist-token"})

    response = client.post(
        "/v1/task-integrations/todoist/tasks",
        json=_todoist_task_payload("Disconnected task"),
        headers=auth_headers,
    )

    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "Not connected to todoist"


def test_task_creation_returns_no_access_token_for_connected_integration_without_token(
    client, auth_headers, monkeypatch
):
    _patch_integration_lookup(monkeypatch, integration={"connected": True})

    response = client.post(
        "/v1/task-integrations/todoist/tasks",
        json=_todoist_task_payload("Tokenless task"),
        headers=auth_headers,
    )

    assert response.status_code == 401, response.text
    assert response.json()["detail"] == "No access token for todoist"


def test_todoist_provider_500_returns_failure_without_disconnect(client, auth_headers, monkeypatch):
    requests = []
    set_calls = []

    def handler(request):
        requests.append(request)
        return httpx.Response(500, json={"error": "upstream unavailable"})

    fake_client = _patch_todoist_transport(monkeypatch, handler)
    _patch_integration_lookup(monkeypatch, set_calls=set_calls)

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
    assert set_calls == []


def test_todoist_provider_401_marks_integration_disconnected(client, auth_headers, monkeypatch):
    integration = {"connected": True, "access_token": "expired-todoist-token"}
    set_calls = []

    def handler(request):
        return httpx.Response(401, json={"error": "unauthorized"})

    fake_client = _patch_todoist_transport(monkeypatch, handler)
    _patch_integration_lookup(monkeypatch, integration=integration, set_calls=set_calls)

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
    assert set_calls == [("123", "todoist", {"connected": False, "access_token": "expired-todoist-token"})]


def test_todoist_timeout_returns_failure_without_real_network(client, auth_headers, monkeypatch):
    def handler(request):
        raise httpx.ConnectTimeout("deterministic Todoist timeout")

    fake_client = _patch_todoist_transport(monkeypatch, handler)
    _patch_integration_lookup(monkeypatch)

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
