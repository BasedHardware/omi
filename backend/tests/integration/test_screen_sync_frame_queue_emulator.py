"""Exercise desktop sync and frame queue transactions on a loopback Firestore emulator."""

import logging
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore

from database import _client, frame_requests
from models.frame_request import FrameRequestState
from routers import desktop_screen_crisp
from services.conversation_keyframes import ensure_conversation_keyframe_job
from testing.hermetic_network import block_outbound_network
from utils.retrieval.frame_request_authority import FrameRequestAuthorityDecision
from utils.retrieval.frame_request_policy import FRAME_REQUEST_MAX_PENDING_PER_DEVICE

DEVICE = "mac-a"
GENERATION = 7
CONVERSATION = "conversation-1"


@pytest.fixture
def screen_sync(monkeypatch):
    host = os.environ.get("FIRESTORE_EMULATOR_HOST", "")
    if urlparse(f"//{host}").hostname not in {"localhost", "127.0.0.1", "::1"}:
        pytest.fail("A loopback Firestore emulator is required")
    db = firestore.Client(project="demo-omi-isolated-tests", credentials=AnonymousCredentials())
    monkeypatch.setattr(_client, "_data_plane_firestore_client", db)
    uid = uuid4().hex
    user = db.collection("users").document(uid)
    captured = datetime.now(timezone.utc) - timedelta(minutes=1)
    finished = captured + timedelta(seconds=1)
    job = user.collection("conversation_keyframe_jobs").document(CONVERSATION)

    async def authorize(_uid):
        return FrameRequestAuthorityDecision(enabled=True, account_generation=GENERATION)

    monkeypatch.setattr(desktop_screen_crisp, "resolve_frame_request_authority", authorize)
    app = FastAPI()
    app.include_router(desktop_screen_crisp.router)
    app.dependency_overrides[desktop_screen_crisp._authorized_desktop_user] = lambda: uid
    with block_outbound_network(), TestClient(app) as client:
        conversation = SimpleNamespace(
            id=CONVERSATION,
            source="desktop",
            client_device_id=DEVICE,
            started_at=captured - timedelta(seconds=1),
            finished_at=finished,
        )
        assert ensure_conversation_keyframe_job(uid, conversation, firestore_client=db)

        def sync():
            response = client.post(
                "/v1/screen-activity/sync",
                json={
                    "account_generation": GENERATION,
                    "rows": [
                        {
                            "id": 42,
                            "timestamp": captured.isoformat(),
                            "clientDeviceId": DEVICE,
                            "appName": "Editor",
                            "captureEligible": True,
                        }
                    ],
                },
            )
            assert response.status_code == 200, response.text
            return response.json()["frame_requests"]

        yield uid, user, job, sync
    db.close()


def enqueue(uid, key, **kwargs):
    request, _ = frame_requests.enqueue_frame_request(
        uid, device_id=DEVICE, account_generation=GENERATION, dedupe_key=key, **kwargs
    )
    return request.request_id


def test_full_queue_is_delivered_and_job_retries_after_drain(screen_sync, caplog):
    uid, user, job, sync = screen_sync
    queued = [enqueue(uid, f"pending-{index}") for index in range(FRAME_REQUEST_MAX_PENDING_PER_DEVICE)]
    with pytest.raises(ValueError, match="frame request quota exceeded: pending_count"):
        enqueue(uid, "over-quota")

    assert {item["request_id"] for item in sync()} == set(queued)
    assert job.get().get("state") == "pending"
    assert {row.id for row in user.collection("frame_requests").stream()} == set(queued)
    assert not any(
        record.name == desktop_screen_crisp.__name__ and record.levelno >= logging.ERROR for record in caplog.records
    )

    frame_requests.transition_frame_request(
        uid,
        queued[0],
        next_state=FrameRequestState.failed,
        device_id=DEVICE,
        account_generation=GENERATION,
        terminal_reason="device_capture_unavailable",
    )

    delivered = sync()
    requested = job.get()
    assert requested.get("state") == "requested"
    assert {item["request_id"] for item in delivered} == {requested.get("frame_request_id"), *queued[1:]}


def test_sync_expires_stale_requests(screen_sync):
    uid, user, job, sync = screen_sync
    stale = enqueue(uid, "stale", now=datetime.now(timezone.utc) - timedelta(days=1), requested_ttl_seconds=60)
    queued = [enqueue(uid, f"pending-{index}") for index in range(FRAME_REQUEST_MAX_PENDING_PER_DEVICE - 1)]

    assert {item["request_id"] for item in sync()} == {job.get().get("frame_request_id"), *queued}
    expired = user.collection("frame_requests").document(stale).get()
    assert expired.get("state") == "pruned"
    assert expired.get("terminal_reason") == "retention_expired"


def test_sync_enqueues_and_delivers_new_keyframe(screen_sync):
    _, _, job, sync = screen_sync

    (item,) = sync()
    requested = job.get()
    assert requested.get("state") == "requested"
    assert item == {
        "request_id": requested.get("frame_request_id"),
        "device_id": DEVICE,
        "account_generation": GENERATION,
        "conversation_id": CONVERSATION,
        "screenshot_id": "42",
        "state": "requested",
        "expires_at": item["expires_at"],
    }
