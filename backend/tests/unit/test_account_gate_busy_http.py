"""Account-gate contention is a 409 with Retry-After, never a 500."""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from database.legal_holds import DestructiveOperationInProgress
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
