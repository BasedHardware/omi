from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import MagicMock
import pytest
from google.api_core.exceptions import GoogleAPICallError

import database.chat_first_delivery_attempts as delivery_attempts_db
from database.chat_first_delivery_attempts import (
    DEFAULT_REPAIR_LIMIT,
    MAX_ID_LENGTH,
    MAX_REPAIR_LIMIT,
    TRANSIENT_DEAD_LETTER_REPAIR_AGE,
    _clean_id,
    _ensure_utc,
    _resolve_client,
    dead_letter_ref,
    delivery_attempt_ref,
    intent_ref,
    repair_transient_dead_letters,
    requeue_transient_dead_letter,
    user_ref,
)


def test_clean_id_resilience():
    assert _clean_id("valid_uid_123") == "valid_uid_123"
    assert _clean_id("  user_with_spaces  ") == "user_with_spaces"
    assert _clean_id("") == ""
    assert _clean_id("   ") == ""
    assert _clean_id(None) == ""
    assert _clean_id(12345) == ""
    assert _clean_id("../path_traversal") == ""
    assert _clean_id("nested/path") == ""
    assert _clean_id("nested\\path") == ""
    assert _clean_id("null\x00byte") == ""
    assert _clean_id("a" * (MAX_ID_LENGTH + 1)) == ""
    assert _clean_id("a" * MAX_ID_LENGTH) == "a" * MAX_ID_LENGTH


def test_ensure_utc_resilience():
    assert _ensure_utc(None) is None
    assert _ensure_utc("not-a-datetime") is None

    naive = datetime(2026, 10, 29, 12, 0, 0)
    aware_utc = _ensure_utc(naive)
    assert aware_utc is not None
    assert aware_utc.tzinfo == timezone.utc

    aware = datetime(2026, 10, 29, 12, 0, 0, tzinfo=timezone.utc)
    assert _ensure_utc(aware) == aware


def test_refs_reject_invalid_ids():
    mock_client = MagicMock()

    with pytest.raises(ValueError, match="Invalid user ID"):
        user_ref("../traversal", firestore_client=mock_client)

    with pytest.raises(ValueError, match="Invalid intent ID"):
        intent_ref("valid_user", "../traversal", firestore_client=mock_client)

    with pytest.raises(ValueError, match="Invalid intent ID"):
        delivery_attempt_ref("valid_user", "bad/intent", firestore_client=mock_client)

    with pytest.raises(ValueError, match="Invalid intent ID"):
        dead_letter_ref("valid_user", "intent\x00null", firestore_client=mock_client)


def test_requeue_transient_dead_letter_invalid_inputs():
    mock_client = MagicMock()
    now = datetime.now(timezone.utc)

    # Empty / traversal uid or intent_id returns None safely
    assert (
        requeue_transient_dead_letter(
            "",
            "intent_1",
            account_generation=1,
            now=now,
            firestore_client=mock_client,
        )
        is None
    )
    assert (
        requeue_transient_dead_letter(
            "user_1",
            "../bad_intent",
            account_generation=1,
            now=now,
            firestore_client=mock_client,
        )
        is None
    )


def test_repair_transient_dead_letters_limit_clamping_and_invalid_uid():
    mock_client = MagicMock()
    now = datetime.now(timezone.utc)

    # Invalid uid returns True (handled error)
    assert (
        repair_transient_dead_letters(
            "../bad_uid",
            account_generation=1,
            limit=10,
            now=now,
            firestore_client=mock_client,
        )
        is True
    )


def test_repair_transient_dead_letters_catches_general_exception():
    mock_client = MagicMock()
    now = datetime.now(timezone.utc)

    # Mock user_ref / collection to raise an unexpected runtime error
    mock_client.collection.side_effect = RuntimeError("Simulated network dropout")

    # Should catch the error, log, and return True without crashing caller
    res = repair_transient_dead_letters(
        "user_123",
        account_generation=1,
        limit=10,
        now=now,
        firestore_client=mock_client,
    )
    assert res is True
