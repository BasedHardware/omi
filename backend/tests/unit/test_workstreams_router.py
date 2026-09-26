import pytest
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient

import database.workstreams as workstreams_db
from models.workstream import (
    Workstream,
    WorkstreamDetailProjection,
    WorkstreamStatus,
)
from routers.canonical_task_access import require_canonical_task_user
from routers.workstreams import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_canonical_task_user] = lambda: "test_user_456"
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


STANDARD_HEADERS = {
    "Idempotency-Key": "test-idem-key-12345",
    "X-Account-Generation": "1",
}


def _dummy_workstream(ws_id="ws_1"):
    now = datetime.now(timezone.utc)
    return Workstream(
        workstream_id=ws_id,
        goal_id="goal_1",
        title="Test Workstream",
        objective="Deliver test results",
        status=WorkstreamStatus.open,
        current_state_summary="In progress",
        next_review_at=None,
        last_meaningful_progress_at=now,
        latest_event_sequence=1,
        created_at=now,
        updated_at=now,
    )


def test_empty_or_whitespace_workstream_id_rejected(client):
    # Exactly 400 for whitespace IDs
    resp1 = client.get("/v1/workstreams/%20")
    assert resp1.status_code == 400
    assert resp1.json()["detail"] == "workstream_id must not be empty or whitespace"

    resp2 = client.patch("/v1/workstreams/%20", headers=STANDARD_HEADERS, json={"title": "New"})
    assert resp2.status_code == 400
    assert resp2.json()["detail"] == "workstream_id must not be empty or whitespace"

    resp3 = client.post(
        "/v1/workstreams/%20/events",
        headers=STANDARD_HEADERS,
        json={"kind": "user_note", "summary": "Sample summary"},
    )
    assert resp3.status_code == 400
    assert resp3.json()["detail"] == "workstream_id must not be empty or whitespace"

    resp4 = client.get("/v1/workstreams/%20/events")
    assert resp4.status_code == 400
    assert resp4.json()["detail"] == "workstream_id must not be empty or whitespace"

    resp5 = client.get("/v1/workstreams/%20/artifacts")
    assert resp5.status_code == 400
    assert resp5.json()["detail"] == "workstream_id must not be empty or whitespace"

    resp6 = client.get("/v1/workstreams/%20/checkpoints")
    assert resp6.status_code == 400
    assert resp6.json()["detail"] == "workstream_id must not be empty or whitespace"


def test_empty_or_whitespace_artifact_and_runtime_id_rejected(client):
    # Artifact status transition with whitespace artifact_id
    resp = client.patch(
        "/v1/workstreams/ws_1/artifacts/%20/status",
        headers=STANDARD_HEADERS,
        json={"status": "superseded"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "artifact_id must not be empty or whitespace"

    # Continuation checkpoint with whitespace runtime_id in path
    resp_cp = client.put(
        "/v1/workstreams/ws_1/checkpoints/%20",
        headers=STANDARD_HEADERS,
        json={"runtime_id": "valid_rt", "last_event_sequence": 0, "context_summary": "summary"},
    )
    assert resp_cp.status_code == 400
    assert resp_cp.json()["detail"] == "runtime_id must not be empty or whitespace"


def test_runtime_id_mismatch_returns_422(client):
    resp = client.put(
        "/v1/workstreams/ws_1/checkpoints/runtime_abc",
        headers=STANDARD_HEADERS,
        json={"runtime_id": "runtime_xyz", "last_event_sequence": 0, "context_summary": "summary"},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"] == "runtime_id path and body must match"


def test_workstream_not_found_mapped_to_404(client, monkeypatch):
    def mock_get_detail(uid, ws_id):
        raise workstreams_db.WorkstreamNotFoundError(ws_id)

    monkeypatch.setattr(workstreams_db, "get_workstream_detail", mock_get_detail)

    resp = client.get("/v1/workstreams/ws_missing")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Workflow resource not found"


def test_workstream_conflict_mapped_to_409(client, monkeypatch):
    def mock_append_event(*args, **kwargs):
        raise workstreams_db.WorkstreamConflictError("idempotency key reused")

    monkeypatch.setattr(workstreams_db, "append_workstream_event", mock_append_event)

    resp = client.post(
        "/v1/workstreams/ws_1/events",
        headers=STANDARD_HEADERS,
        json={"kind": "user_note", "summary": "Valid summary"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Workflow operation conflicts with current state"


def test_workstream_generation_mismatch_mapped_to_409(client, monkeypatch):
    def mock_update(*args, **kwargs):
        raise workstreams_db.WorkstreamGenerationMismatchError("account gen mismatch")

    monkeypatch.setattr(workstreams_db, "update_workstream", mock_update)

    resp = client.patch(
        "/v1/workstreams/ws_1",
        headers=STANDARD_HEADERS,
        json={"title": "New Title"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Workflow operation conflicts with current state"


def test_value_error_mapped_to_400_clean_detail(client, monkeypatch):
    def mock_resolve(*args, **kwargs):
        raise ValueError("idempotency_key is required")

    monkeypatch.setattr(workstreams_db, "resolve_work_intent", mock_resolve)

    resp = client.post(
        "/v1/work-intents",
        headers=STANDARD_HEADERS,
        json={"origin": "task", "task_id": "task_123"},
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "Invalid workstream request"


def test_unexpected_exception_masked_and_never_leaks_secrets(client, monkeypatch):
    # Simulated sensitive error string with credential and internal paths
    sensitive_token = "sec_abc123xyz789"
    internal_path = "firestore/internal/cluster/node_88"

    def mock_failing_detail(uid, ws_id):
        raise RuntimeError(f"Database cluster timeout: token={sensitive_token} at {internal_path}")

    monkeypatch.setattr(workstreams_db, "get_workstream_detail", mock_failing_detail)

    resp = client.get("/v1/workstreams/ws_1")
    assert resp.status_code == 500
    assert resp.json()["detail"] == "An internal server error occurred"

    # Absolute leak prevention
    assert sensitive_token not in resp.text
    assert internal_path not in resp.text


def test_list_events_and_artifacts_exceptions_handled_gracefully(client, monkeypatch):
    def mock_list_events(*args, **kwargs):
        raise workstreams_db.WorkstreamNotFoundError("ws_1")

    monkeypatch.setattr(workstreams_db, "list_workstream_events", mock_list_events)

    resp_events = client.get("/v1/workstreams/ws_1/events")
    assert resp_events.status_code == 404
    assert resp_events.json()["detail"] == "Workflow resource not found"

    def mock_list_artifacts(*args, **kwargs):
        raise RuntimeError("GCS storage bucket unreachable")

    monkeypatch.setattr(workstreams_db, "list_artifact_descriptors", mock_list_artifacts)

    resp_artifacts = client.get("/v1/workstreams/ws_1/artifacts")
    assert resp_artifacts.status_code == 500
    assert resp_artifacts.json()["detail"] == "An internal server error occurred"


def test_list_checkpoints_exceptions_handled_gracefully(client, monkeypatch):
    def mock_list_checkpoints(*args, **kwargs):
        raise workstreams_db.WorkstreamNotFoundError("ws_1")

    monkeypatch.setattr(workstreams_db, "list_continuation_checkpoints", mock_list_checkpoints)

    resp = client.get("/v1/workstreams/ws_1/checkpoints")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Workflow resource not found"


def test_create_artifact_descriptor_store_error_and_exception(client, monkeypatch):
    def mock_create_artifact(*args, **kwargs):
        raise workstreams_db.WorkstreamConflictError("artifact version collision")

    monkeypatch.setattr(workstreams_db, "create_artifact_descriptor", mock_create_artifact)

    resp = client.post(
        "/v1/workstreams/ws_1/artifacts",
        headers=STANDARD_HEADERS,
        json={
            "logical_key": "art_1",
            "version": 1,
            "kind": "report",
            "uri": "gcs://bucket/art.md",
            "content_hash": "sha256:1234567890abcdef",
        },
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Workflow operation conflicts with current state"


def test_transition_artifact_status_conflict(client, monkeypatch):
    def mock_trans(*args, **kwargs):
        raise workstreams_db.WorkstreamConflictError("status transition not allowed")

    monkeypatch.setattr(workstreams_db, "transition_artifact_status", mock_trans)

    resp = client.patch(
        "/v1/workstreams/ws_1/artifacts/art_1/status",
        headers=STANDARD_HEADERS,
        json={"status": "superseded"},
    )
    assert resp.status_code == 409
    assert resp.json()["detail"] == "Workflow operation conflicts with current state"


def test_import_task_goal_links_store_error(client, monkeypatch):
    def mock_import(*args, **kwargs):
        raise workstreams_db.WorkstreamNotFoundError("goal:goal_404")

    monkeypatch.setattr(workstreams_db, "import_task_goal_links", mock_import)

    resp = client.post(
        "/v1/workflow-migrations/task-goal-links",
        headers=STANDARD_HEADERS,
        json={"links": [{"task_id": "task_1", "goal_id": "goal_404"}]},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Workflow resource not found"


def test_get_workstream_detail_success(client, monkeypatch):
    ws = _dummy_workstream("ws_valid")
    detail = WorkstreamDetailProjection(
        workstream=ws,
        recent_events=[],
        tasks=[],
        artifacts=[],
        checkpoints=[],
    )

    monkeypatch.setattr(workstreams_db, "get_workstream_detail", lambda uid, ws_id: detail)

    resp = client.get("/v1/workstreams/ws_valid")
    assert resp.status_code == 200
    data = resp.json()
    assert data["workstream"]["workstream_id"] == "ws_valid"
    assert data["workstream"]["title"] == "Test Workstream"
