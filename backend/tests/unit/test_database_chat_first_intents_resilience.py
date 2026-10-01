"""Unit tests verifying defensive boundary guards in chat_first_intents."""

from datetime import datetime, timezone
import pytest

from database.chat_first_intents import (
    fetch_ready_intent_batch,
    fetch_ready_intents,
    release_due_deferrals,
)


def test_fetch_ready_intent_batch_rejects_empty_uid():
    """Verify fetch_ready_intent_batch strictly rejects empty or non-string uid."""
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        fetch_ready_intent_batch("", account_generation=1)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        fetch_ready_intent_batch("   ", account_generation=1)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        fetch_ready_intent_batch(None, account_generation=1)  # type: ignore[arg-type]


def test_fetch_ready_intent_batch_rejects_invalid_generation():
    """Verify fetch_ready_intent_batch rejects boolean or negative account_generation."""
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        fetch_ready_intent_batch("user_123", account_generation=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        fetch_ready_intent_batch("user_123", account_generation=-1)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        fetch_ready_intent_batch("user_123", account_generation="1")  # type: ignore[arg-type]


def test_fetch_ready_intent_batch_rejects_invalid_now_type():
    """Verify fetch_ready_intent_batch rejects non-datetime now argument."""
    with pytest.raises(ValueError, match="now must be a datetime"):
        fetch_ready_intent_batch("user_123", account_generation=1, now="2026-09-30")  # type: ignore[arg-type]


def test_release_due_deferrals_rejects_empty_uid_and_invalid_generation():
    """Verify release_due_deferrals validates uid and generation boundaries."""
    now = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="uid must be a non-empty string"):
        release_due_deferrals("", account_generation=1, now=now)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        release_due_deferrals("user_123", account_generation=-1, now=now)
    with pytest.raises(ValueError, match="account_generation must be a non-negative integer"):
        release_due_deferrals("user_123", account_generation=True, now=now)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="now must be a datetime"):
        release_due_deferrals("user_123", account_generation=1, now="not-a-dt")  # type: ignore[arg-type]
