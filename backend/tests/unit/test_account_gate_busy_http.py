"""Account-gate contention is a 409 with Retry-After, never a 500."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from database.legal_holds import DestructiveOperationInProgress, LegalHoldAuthorityUnavailable
from models.feedback import MemoryUseFeedback
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


def test_memory_use_replay_maps_destructive_gate_to_account_gate_busy(monkeypatch):
    fence = _fence()

    def blocked(*args, **kwargs):
        raise fence

    monkeypatch.setattr(canonical_adapter, "read_memory_use_feedback_replay", blocked)
    feedback = MemoryUseFeedback(
        uid="uid",
        feedback_id="use-1",
        target_memory_id="mem",
        action="suppress",
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(HTTPException) as caught:
        canonical_adapter._apply_canonical_user_mutation(
            "uid",
            "mem",
            mutation_kind="memory_use",
            build_patch=lambda item, now: None,
            memory_use_feedback=feedback,
            db_client=object(),
        )

    _assert_gate_busy(caught.value, fence)


@pytest.mark.parametrize("error_type", [DestructiveOperationInProgress, LegalHoldAuthorityUnavailable])
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


@pytest.mark.parametrize("error_type", [DestructiveOperationInProgress, LegalHoldAuthorityUnavailable])
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
