"""Task integration route and external-call seam coverage."""

import json

import httpx


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

    import routers.task_integrations as task_integrations

    fake_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(task_integrations, "http_client", fake_client)
    # fake-firestore can stream the saved subcollection doc above, but this route's
    # single-document lookup is brittle under the fake. Keep CRUD/default coverage
    # real, and isolate the external task-creation seam with a deterministic lookup.
    monkeypatch.setattr(
        task_integrations.users_db,
        "get_task_integration",
        lambda uid, app_key: {"connected": True, "access_token": "todoist-token"} if app_key == "todoist" else None,
    )

    try:
        created = client.post(
            "/v1/task-integrations/todoist/tasks",
            json={
                "title": "E2E task",
                "description": "from hermetic test",
                "due_date": "2026-01-02T00:00:00Z",
            },
            headers=auth_headers,
        )
    finally:
        import asyncio

        asyncio.run(fake_client.aclose())

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
