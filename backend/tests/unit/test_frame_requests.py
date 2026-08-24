from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from models.frame_request import FrameRequest, FrameRequestState
from routers import frame_requests
from utils.other.endpoints import get_current_user_uid
from utils.retrieval.frame_request_authority import (
    DisabledFrameRequestAuthority,
    FrameRequestAuthorityDecision,
    set_frame_request_authority_for_tests,
)


class _EnabledAuthority:
    def __init__(self, generation: int):
        self.generation = generation

    def decide(self, uid: str) -> FrameRequestAuthorityDecision:
        return FrameRequestAuthorityDecision(enabled=True, account_generation=self.generation)


@pytest.fixture(autouse=True)
def _reset_authority():
    set_frame_request_authority_for_tests(DisabledFrameRequestAuthority())
    yield
    set_frame_request_authority_for_tests(DisabledFrameRequestAuthority())


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(frame_requests.router)
    app.dependency_overrides[get_current_user_uid] = lambda: "uid-1"
    return TestClient(app)


def _request() -> FrameRequest:
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return FrameRequest(
        request_id="frame-1",
        uid="uid-1",
        device_id="mac-1",
        dedupe_key="dedupe-1",
        created_at=now,
        expires_at=now,
    )


def test_frame_request_routes_are_inert_without_rollout_authority():
    response = _client().post(
        "/v1/frame-requests",
        json={"device_id": "mac-1", "dedupe_key": "dedupe-1", "screenshot_id": "42"},
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "frame_requests_unavailable"}


def test_create_route_is_idempotent_and_returns_metadata_only(monkeypatch):
    set_frame_request_authority_for_tests(_EnabledAuthority(7))
    calls = {}

    def enqueue(*args, **kwargs):
        calls.update(kwargs)
        return _request(), True

    monkeypatch.setattr(frame_requests, "enqueue_frame_request", enqueue)
    response = _client().post(
        "/v1/frame-requests",
        json={
            "device_id": "mac-1",
            "account_generation": 7,
            "dedupe_key": "dedupe-1",
            "screenshot_id": "42",
            "conversation_id": "conversation-1",
        },
    )
    assert response.status_code == 200
    assert response.json()["deduplicated"] is True
    assert response.json()["request"]["state"] == "requested"
    assert calls["account_generation"] == 7
    assert "image_base64" not in response.text


def test_create_route_rejects_non_conversation_requests_before_enqueue(monkeypatch):
    set_frame_request_authority_for_tests(_EnabledAuthority(0))
    monkeypatch.setattr(
        frame_requests, "enqueue_frame_request", lambda *args, **kwargs: pytest.fail("must reject early")
    )
    response = _client().post(
        "/v1/frame-requests",
        json={"device_id": "mac-1", "dedupe_key": "dedupe-1", "account_generation": 0},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "conversation_id_required"}


def test_pending_route_is_owner_device_scoped(monkeypatch):
    set_frame_request_authority_for_tests(_EnabledAuthority(0))
    monkeypatch.setattr(
        frame_requests,
        "list_pending_frame_requests",
        lambda *args, **kwargs: [_request()],
    )
    response = _client().get("/v1/frame-requests/pending?device_id=mac-1&account_generation=0")
    assert response.status_code == 200
    assert [item["request_id"] for item in response.json()["requests"]] == ["frame-1"]


def test_state_route_maps_owner_mismatch_to_forbidden(monkeypatch):
    set_frame_request_authority_for_tests(_EnabledAuthority(0))

    def reject(*args, **kwargs):
        raise PermissionError("frame request owner or account generation mismatch")

    monkeypatch.setattr(frame_requests, "transition_frame_request", reject)
    response = _client().post(
        "/v1/frame-requests/frame-1/state",
        json={"state": FrameRequestState.claimed.value, "device_id": "other-device"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "frame_request_owner_mismatch"}
