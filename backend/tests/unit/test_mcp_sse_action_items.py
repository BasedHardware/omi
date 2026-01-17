from datetime import datetime

import pytest

from mcp_test_helpers import load_mcp_sse


@pytest.fixture()
def mcp_sse():
    return load_mcp_sse()


def _get_tool_names(mcp_sse):
    return {tool["name"] for tool in mcp_sse.MCP_TOOLS}


def test_tools_list_includes_action_items(mcp_sse):
    names = _get_tool_names(mcp_sse)
    assert "get_action_items" in names
    assert "create_action_item" in names
    assert "update_action_item" in names
    assert "delete_action_item" in names


def test_get_action_items_truncates_locked_description(mcp_sse, monkeypatch):
    def fake_get_action_items(**_kwargs):
        return [
            {"id": "item-1", "description": "y" * 80, "completed": False, "is_locked": True},
            {"id": "item-2", "description": "short", "completed": True, "is_locked": False},
        ]

    monkeypatch.setattr(mcp_sse.action_items_db, "get_action_items", fake_get_action_items)

    result = mcp_sse.execute_tool("user-1", "get_action_items", {"limit": 2})
    assert result["action_items"][0]["description"].endswith("...")
    assert len(result["action_items"][0]["description"]) == 73
    assert result["action_items"][1]["description"] == "short"


def test_get_action_items_rejects_invalid_date(mcp_sse, monkeypatch):
    monkeypatch.setattr(mcp_sse.action_items_db, "get_action_items", lambda **_kwargs: [])

    with pytest.raises(mcp_sse.ToolExecutionError) as exc:
        mcp_sse.execute_tool("user-1", "get_action_items", {"start_date": "not-a-date"})

    assert exc.value.code == -32602


def test_create_action_item_sends_notification(mcp_sse, monkeypatch):
    calls = {}

    def fake_create_action_item(uid, action_item_data):
        calls["create"] = action_item_data
        return "item-1"

    def fake_send_action_item_data_message(**kwargs):
        calls["notify"] = kwargs

    monkeypatch.setattr(mcp_sse.action_items_db, "create_action_item", fake_create_action_item)
    monkeypatch.setattr(mcp_sse, "send_action_item_data_message", fake_send_action_item_data_message)

    result = mcp_sse.execute_tool(
        "user-1",
        "create_action_item",
        {"description": "Do it", "due_at": "2025-01-01T00:00:00Z"},
    )

    assert result["success"] is True
    assert result["action_item"]["id"] == "item-1"
    assert isinstance(calls["create"]["due_at"], datetime)
    assert calls["notify"]["action_item_id"] == "item-1"


def test_update_action_item_clears_due_date_without_notification(mcp_sse, monkeypatch):
    calls = {}

    def fake_get_action_item(uid, action_item_id):
        return {
            "id": action_item_id,
            "description": "Task",
            "completed": False,
            "is_locked": False,
            "due_at": datetime(2025, 1, 1),
        }

    def fake_update_action_item(uid, action_item_id, update_data):
        calls["update"] = update_data
        return True

    monkeypatch.setattr(mcp_sse.action_items_db, "get_action_item", fake_get_action_item)
    monkeypatch.setattr(mcp_sse.action_items_db, "update_action_item", fake_update_action_item)
    monkeypatch.setattr(mcp_sse, "send_action_item_update_message", lambda **kwargs: calls.setdefault("notify", kwargs))

    result = mcp_sse.execute_tool("user-1", "update_action_item", {"action_item_id": "item-1", "due_at": None})
    assert result["success"] is True
    assert calls["update"]["due_at"] is None
    assert "notify" not in calls
    assert result["action_item"]["due_at"] is None


def test_update_action_item_rejects_locked_item(mcp_sse, monkeypatch):
    def fake_get_action_item(uid, action_item_id):
        return {"id": action_item_id, "description": "Task", "completed": False, "is_locked": True}

    monkeypatch.setattr(mcp_sse.action_items_db, "get_action_item", fake_get_action_item)

    with pytest.raises(mcp_sse.ToolExecutionError) as exc:
        mcp_sse.execute_tool("user-1", "update_action_item", {"action_item_id": "item-1", "completed": True})

    assert exc.value.code == -32002


def test_delete_action_item_sends_deletion_notification(mcp_sse, monkeypatch):
    calls = {}

    def fake_get_action_item(uid, action_item_id):
        return {"id": action_item_id, "description": "Task", "completed": False, "is_locked": False}

    monkeypatch.setattr(mcp_sse.action_items_db, "get_action_item", fake_get_action_item)
    monkeypatch.setattr(mcp_sse.action_items_db, "delete_action_item", lambda uid, action_item_id: True)
    monkeypatch.setattr(
        mcp_sse,
        "send_action_item_deletion_message",
        lambda **kwargs: calls.setdefault("notify", kwargs),
    )

    result = mcp_sse.execute_tool("user-1", "delete_action_item", {"action_item_id": "item-1"})
    assert result["success"] is True
    assert calls["notify"]["action_item_id"] == "item-1"
