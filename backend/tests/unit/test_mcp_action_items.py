from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mcp_test_helpers import load_mcp_router


@pytest.fixture()
def mcp_router():
    return load_mcp_router()


@pytest.fixture()
def client(mcp_router):
    app = FastAPI()
    app.include_router(mcp_router.router)
    app.dependency_overrides[mcp_router.get_uid_from_mcp_api_key] = lambda: "user-123"
    return TestClient(app)


def test_get_action_items_truncates_locked_description(client, mcp_router, monkeypatch):
    captured = {}

    def fake_get_action_items(**kwargs):
        captured.update(kwargs)
        return [
            {"id": "item-1", "description": "x" * 80, "completed": False, "is_locked": True},
            {"id": "item-2", "description": "short", "completed": True, "is_locked": False},
        ]

    monkeypatch.setattr(mcp_router.action_items_db, "get_action_items", fake_get_action_items)

    response = client.get("/v1/mcp/action-items?limit=2&offset=1")
    assert response.status_code == 200
    payload = response.json()

    assert captured["limit"] == 2
    assert captured["offset"] == 1
    assert payload[0]["description"].endswith("...")
    assert len(payload[0]["description"]) == 73
    assert payload[1]["description"] == "short"


def test_create_action_item_sends_notification(client, mcp_router, monkeypatch):
    calls = {}

    def fake_create_action_item(uid, action_item_data):
        calls["create"] = action_item_data
        return "item-1"

    def fake_get_action_item(uid, action_item_id):
        return {"id": action_item_id, "description": "Do it", "completed": False}

    def fake_send_action_item_data_message(**kwargs):
        calls["notify"] = kwargs

    monkeypatch.setattr(mcp_router.action_items_db, "create_action_item", fake_create_action_item)
    monkeypatch.setattr(mcp_router.action_items_db, "get_action_item", fake_get_action_item)
    monkeypatch.setattr(mcp_router, "send_action_item_data_message", fake_send_action_item_data_message)

    response = client.post(
        "/v1/mcp/action-items",
        json={"description": "Do it", "due_at": "2025-01-01T00:00:00Z"},
    )
    assert response.status_code == 200
    assert isinstance(calls["create"]["due_at"], datetime)
    assert calls["notify"]["action_item_id"] == "item-1"
    assert calls["notify"]["due_at"].endswith("+00:00")


def test_update_action_item_clears_due_date_without_notification(client, mcp_router, monkeypatch):
    calls = {}

    def fake_get_action_item(uid, action_item_id):
        return {"id": action_item_id, "description": "Task", "completed": False, "is_locked": False}

    def fake_update_action_item(uid, action_item_id, update_data):
        calls["update"] = update_data
        return True

    monkeypatch.setattr(mcp_router.action_items_db, "get_action_item", fake_get_action_item)
    monkeypatch.setattr(mcp_router.action_items_db, "update_action_item", fake_update_action_item)
    monkeypatch.setattr(mcp_router, "send_action_item_update_message", lambda **kwargs: calls.setdefault("notify", kwargs))

    response = client.patch("/v1/mcp/action-items/item-1", json={"due_at": None})
    assert response.status_code == 200
    assert "due_at" in calls["update"]
    assert calls["update"]["due_at"] is None
    assert "notify" not in calls


def test_update_action_item_sets_completed_timestamp(client, mcp_router, monkeypatch):
    calls = {}
    call_count = {"get": 0}

    def fake_get_action_item(uid, action_item_id):
        call_count["get"] += 1
        if call_count["get"] == 1:
            return {"id": action_item_id, "description": "Task", "completed": False, "is_locked": False}
        return {"id": action_item_id, "description": "Task", "completed": True, "is_locked": False}

    def fake_update_action_item(uid, action_item_id, update_data):
        calls["update"] = update_data
        return True

    monkeypatch.setattr(mcp_router.action_items_db, "get_action_item", fake_get_action_item)
    monkeypatch.setattr(mcp_router.action_items_db, "update_action_item", fake_update_action_item)

    response = client.patch("/v1/mcp/action-items/item-1", json={"completed": True})
    assert response.status_code == 200
    assert calls["update"]["completed"] is True
    assert calls["update"]["completed_at"] is not None


def test_delete_action_item_sends_deletion_notification(client, mcp_router, monkeypatch):
    calls = {}

    def fake_get_action_item(uid, action_item_id):
        return {"id": action_item_id, "description": "Task", "completed": False, "is_locked": False}

    monkeypatch.setattr(mcp_router.action_items_db, "get_action_item", fake_get_action_item)
    monkeypatch.setattr(mcp_router.action_items_db, "delete_action_item", lambda uid, action_item_id: True)
    monkeypatch.setattr(
        mcp_router,
        "send_action_item_deletion_message",
        lambda **kwargs: calls.setdefault("notify", kwargs),
    )

    response = client.delete("/v1/mcp/action-items/item-1")
    assert response.status_code == 204
    assert calls["notify"]["action_item_id"] == "item-1"


def test_update_action_item_rejects_locked_item(client, mcp_router, monkeypatch):
    def fake_get_action_item(uid, action_item_id):
        return {"id": action_item_id, "description": "Task", "completed": False, "is_locked": True}

    monkeypatch.setattr(mcp_router.action_items_db, "get_action_item", fake_get_action_item)

    response = client.patch("/v1/mcp/action-items/item-1", json={"description": "Updated"})
    assert response.status_code == 402
