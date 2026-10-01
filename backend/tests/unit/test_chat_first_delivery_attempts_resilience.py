"""Hermetic resilience unit tests for backend/database/chat_first_delivery_attempts.py."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import GoogleAPICallError

import database.chat_first_delivery_attempts as delivery_attempts_db
from database.chat_first_delivery_attempts import (
    ChatFirstMalformedDeliveryAttempt,
    DEFAULT_REPAIR_LIMIT,
    MAX_ID_LENGTH,
    MAX_REPAIR_LIMIT,
    TRANSIENT_DEAD_LETTER_REPAIR_AGE,
    _clean_id,
    _ensure_utc,
    _resolve_client,
    dead_letter_payload,
    dead_letter_ref,
    delivery_attempt_ref,
    intent_ref,
    move_to_dead_letters,
    repair_transient_dead_letters,
    requeue_transient_dead_letter,
    reset_malformed_delivery_attempt,
    user_ref,
    valid_attempt_value,
)
from models.chat_first import DeadLetteredProactiveIntent, ProactiveIntent


def _make_dummy_intent(
    intent_id: str = "intent_123",
    account_generation: int = 1,
    delivery_state: str = "dead_letter",
    dead_letter_reason: str = "unacknowledged_after_fetch_budget",
    requeue_count: int = 0,
    terminal_at: Optional[datetime] = None,
) -> Dict[str, Any]:
    now = terminal_at or (datetime.now(timezone.utc) - timedelta(hours=8))
    return {
        "intent_id": intent_id,
        "continuity_key": "cont_123",
        "account_generation": account_generation,
        "source": "cold_start_rich",
        "blocks": [{"type": "taskCard", "task_id": "task_123"}],
        "delivery_state": delivery_state,
        "dead_letter_reason": dead_letter_reason,
        "requeue_count": requeue_count,
        "created_at": now - timedelta(hours=1),
        "last_fetched_at": now,
        "last_rejection_at": now,
    }


def test_clean_id_validates_and_sanitizes():
    assert _clean_id("user-123") == "user-123"
    assert _clean_id("  intent_abc-456  ") == "intent_abc-456"
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id(None) == ""
    assert _clean_id(12345) == ""  # type: ignore[arg-type]

    # Path traversal and injection defense
    assert _clean_id("../traversal") == ""
    assert _clean_id("dir/intent") == ""
    assert _clean_id("dir\\intent") == ""
    assert _clean_id("intent\x00null") == ""
    assert _clean_id("a" * (MAX_ID_LENGTH + 1)) == ""
    assert _clean_id("a" * MAX_ID_LENGTH) == "a" * MAX_ID_LENGTH


def test_ensure_utc_normalizes_naive_and_aware():
    now_naive = datetime(2026, 9, 30, 8, 0, 0)
    utc_aware = _ensure_utc(now_naive)
    assert utc_aware is not None
    assert utc_aware.tzinfo == timezone.utc

    now_aware = datetime(2026, 9, 30, 8, 0, 0, tzinfo=timezone.utc)
    assert _ensure_utc(now_aware) == now_aware
    assert _ensure_utc(None) is None
    assert _ensure_utc("not-a-datetime") is None


def test_user_ref_validation_and_di():
    mock_client = MagicMock()
    ref = user_ref("valid-user", firestore_client=mock_client)
    mock_client.collection.assert_called_with("users")
    mock_client.collection.return_value.document.assert_called_with("valid-user")

    with pytest.raises(ValueError, match="Invalid or missing uid"):
        user_ref("", firestore_client=mock_client)
    with pytest.raises(ValueError, match="Invalid or missing uid"):
        user_ref("../bad-user", firestore_client=mock_client)
    with pytest.raises(ValueError, match="Invalid or missing uid"):
        user_ref("bad/user", firestore_client=mock_client)


def test_intent_refs_validation():
    mock_client = MagicMock()
    for fn in [intent_ref, delivery_attempt_ref, dead_letter_ref]:
        ref = fn("valid-uid", "valid-intent", firestore_client=mock_client)
        assert ref is not None

        with pytest.raises(ValueError, match="Invalid or missing intent_id"):
            fn("valid-uid", "", firestore_client=mock_client)
        with pytest.raises(ValueError, match="Invalid or missing intent_id"):
            fn("valid-uid", "../traversal", firestore_client=mock_client)
        with pytest.raises(ValueError, match="Invalid or missing intent_id"):
            fn("valid-uid", "path/intent", firestore_client=mock_client)


def test_valid_attempt_value():
    dummy_intent = MagicMock()
    assert valid_attempt_value(dummy_intent, "fetch_count", 5) is True
    assert valid_attempt_value(dummy_intent, "fetch_count", -1) is False
    assert valid_attempt_value(dummy_intent, "requeue_count", 1) is True
    assert valid_attempt_value(dummy_intent, "requeue_count", 2) is False
    assert valid_attempt_value(dummy_intent, "last_rejection_code", "valid_code_123") is True
    assert valid_attempt_value(dummy_intent, "last_rejection_code", "INVALID UPPER") is False


def test_reset_malformed_delivery_attempt_and_timezone_safety():
    dummy_intent = MagicMock()
    now_naive = datetime(2026, 9, 30, 8, 0, 0)
    raw = {
        "requeue_count": 1,
        "fetch_count": 3,
        "materialization_attempts": 2,
        "last_rejection_code": "code_ok",
    }
    reset = reset_malformed_delivery_attempt(dummy_intent, raw, now=now_naive)
    assert reset["requeue_count"] == 1
    assert reset["fetch_count"] == 4
    assert reset["last_fetched_at"].tzinfo == timezone.utc
    assert reset["materialization_attempts"] == 2
    assert reset["last_rejection_code"] == "code_ok"


def test_dead_letter_payload_populates_last_fetched_at():
    data = _make_dummy_intent(terminal_at=datetime(2026, 9, 30, 0, 0, 0, tzinfo=timezone.utc))
    data["last_fetched_at"] = None
    intent = DeadLetteredProactiveIntent.model_validate(data)

    terminal_at = datetime(2026, 9, 30, 8, 0, 0, tzinfo=timezone.utc)
    payload = dead_letter_payload(intent, terminal_at=terminal_at)
    assert payload["last_fetched_at"] == terminal_at


def test_move_to_dead_letters():
    mock_txn = MagicMock()
    mock_intent_ref = MagicMock()
    mock_dead_ref = MagicMock()

    data = _make_dummy_intent()
    intent = DeadLetteredProactiveIntent.model_validate(data)
    now = datetime.now(timezone.utc)

    move_to_dead_letters(
        mock_txn,
        intent_ref_value=mock_intent_ref,
        dead_letter_ref_value=mock_dead_ref,
        intent=intent,
        terminal_at=now,
    )
    mock_txn.set.assert_called_once()
    mock_txn.delete.assert_called_once_with(mock_intent_ref)


def test_requeue_transient_dead_letter_missing_document():
    mock_client = MagicMock()
    dead_doc = MagicMock(exists=False)
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        dead_doc
    )

    res = requeue_transient_dead_letter(
        "u1",
        "intent_1",
        account_generation=1,
        now=datetime.now(timezone.utc),
        firestore_client=mock_client,
    )
    assert res is None


def test_requeue_transient_dead_letter_ineligible_conditions():
    mock_client = MagicMock()
    now = datetime.now(timezone.utc)

    # 1. account_generation mismatch
    data = _make_dummy_intent(account_generation=2)
    mock_doc = MagicMock(exists=True)
    mock_doc.to_dict.return_value = data
    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        mock_doc
    )

    res = requeue_transient_dead_letter("u1", "intent_1", account_generation=1, now=now, firestore_client=mock_client)
    assert res is None

    # 2. Requeue count already spent (> 0)
    data_requeued = _make_dummy_intent(account_generation=1, requeue_count=1)
    mock_doc.to_dict.return_value = data_requeued
    res = requeue_transient_dead_letter("u1", "intent_1", account_generation=1, now=now, firestore_client=mock_client)
    assert res is None

    # 3. Not enough age elapsed (less than 6 hours)
    recent_terminal = now - timedelta(hours=1)
    data_recent = _make_dummy_intent(account_generation=1, requeue_count=0, terminal_at=recent_terminal)
    mock_doc.to_dict.return_value = data_recent
    res = requeue_transient_dead_letter("u1", "intent_1", account_generation=1, now=now, firestore_client=mock_client)
    assert res is None


def test_repair_transient_dead_letters_limit_clamping():
    mock_client = MagicMock()
    mock_query = MagicMock()
    mock_query.stream.return_value = []
    mock_client.collection.return_value.document.return_value.collection.return_value.where.return_value.order_by.return_value.limit.return_value = (
        mock_query
    )

    # Negative limit clamped to 1 (query limit 2 * 1 = 2)
    failed = repair_transient_dead_letters(
        "u1",
        account_generation=1,
        limit=-5,
        now=datetime.now(timezone.utc),
        firestore_client=mock_client,
    )
    assert failed is False

    # Excessive limit clamped to MAX_REPAIR_LIMIT (1000, query limit 2 * 1000 = 2000)
    failed_excessive = repair_transient_dead_letters(
        "u1",
        account_generation=1,
        limit=999999,
        now=datetime.now(timezone.utc),
        firestore_client=mock_client,
    )
    assert failed_excessive is False


def test_repair_transient_dead_letters_handles_google_api_call_error():
    mock_client = MagicMock()
    mock_col = MagicMock()
    mock_col.where.return_value = mock_col
    mock_col.order_by.return_value = mock_col
    mock_col.limit.return_value = mock_col
    mock_col.stream.side_effect = GoogleAPICallError("Firestore transport closed")
    mock_client.collection.return_value.document.return_value.collection.return_value = mock_col

    failed = repair_transient_dead_letters(
        "u1",
        account_generation=1,
        limit=10,
        now=datetime.now(timezone.utc),
        firestore_client=mock_client,
    )
    # Catches GoogleAPICallError during stream and returns True without crashing
    assert failed is True


def test_repair_transient_dead_letters_propagates_invalid_uid_programming_error():
    mock_client = MagicMock()

    # Malformed uid raises ValueError immediately rather than returning True as a serving query failure
    with pytest.raises(ValueError, match="Invalid or missing uid"):
        repair_transient_dead_letters(
            "../bad-user",
            account_generation=1,
            limit=10,
            now=datetime.now(timezone.utc),
            firestore_client=mock_client,
        )


def test_requeue_transient_dead_letter_propagates_transactional_exceptions():
    mock_client = MagicMock()
    mock_txn = MagicMock()
    mock_client.transaction.return_value = mock_txn

    mock_dead_ref = MagicMock()
    mock_dead_ref.get.side_effect = RuntimeError("Contention retry limit exhausted")

    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value = (
        mock_dead_ref
    )

    # Must propagate the exception rather than falling back to raw client
    with pytest.raises(RuntimeError, match="Contention retry limit exhausted"):
        requeue_transient_dead_letter(
            "u1",
            "intent_1",
            account_generation=1,
            now=datetime.now(timezone.utc),
            firestore_client=mock_client,
        )


def test_requeue_transient_dead_letter_propagates_malformed_document_error():
    mock_client = MagicMock()
    mock_txn = MagicMock()
    mock_client.transaction.return_value = mock_txn

    mock_doc = MagicMock(exists=True)
    mock_doc.to_dict.return_value = {"invalid": "missing_required_fields"}

    mock_client.collection.return_value.document.return_value.collection.return_value.document.return_value.get.return_value = (
        mock_doc
    )

    with pytest.raises(ChatFirstMalformedDeliveryAttempt):
        requeue_transient_dead_letter(
            "u1",
            "intent_1",
            account_generation=1,
            now=datetime.now(timezone.utc),
            firestore_client=mock_client,
        )


def test_repair_transient_dead_letters_requeues_eligible_snapshots():
    mock_client = MagicMock()
    now = datetime.now(timezone.utc)
    old_time = now - timedelta(hours=10)

    snap1 = MagicMock(id="intent_1")
    snap1.to_dict.return_value = {"last_rejection_at": old_time}

    snap2 = MagicMock(id="intent_2")
    snap2.to_dict.return_value = {"last_rejection_at": now - timedelta(minutes=5)}  # too recent

    mock_stream = [snap1, snap2]
    mock_collection = MagicMock()
    mock_collection.where.return_value = mock_collection
    mock_collection.order_by.return_value = mock_collection
    mock_collection.limit.return_value.stream.return_value = mock_stream

    mock_client.collection.return_value.document.return_value.collection.return_value = mock_collection

    mock_requeue = MagicMock(return_value=MagicMock())

    failed = repair_transient_dead_letters(
        "u1",
        account_generation=1,
        limit=5,
        now=now,
        firestore_client=mock_client,
        requeue=mock_requeue,
    )
    assert failed is False
    mock_requeue.assert_called_once_with(
        "u1",
        "intent_1",
        account_generation=1,
        now=now,
        firestore_client=mock_client,
    )
