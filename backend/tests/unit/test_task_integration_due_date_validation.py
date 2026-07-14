"""Regression test for POST /v1/task-integrations/{app_key}/tasks due_date validation.

CreateTaskRequest.due_date is a free-form Optional[str] with no format validator. Before the fix,
a malformed value made datetime.fromisoformat(...) raise an unhandled ValueError, returning HTTP 500.
The handler now catches it and returns HTTP 400, mirroring the same guard in routers/conversations.py
and routers/integration.py. These tests mount the task-integrations router and exercise the HTTP layer
with the auth dependency overridden and the Firestore/external calls stubbed (no live services).
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def app_client():
    # conftest sets OPENAI_API_KEY / ENCRYPTION_SECRET before collection, so the router imports cleanly.
    from routers import task_integrations as ti
    from utils.other import endpoints as auth

    app = FastAPI()
    app.include_router(ti.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: "test-uid"
    return TestClient(app, raise_server_exceptions=False), ti


def _connected(uid, app_key):
    return {"connected": True, "access_token": "tok"}


def test_invalid_due_date_returns_400(app_client, monkeypatch):
    """A non-ISO due_date must return 400, not an unhandled 500."""
    client, ti = app_client
    monkeypatch.setattr(ti.users_db, "get_task_integration", _connected)
    # Stub the external creation so a regression that slips past the guard cannot reach a real call.
    monkeypatch.setattr(ti, "create_task_internal", AsyncMock(return_value={"success": True}))

    resp = client.post("/v1/task-integrations/todoist/tasks", json={"title": "buy milk", "due_date": "not-a-date"})

    assert resp.status_code == 400
    assert "due_date" in resp.json()["detail"]


def test_valid_due_date_reaches_creation(app_client, monkeypatch):
    """A valid ISO due_date (with Z suffix) is parsed and forwarded; the happy path is preserved."""
    client, ti = app_client
    monkeypatch.setattr(ti.users_db, "get_task_integration", _connected)
    created = AsyncMock(return_value={"success": True, "external_task_id": "ext-1"})
    monkeypatch.setattr(ti, "create_task_internal", created)

    resp = client.post(
        "/v1/task-integrations/todoist/tasks",
        json={"title": "buy milk", "due_date": "2026-07-11T10:00:00Z"},
    )

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert created.await_count == 1
    assert created.await_args.kwargs["due_date"] is not None  # parsed datetime, not the raw string


def test_missing_due_date_is_allowed(app_client, monkeypatch):
    """No due_date is valid and must not 400."""
    client, ti = app_client
    monkeypatch.setattr(ti.users_db, "get_task_integration", _connected)
    created = AsyncMock(return_value={"success": True, "external_task_id": "ext-2"})
    monkeypatch.setattr(ti, "create_task_internal", created)

    resp = client.post("/v1/task-integrations/todoist/tasks", json={"title": "no due date"})

    assert resp.status_code == 200
    assert created.await_args.kwargs["due_date"] is None
