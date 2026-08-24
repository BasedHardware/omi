from datetime import datetime, timezone

import pytest

from models.frame_request import FrameRequest, FrameRequestCleanupState, FrameRequestPromotion, FrameRequestState
from routers import frame_requests
from utils.retrieval import frame_request_authority


def _request(state: FrameRequestState) -> FrameRequest:
    now = datetime(2026, 8, 24, tzinfo=timezone.utc)
    return FrameRequest(
        request_id="frame-1",
        uid="user-1",
        device_id="desktop-1",
        account_generation=3,
        dedupe_key="opaque",
        conversation_id="conversation-1",
        screenshot_id="42",
        state=state,
        created_at=now,
        expires_at=now if state == FrameRequestState.attached else now.replace(day=25),
        storage_id="storage-1",
        byte_count=1024,
        content_type="image/jpeg",
        cleanup_state=(
            FrameRequestCleanupState.permanent
            if state == FrameRequestState.attached
            else FrameRequestCleanupState.pending
        ),
    )


@pytest.mark.asyncio
async def test_attached_retry_is_idempotent_and_never_cleans_permanent_evidence(monkeypatch):
    request = _request(FrameRequestState.attached)
    monkeypatch.setattr(frame_requests, "_authorize", lambda uid, generation: None)
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda uid, request_id: request)
    monkeypatch.setattr(
        frame_requests,
        "delete_frame_request_pixels",
        lambda *args: pytest.fail("permanent pixels must not be deleted on retry"),
    )
    monkeypatch.setattr(
        frame_requests.conversations_db,
        "delete_conversation_photo",
        lambda *args: pytest.fail("permanent metadata must not be deleted on retry"),
    )

    result = await frame_requests.promote_frame_request(
        "frame-1",
        FrameRequestPromotion(device_id="desktop-1", account_generation=3, conversation_id="conversation-1"),
        uid="user-1",
    )

    assert result.request.state == FrameRequestState.attached


@pytest.mark.asyncio
async def test_ambiguous_state_commit_leaves_object_retryable(monkeypatch):
    request = _request(FrameRequestState.uploaded)
    monkeypatch.setattr(frame_requests, "_authorize", lambda uid, generation: None)
    monkeypatch.setattr(frame_requests, "get_frame_request", lambda uid, request_id: request)
    monkeypatch.setattr(frame_requests, "list_attached_frame_requests", lambda *args: [])
    monkeypatch.setattr(frame_requests.conversations_db, "store_conversation_photos", lambda *args: True)
    monkeypatch.setattr(
        frame_requests,
        "transition_frame_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("commit outcome unknown")),
    )
    monkeypatch.setattr(
        frame_requests,
        "delete_frame_request_pixels",
        lambda *args: pytest.fail("ambiguous commit must not delete the object"),
    )

    with pytest.raises(RuntimeError, match="commit outcome unknown"):
        await frame_requests.promote_frame_request(
            "frame-1",
            FrameRequestPromotion(device_id="desktop-1", account_generation=3, conversation_id="conversation-1"),
            uid="user-1",
        )


def test_posthog_authority_requires_cohort_and_independent_kill_switch(monkeypatch):
    class FakePostHog:
        def __init__(self):
            self.values = {"cohort": True, "kill": False}

        def get_feature_flag(self, name, uid):
            return self.values[name]

    fake = FakePostHog()
    monkeypatch.setattr(frame_request_authority, "get_posthog_client_for_decisions", lambda: fake)
    monkeypatch.setattr(
        frame_request_authority,
        "get_account_cutover_record",
        lambda uid: type("Record", (), {"account_generation": 9})(),
    )
    authority = frame_request_authority.PostHogFrameRequestAuthority(cohort_flag="cohort", kill_switch_flag="kill")

    enabled = authority.decide("user-1")
    assert enabled.enabled is True and enabled.account_generation == 9

    fake.values["kill"] = True
    killed = authority.decide("user-1")
    assert killed.enabled is False and killed.kill_switch is True
