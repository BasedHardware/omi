from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.frame_request import FrameRequest, FrameRequestState
from routers import frame_requests
from utils.other.endpoints import get_current_user_uid


@pytest.fixture(autouse=True)
def _deny_authority(monkeypatch):
    async def deny(*_args, **_kwargs):
        raise PermissionError("disabled")

    monkeypatch.setattr(frame_requests, "authorize_frame_request", deny)


def _enable_authority(monkeypatch, generation: int) -> None:
    async def allow(_uid, account_generation, **_kwargs):
        if account_generation != generation:
            raise PermissionError("generation mismatch")

    monkeypatch.setattr(frame_requests, "authorize_frame_request", allow)


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
    _enable_authority(monkeypatch, 7)
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


def test_create_route_accepts_temporary_non_conversation_requests(monkeypatch):
    _enable_authority(monkeypatch, 0)
    calls = {}

    def enqueue(*args, **kwargs):
        calls.update(kwargs)
        return _request(), False

    monkeypatch.setattr(frame_requests, "enqueue_frame_request", enqueue)
    response = _client().post(
        "/v1/frame-requests",
        json={
            "device_id": "mac-1",
            "dedupe_key": "dedupe-1",
            "account_generation": 0,
            "screenshot_id": "42",
            "requested_ttl_seconds": 518400,
        },
    )
    assert response.status_code == 200
    assert calls["conversation_id"] is None
    assert calls["requested_ttl_seconds"] == 518400


def test_temporary_image_read_is_owner_fenced_and_never_promotes(monkeypatch):
    _enable_authority(monkeypatch, 7)
    now = datetime.now(timezone.utc)
    temporary = FrameRequest(
        request_id="frame-1",
        uid="uid-1",
        device_id="mac-1",
        account_generation=7,
        dedupe_key="dedupe-1",
        screenshot_id="42",
        state=FrameRequestState.uploaded,
        created_at=now,
        expires_at=now.replace(year=now.year + 1),
        uploaded_at=now,
        byte_count=3,
        content_type="image/jpeg",
        storage_id="storage-1",
        cleanup_state="pending",
        cleanup_next_attempt_at=now,
    )
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda *_args: temporary)
    monkeypatch.setattr(frame_requests, "download_frame_request_pixels", lambda *_args: b"jpg")

    response = _client().get("/v1/frame-requests/temporary/frame-1/image?account_generation=7")

    assert response.status_code == 200
    assert response.content == b"jpg"
    assert response.headers["content-type"] == "image/jpeg"
    assert temporary.state == FrameRequestState.uploaded


def test_temporary_image_read_force_refreshes_authority_before_releasing_pixels(monkeypatch):
    calls = []

    async def authorize(_uid, account_generation, **kwargs):
        assert account_generation == 7
        calls.append(kwargs.get("force_refresh", False))
        if kwargs.get("force_refresh"):
            raise PermissionError("kill switch enabled")

    monkeypatch.setattr(frame_requests, "authorize_frame_request", authorize)
    now = datetime.now(timezone.utc)
    temporary = FrameRequest(
        request_id="frame-1",
        uid="uid-1",
        device_id="mac-1",
        account_generation=7,
        dedupe_key="dedupe-1",
        screenshot_id="42",
        state=FrameRequestState.uploaded,
        created_at=now,
        expires_at=now.replace(year=now.year + 1),
        uploaded_at=now,
        byte_count=3,
        content_type="image/jpeg",
        storage_id="storage-1",
        cleanup_state="pending",
        cleanup_next_attempt_at=now,
    )
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda *_args: temporary)
    download = MagicMock(return_value=b"jpg")
    monkeypatch.setattr(frame_requests, "download_frame_request_pixels", download)

    response = _client().get("/v1/frame-requests/temporary/frame-1/image?account_generation=7")

    assert response.status_code == 404
    assert calls == [False, True]
    download.assert_not_called()


def test_temporary_image_read_rejects_conversation_owned_pixels(monkeypatch):
    _enable_authority(monkeypatch, 7)
    row = _request().model_copy(update={"account_generation": 7, "conversation_id": "conversation-1"})
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda *_args: row)

    response = _client().get("/v1/frame-requests/temporary/frame-1/image?account_generation=7")

    assert response.status_code == 404


def test_status_read_reports_uploaded_without_promoting(monkeypatch):
    _enable_authority(monkeypatch, 7)
    row = _request().model_copy(update={"account_generation": 7, "state": FrameRequestState.claimed})
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda *_args: row)

    response = _client().get("/v1/frame-requests/status/frame-1?account_generation=7")

    assert response.status_code == 200
    assert response.json()["request"]["state"] == "claimed"


def test_temporary_image_read_rejects_stale_account_generation(monkeypatch):
    _enable_authority(monkeypatch, 7)
    row = _request().model_copy(update={"account_generation": 6})
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda *_args: row)

    response = _client().get("/v1/frame-requests/temporary/frame-1/image?account_generation=7")

    assert response.status_code == 404


def test_pending_route_is_owner_device_scoped(monkeypatch):
    _enable_authority(monkeypatch, 0)
    monkeypatch.setattr(
        frame_requests,
        "list_pending_frame_requests",
        lambda *args, **kwargs: [_request()],
    )
    response = _client().get("/v1/frame-requests/pending?device_id=mac-1&account_generation=0")
    assert response.status_code == 200
    assert [item["request_id"] for item in response.json()["requests"]] == ["frame-1"]


def test_state_route_maps_owner_mismatch_to_forbidden(monkeypatch):
    _enable_authority(monkeypatch, 0)

    def reject(*args, **kwargs):
        raise PermissionError("frame request owner or account generation mismatch")

    monkeypatch.setattr(frame_requests, "transition_frame_request", reject)
    response = _client().post(
        "/v1/frame-requests/frame-1/state",
        json={"state": FrameRequestState.claimed.value, "device_id": "other-device"},
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "frame_request_owner_mismatch"}
