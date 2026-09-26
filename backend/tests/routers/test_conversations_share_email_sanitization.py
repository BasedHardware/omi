"""Unit tests for share-email exception detail sanitization in conversations router.

Verifies that AmbiguousDeliveryError, ValueError, and RuntimeError raised during
share email dispatch do not leak internal connection strings, SMTP hostnames,
or internal cluster details to clients.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from routers import conversations


@pytest.fixture
def mock_share_setup(monkeypatch):
    """Setup standard mocks to reach publish_then_send seam."""
    monkeypatch.setattr(
        conversations,
        "_get_valid_conversation_by_id",
        lambda _uid, cid: {"id": cid, "visibility": "private"},
    )
    monkeypatch.setattr(
        conversations.share_email,
        "normalized_recipient_emails",
        lambda _emails: ["recipient@example.com"],
    )
    monkeypatch.setattr(
        conversations.conversations_db,
        "reserve_share_email_recipients",
        lambda _uid, _cid, _req: (["recipient@example.com"], [], False),
    )
    monkeypatch.setattr(
        conversations.share_email,
        "consume_daily_send_quota",
        lambda _uid, _count: True,
    )
    monkeypatch.setattr(
        conversations.conversations_db,
        "release_share_email_recipients",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        conversations.share_email,
        "refund_daily_send_quota",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        conversations.conversations_db,
        "confirm_share_email_recipients",
        lambda *args, **kwargs: None,
    )


def test_share_email_timeout_error_is_masked(mock_share_setup, monkeypatch):
    """AmbiguousDeliveryError must return static 504 without leaking internal SMTP details."""
    leak_text = "smtp connection timed out to mail-gateway-prod.internal.corp:587 (tcp syn retransmits exhausted)"

    def _failing_publish_then_send(*args, **kwargs):
        raise conversations.share_email.AmbiguousDeliveryError(leak_text)

    monkeypatch.setattr(conversations.share_email, "publish_then_send", _failing_publish_then_send)

    req = conversations.SendShareEmailRequest(recipient_emails=["recipient@example.com"])
    with pytest.raises(HTTPException) as exc_info:
        conversations.send_conversation_share_email("conv-123", req, uid="user-456")

    assert exc_info.value.status_code == 504
    assert exc_info.value.detail == "The share operation timed out. Please try again."
    assert "mail-gateway-prod" not in exc_info.value.detail
    assert "587" not in exc_info.value.detail
    assert "retransmits" not in exc_info.value.detail


def test_share_email_validation_error_is_masked(mock_share_setup, monkeypatch):
    """ValueError during dispatch must return static 503 without internal schema details."""
    leak_text = "corrupt recipient queue segment in redis db index 3"

    def _failing_publish_then_send(*args, **kwargs):
        raise ValueError(leak_text)

    monkeypatch.setattr(conversations.share_email, "publish_then_send", _failing_publish_then_send)

    req = conversations.SendShareEmailRequest(recipient_emails=["recipient@example.com"])
    with pytest.raises(HTTPException) as exc_info:
        conversations.send_conversation_share_email("conv-123", req, uid="user-456")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Share failed due to invalid data. Please try again."
    assert "redis db index 3" not in exc_info.value.detail


def test_share_email_runtime_error_is_masked(mock_share_setup, monkeypatch):
    """RuntimeError during dispatch must return static 502 without cluster/worker details."""
    leak_text = "failed reservation lock on worker-node-42.cluster.internal:6379"

    def _failing_publish_then_send(*args, **kwargs):
        raise RuntimeError(leak_text)

    monkeypatch.setattr(conversations.share_email, "publish_then_send", _failing_publish_then_send)

    req = conversations.SendShareEmailRequest(recipient_emails=["recipient@example.com"])
    with pytest.raises(HTTPException) as exc_info:
        conversations.send_conversation_share_email("conv-123", req, uid="user-456")

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == "Share service temporarily unavailable. Please try again."
    assert "worker-node-42" not in exc_info.value.detail
    assert "6379" not in exc_info.value.detail
