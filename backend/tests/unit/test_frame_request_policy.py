from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from models.frame_request import FrameRequest, FrameRequestState
from utils.retrieval.frame_request_policy import (
    FRAME_REQUEST_MAX_TTL_SECONDS,
    canonical_dedupe_key,
    check_device_quota,
    conversation_lifetime_expiry,
    explicit_frame_requests_enabled,
    is_expired,
    request_expiry,
    validate_transition,
)

NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def _request(**updates) -> FrameRequest:
    values = {
        "request_id": "frame-1",
        "uid": "uid-1",
        "device_id": "mac-1",
        "account_generation": 3,
        "dedupe_key": "dedupe-1",
        "state": FrameRequestState.requested,
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
    }
    values.update(updates)
    return FrameRequest.model_validate(values)


def test_frame_request_gate_requires_authenticated_request_decision():
    assert explicit_frame_requests_enabled(None) is False
    assert explicit_frame_requests_enabled({"uid": "", "frame_requests_enabled": True}) is False
    assert explicit_frame_requests_enabled({"uid": "uid-1", "frame_requests_enabled": "true"}) is False
    assert explicit_frame_requests_enabled({"uid": "uid-1", "frame_requests_enabled": True}) is True


def test_expiry_is_capped_by_product_and_shorter_device_retention():
    expiry = request_expiry(
        created_at=NOW,
        requested_ttl_seconds=FRAME_REQUEST_MAX_TTL_SECONDS * 2,
        device_retention_seconds=900,
    )
    assert expiry == NOW + timedelta(seconds=900)


def test_conversation_evidence_uses_creation_sentinel_not_time_based_ttl():
    request = _request(
        conversation_id="conversation-1",
        state=FrameRequestState.attached,
        expires_at=conversation_lifetime_expiry(NOW),
    )
    assert request.expires_at == request.created_at
    assert is_expired(request, now=NOW + timedelta(days=3650)) is False


def test_conversation_bound_request_is_temporary_until_upload_and_attach():
    request = _request(conversation_id="conversation-1", expires_at=NOW + timedelta(hours=1))
    assert is_expired(request, now=NOW + timedelta(hours=2)) is True


def test_unattached_requested_frame_expires_and_cannot_be_reused():
    request = _request(expires_at=NOW + timedelta(seconds=10))
    assert is_expired(request, now=NOW + timedelta(seconds=10)) is True
    with pytest.raises(ValueError, match="expired"):
        validate_transition(
            request,
            next_state=FrameRequestState.claimed,
            uid="uid-1",
            device_id="mac-1",
            account_generation=3,
            now=NOW + timedelta(seconds=10),
        )


def test_transition_fences_owner_device_and_account_generation():
    with pytest.raises(PermissionError, match="mismatch"):
        validate_transition(
            _request(),
            next_state=FrameRequestState.claimed,
            uid="uid-1",
            device_id="other-device",
            account_generation=3,
            now=NOW,
        )
    with pytest.raises(PermissionError, match="mismatch"):
        validate_transition(
            _request(),
            next_state=FrameRequestState.claimed,
            uid="uid-1",
            device_id="mac-1",
            account_generation=4,
            now=NOW,
        )


@pytest.mark.parametrize("state", [FrameRequestState.offline, FrameRequestState.pruned, FrameRequestState.failed])
def test_offline_and_pruned_are_terminal(state):
    request = _request()
    validate_transition(
        request,
        next_state=state,
        uid="uid-1",
        device_id="mac-1",
        account_generation=3,
        now=NOW,
    )
    terminal = _request(state=state, terminal_reason="device_offline")
    with pytest.raises(ValueError, match="already terminal"):
        validate_transition(
            terminal,
            next_state=FrameRequestState.claimed,
            uid="uid-1",
            device_id="mac-1",
            account_generation=3,
            now=NOW,
        )


def test_upload_then_attach_is_the_only_path_to_permanent_evidence():
    request = _request(state=FrameRequestState.claimed)
    validate_transition(
        request,
        next_state=FrameRequestState.uploaded,
        uid="uid-1",
        device_id="mac-1",
        account_generation=3,
        now=NOW,
    )
    with pytest.raises(ValueError, match="conversation"):
        validate_transition(
            _request(state=FrameRequestState.uploaded, storage_id="frame-storage-1"),
            next_state=FrameRequestState.attached,
            uid="uid-1",
            device_id="mac-1",
            account_generation=3,
            now=NOW,
        )


def test_quota_counts_only_live_owner_device_requests():
    requests = [_request(request_id=f"frame-{i}", byte_count=1) for i in range(8)]
    decision = check_device_quota(requests, uid="uid-1", device_id="mac-1", now=NOW)
    assert decision.allowed is False
    assert decision.reason == "pending_count"
    assert (
        check_device_quota([_request(uid="other", request_id="other")], uid="uid-1", device_id="mac-1", now=NOW).allowed
        is True
    )


def test_quota_ignores_terminal_and_expired_rows():
    requests = [
        _request(state=FrameRequestState.failed, terminal_reason="device_error", byte_count=10**7),
        _request(
            created_at=NOW - timedelta(seconds=2),
            expires_at=NOW - timedelta(seconds=1),
            byte_count=10**7,
        ),
    ]
    decision = check_device_quota(requests, uid="uid-1", device_id="mac-1", now=NOW)
    assert decision.allowed is True
    assert decision.pending_count == 0
    assert decision.pending_bytes == 0


def test_dedupe_key_is_stable_and_does_not_expose_input():
    first = canonical_dedupe_key(
        uid="uid-1", device_id="mac-1", screenshot_id="42", conversation_id=None, intent_key="look-at-frame"
    )
    second = canonical_dedupe_key(
        uid="uid-1", device_id="mac-1", screenshot_id="42", conversation_id=None, intent_key="look-at-frame"
    )
    assert first == second
    assert len(first) == 64
    assert "look-at-frame" not in first


@pytest.mark.parametrize(
    "payload",
    [
        {"state": "attached", "conversation_id": None, "expires_at": NOW},
        {"state": "uploaded", "storage_id": None},
        {"state": "failed", "terminal_reason": None},
    ],
)
def test_model_rejects_unowned_or_unexplainable_terminal_rows(payload):
    values = {
        "request_id": "frame-1",
        "uid": "uid-1",
        "device_id": "mac-1",
        "dedupe_key": "d-1",
        "created_at": NOW,
        "expires_at": NOW + timedelta(hours=1),
    }
    values.update(payload)
    with pytest.raises(ValidationError):
        FrameRequest.model_validate(values)


def test_model_rejects_request_ids_that_escape_the_queue_collection():
    with pytest.raises(ValidationError, match="path segment"):
        _request(request_id="frame/nested")
