import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.cloud import firestore


@pytest.fixture
def saved(monkeypatch):
    from routers import task_integrations as ti
    from utils.other import endpoints as auth

    writes = []
    monkeypatch.setattr(ti.users_db, "set_task_integration", lambda uid, app_key, data: writes.append(data))
    app = FastAPI()
    app.include_router(ti.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: "uid-1"
    return TestClient(app), writes


def test_clearing_the_asana_project_removes_it(saved):
    client, writes = saved

    resp = client.put(
        "/v1/task-integrations/asana",
        json={"connected": True, "workspace_gid": "ws-2", "project_gid": None, "project_name": None},
    )

    assert resp.status_code == 200
    assert writes[0]["workspace_gid"] == "ws-2"
    assert writes[0]["project_gid"] is firestore.DELETE_FIELD
    assert writes[0]["project_name"] is firestore.DELETE_FIELD


def test_switching_clickup_team_clears_the_old_space_and_list(saved):
    client, writes = saved

    client.put(
        "/v1/task-integrations/clickup",
        json={"team_id": "t-2", "space_id": None, "space_name": None, "list_id": None, "list_name": None},
    )

    for field in ("space_id", "space_name", "list_id", "list_name"):
        assert writes[0][field] is firestore.DELETE_FIELD


def test_fields_left_out_and_null_tokens_are_not_touched(saved):
    client, writes = saved

    client.put("/v1/task-integrations/asana", json={"project_gid": "p-1", "access_token": None})

    assert writes[0]["project_gid"] == "p-1"
    assert "access_token" not in writes[0]
    assert "workspace_gid" not in writes[0]
