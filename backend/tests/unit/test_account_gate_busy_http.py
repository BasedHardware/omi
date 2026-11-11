"""Account-gate contention is a 409 with Retry-After, never a 500."""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from database.legal_holds import DestructiveGateTakeover, DestructiveOperationInProgress, LegalHoldAuthorityUnavailable
from utils.other.account_gate_http import (
    ACCOUNT_GATE_BUSY_DETAIL,
    ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS,
    account_gate_busy_http_exception,
)
from utils.stt.outcomes import is_destructive_operation_in_progress
import utils.memory.canonical_memory_adapter as canonical_adapter


def test_account_gate_busy_http_exception_is_409_with_short_retry_after():
    error = account_gate_busy_http_exception()
    assert error.status_code == 409
    assert error.detail == ACCOUNT_GATE_BUSY_DETAIL
    assert error.headers["Retry-After"] == str(ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS)
    assert 1 <= ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS <= 3


def _fence() -> DestructiveOperationInProgress:
    return DestructiveOperationInProgress("canonical mutation blocked by destructive operation")


def _assert_gate_busy(error: HTTPException, fence: DestructiveOperationInProgress) -> None:
    assert error.status_code == 409
    assert error.detail == ACCOUNT_GATE_BUSY_DETAIL
    assert error.headers["Retry-After"] == str(ACCOUNT_GATE_BUSY_RETRY_AFTER_SECONDS)
    assert error.__cause__ is fence
    assert is_destructive_operation_in_progress(error)


def test_canonical_write_maps_destructive_gate_to_account_gate_busy(monkeypatch):
    fence = _fence()
    monkeypatch.setattr(canonical_adapter, "_ensure_control_state", lambda *args, **kwargs: SimpleNamespace())
    monkeypatch.setattr(canonical_adapter, "require_writer_admitted", lambda *args, **kwargs: None)
    write = SimpleNamespace(operation=SimpleNamespace(operation_id="op"), patch_payload={}, evidence=[])
    monkeypatch.setattr(
        canonical_adapter,
        "_canonical_extraction_apply_write",
        lambda *args, **kwargs: (write, "mem-1"),
    )

    def blocked(**kwargs):
        raise fence

    monkeypatch.setattr(canonical_adapter, "apply_long_term_patch_firestore", blocked)

    with pytest.raises(HTTPException) as caught:
        canonical_adapter.write_canonical_extraction_memory("uid", {"content": "hello"}, db_client=object())

    _assert_gate_busy(caught.value, fence)


@pytest.mark.parametrize(
    "error_type", [DestructiveGateTakeover, DestructiveOperationInProgress, LegalHoldAuthorityUnavailable]
)
def test_account_gate_cascade_purge_maps_fence_before_generic_failure(monkeypatch, error_type):
    from utils.memory import memory_service

    fence = error_type("canonical mutation blocked by destructive operation")

    def blocked(*args, **kwargs):
        raise fence

    monkeypatch.setattr(memory_service, "purge_canonical_memory_projections", blocked)
    with pytest.raises(HTTPException) as caught:
        memory_service._purge_required_canonical_projections("uid", ["mem"], db_client=object(), reason="delete")
    assert caught.value.status_code == 409
    assert caught.value.headers["Retry-After"] == "2"
    assert caught.value.__cause__ is fence


@pytest.mark.parametrize(
    "error_type", [DestructiveGateTakeover, DestructiveOperationInProgress, LegalHoldAuthorityUnavailable]
)
def test_account_gate_deletion_boundary_maps_inner_transaction_fence(monkeypatch, error_type):
    from contextlib import nullcontext
    from utils.memory import memory_service

    fence = error_type("canonical mutation blocked by destructive operation")
    monkeypatch.setattr(memory_service, "destructive_operation_gate", lambda *args, **kwargs: nullcontext("token"))

    @memory_service._legal_hold_gated_deletion
    def deletion(self, uid):
        raise fence

    with pytest.raises(HTTPException) as caught:
        deletion(SimpleNamespace(db_client=object()), "uid")
    assert caught.value.status_code == 409
    assert caught.value.headers["Retry-After"] == "2"
    assert caught.value.__cause__ is fence


def test_adapter_projection_loop_aborts_before_next_memory_on_takeover(monkeypatch):
    cleaned = []

    def check(*args, **kwargs):
        if cleaned:
            raise DestructiveGateTakeover("peer completed")

    monkeypatch.setattr(canonical_adapter, "assert_destructive_gate_still_ours", check)
    monkeypatch.setattr(
        canonical_adapter, "_run_immediate_privacy_cleanup", lambda uid, memory_id, **kwargs: cleaned.append(memory_id)
    )
    with pytest.raises(DestructiveGateTakeover):
        canonical_adapter.purge_canonical_memory_projections(
            "uid", ["a", "b"], db_client=object(), reason="delete", revalidate_gate=True
        )
    assert cleaned == ["a"]


@pytest.mark.parametrize("loop", ["tombstone", "retraction"])
def test_adapter_takeover_preserves_marker_without_retry(monkeypatch, loop):
    def check(*args, **kwargs):
        raise DestructiveGateTakeover("peer completed")

    monkeypatch.setattr(canonical_adapter, "assert_destructive_gate_still_ours", check)
    if loop == "tombstone":
        with pytest.raises(DestructiveGateTakeover):
            canonical_adapter._tombstone_memory_items_under_gate("uid", ["a"], db_client=object(), reason="delete")
    else:
        with pytest.raises(DestructiveGateTakeover):
            canonical_adapter._retract_conversation_sourced_memories_under_gate("uid", "conv", db_client=object())


def test_conversation_delete_route_maps_takeover_to_409(monkeypatch):
    from contextlib import nullcontext
    from unittest.mock import MagicMock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    # Earlier modules in this session may have replaced firebase_admin with an
    # AutoMock stub that rejects attribute access; routers.conversations imports
    # utils.notifications, which does `from firebase_admin import messaging, auth`.
    import sys, types as _types

    fb = sys.modules.get("firebase_admin")
    if fb is not None and not hasattr(fb, "messaging"):
        messaging_stub = _types.ModuleType("firebase_admin.messaging")

        class _AnyMeta:
            def __init__(self, *args, **kwargs):
                pass

        for _name in (
            "AndroidConfig",
            "AndroidNotification",
            "APNSConfig",
            "APNSPayload",
            "Aps",
            "ApsAlert",
            "Messaging",
            "MulticastMessage",
            "Notification",
            "TopicMessage",
            "WebpushConfig",
            "WebpushNotification",
            "ConditionMessage",
            "Message",
        ):
            setattr(messaging_stub, _name, _AnyMeta)
        messaging_stub.send = lambda *a, **k: None
        messaging_stub.send_each_for_multicast = lambda *a, **k: None
        fb.messaging = messaging_stub
        if not hasattr(fb, "auth"):
            fb.auth = _types.ModuleType("firebase_admin.auth")
    from routers import conversations as conversation_routes

    service = MagicMock()
    service.retract_conversation_memories.side_effect = DestructiveGateTakeover("peer completed before hold")
    monkeypatch.setattr(conversation_routes, "MemoryService", lambda **kwargs: service)
    monkeypatch.setattr(conversation_routes, 'destructive_operation_gate', lambda *args, **kwargs: nullcontext())
    monkeypatch.setattr(conversation_routes.conversation_tombstones, "record_deletion", lambda *args: None)
    monkeypatch.setattr(conversation_routes, "delete_owner_prompt_embedding_cache", lambda *args: None)
    monkeypatch.setattr(conversation_routes, "retraction_can_be_skipped", lambda *args, **kwargs: False)
    app = FastAPI()
    app.include_router(conversation_routes.router)
    app.dependency_overrides[conversation_routes.auth.get_current_user_uid] = lambda: "uid"
    response = TestClient(app).delete("/v1/conversations/conv?cascade=true")
    assert response.status_code == 409
    assert response.json() == {"detail": "account_gate_busy"}
    assert response.headers["Retry-After"] == "2"


def test_review_resolve_route_maps_takeover_to_409(monkeypatch):
    """A canonical review resolution whose gate revalidation detects a takeover
    surfaces as the retryable account-gate response, never an unhandled 500."""
    from unittest.mock import MagicMock
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from routers import memories as memory_routes

    review_queue_stub = MagicMock()
    review_queue_stub.resolve_review_conflict.side_effect = DestructiveGateTakeover(
        "destructive operation gate was taken over by a same-kind peer"
    )
    monkeypatch.setattr(memory_routes, "review_queue", review_queue_stub)
    app = FastAPI()
    app.include_router(memory_routes.router)
    app.dependency_overrides[memory_routes.auth.get_current_user_uid] = lambda: "uid"
    response = TestClient(app).post("/v3/memories/review-queue/review-1/resolve", json={"decision": "reject"})
    assert response.status_code == 409
    assert response.json() == {"detail": "account_gate_busy"}
    assert response.headers["Retry-After"] == "2"
