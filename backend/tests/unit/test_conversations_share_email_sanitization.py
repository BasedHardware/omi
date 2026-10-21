"""Unit tests verifying error message sanitization for conversation share-email route.

Guards against internal infrastructure leakage (issue #18783):
- AmbiguousDeliveryError maps to HTTP 504 with generic pending confirmation message.
- ValueError maps to HTTP 503 with generic invalid recipient/configuration message.
- RuntimeError maps to HTTP 502 with generic service temporarily unavailable message.
- Asserts internal transport / secret exception details never leak to client responses.
- Asserts ledger confirmations, reservation releases, and quota refunds remain intact.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from routers import conversations as conversations_router
from utils.conversations.share_email import AmbiguousDeliveryError

UID = "uid-sanitization-test"
CONV_ID = "conv-sanitization-1"


def _sample_conversation() -> dict:
    return {
        "id": CONV_ID,
        "visibility": "private",
        "structured": {"title": "Design Review", "overview": "Sprint Notes"},
        "external_data": {
            "calendar_meeting_context": {
                "calendar_event_id": "evt-sanitization-1",
                "title": "Design Review",
                "calendar_source": "google_calendar",
                "participants": [
                    {"name": "Owner User", "email": "owner@acme.com"},
                    {"name": "Alice Partner", "email": "alice@partner.com"},
                ],
            }
        },
    }


def _create_test_client() -> TestClient:
    app = FastAPI()
    app.include_router(conversations_router.router)
    app.dependency_overrides[conversations_router.auth.get_current_user_uid] = lambda: (
        UID
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _stub_share_email_data_layer(monkeypatch):
    state = {
        "visibility": "private",
        "doc_token": "token-1",
        "redis": set(),
        "in_flight": [],
        "sent": [],
        "refunds": [],
        "releases": [],
        "confirmations": [],
    }

    monkeypatch.setattr(
        conversations_router,
        "_get_valid_conversation_by_id",
        lambda uid, cid, **kw: (
            _sample_conversation() | {"visibility": state["visibility"]}
        ),
    )
    monkeypatch.setattr(
        conversations_router.share_email,
        "get_user_from_uid",
        lambda uid: {
            "uid": uid,
            "email": "owner@acme.com",
            "display_name": "Owner User",
        },
    )
    monkeypatch.setattr(
        conversations_router.conversations_db,
        "set_conversation_visibility",
        lambda uid, cid, value: state.__setitem__(
            "visibility", getattr(value, "value", value)
        ),
    )

    def conditional_publish(uid, cid):
        if state["visibility"] in ("shared", "public"):
            return False, None
        state["visibility"] = "shared"
        state["doc_token"] = "token-1"
        return True, "token-1"

    monkeypatch.setattr(
        conversations_router.conversations_db,
        "publish_conversation_visibility_if_private",
        conditional_publish,
    )

    def guarded_set(uid, cid, value, last_update_time):
        if last_update_time != state["doc_token"]:
            return False
        state["visibility"] = getattr(value, "value", value)
        return True

    monkeypatch.setattr(
        conversations_router.conversations_db,
        "set_conversation_visibility_if_unchanged",
        guarded_set,
    )

    monkeypatch.setattr(
        conversations_router.share_email,
        "consume_daily_send_quota",
        lambda uid, n: True,
    )
    monkeypatch.setattr(
        conversations_router.share_email,
        "refund_daily_send_quota",
        lambda uid, n: state["refunds"].append((uid, n)),
    )

    def reserve(uid, cid, emails):
        to_dispatch, already_sent, in_flight_elsewhere = [], [], []
        for email in emails:
            if email in state["sent"]:
                already_sent.append(email)
            elif email in state["in_flight"]:
                in_flight_elsewhere.append(email)
            else:
                to_dispatch.append(email)
                state["in_flight"].append(email)
        return to_dispatch, already_sent, in_flight_elsewhere

    monkeypatch.setattr(
        conversations_router.conversations_db, "reserve_share_email_recipients", reserve
    )

    def confirm(uid, cid, emails):
        state["confirmations"].append((uid, cid, list(emails)))
        for email in emails:
            if email in state["in_flight"]:
                state["in_flight"].remove(email)
            if email not in state["sent"]:
                state["sent"].append(email)

    monkeypatch.setattr(
        conversations_router.conversations_db, "confirm_share_email_recipients", confirm
    )

    def release(uid, cid, emails):
        state["releases"].append((uid, cid, list(emails)))
        for email in emails:
            if email in state["in_flight"]:
                state["in_flight"].remove(email)

    monkeypatch.setattr(
        conversations_router.conversations_db, "release_share_email_recipients", release
    )

    monkeypatch.setattr(
        conversations_router.redis_db,
        "store_conversation_to_uid",
        lambda cid, uid: state["redis"].add(cid),
    )
    monkeypatch.setattr(
        conversations_router.redis_db,
        "add_public_conversation",
        lambda cid: state["redis"].add(f"pub:{cid}"),
    )
    monkeypatch.setattr(
        conversations_router.redis_db,
        "remove_conversation_to_uid",
        lambda cid: state["redis"].discard(cid),
    )
    monkeypatch.setattr(
        conversations_router.redis_db,
        "remove_public_conversation",
        lambda cid: state["redis"].discard(f"pub:{cid}"),
    )
    monkeypatch.setattr(
        conversations_router, "emit_posthog_event", lambda *args, **kwargs: None
    )

    yield state


def test_ambiguous_delivery_sanitizes_error_message(
    monkeypatch, _stub_share_email_data_layer, caplog
):
    """HTTP 504 on AmbiguousDeliveryError returns sanitized user-facing detail and confirms ledger."""
    sensitive_internal_msg = (
        "smtp-pool-internal.aws.zone4:587 read timeout after payload commit"
    )

    def fail_ambiguous(*, uid, conversation, recipient_emails):
        raise AmbiguousDeliveryError(sensitive_internal_msg)

    monkeypatch.setattr(
        conversations_router.share_email, "send_summary_email", fail_ambiguous
    )

    client = _create_test_client()
    with caplog.at_level(logging.WARNING):
        response = client.post(
            f"/v1/conversations/{CONV_ID}/share-email",
            json={"recipient_emails": ["alice@partner.com"]},
        )

    assert response.status_code == 504
    data = response.json()
    expected_detail = "Email delivery timed out or is pending confirmation. Please check back shortly."
    assert data["detail"] == expected_detail
    assert "smtp-pool-internal" not in response.text
    assert sensitive_internal_msg not in response.text

    # Claim promoted to sent ledger to avoid duplicates on retry; visibility stays shared
    assert _stub_share_email_data_layer["visibility"] == "shared"
    assert (
        "uid-sanitization-test",
        CONV_ID,
        ["alice@partner.com"],
    ) in _stub_share_email_data_layer["confirmations"]
    assert "alice@partner.com" in _stub_share_email_data_layer["sent"]
    assert _stub_share_email_data_layer["refunds"] == []

    # Server log contains the diagnostic details for observability
    assert any(
        "ambiguous delivery" in record.message
        and sensitive_internal_msg in record.message
        for record in caplog.records
    )


def test_value_error_sanitizes_error_message(
    monkeypatch, _stub_share_email_data_layer, caplog
):
    """HTTP 503 on ValueError returns sanitized configuration/recipient detail and releases reservation."""
    sensitive_internal_msg = (
        "Invalid internal DKIM key dkim_sec_xyz890 for tenant omi-corp"
    )

    def fail_value_error(*, uid, conversation, recipient_emails):
        raise ValueError(sensitive_internal_msg)

    monkeypatch.setattr(
        conversations_router.share_email, "send_summary_email", fail_value_error
    )

    client = _create_test_client()
    with caplog.at_level(logging.WARNING):
        response = client.post(
            f"/v1/conversations/{CONV_ID}/share-email",
            json={"recipient_emails": ["alice@partner.com"]},
        )

    assert response.status_code == 503
    data = response.json()
    expected_detail = "Invalid email recipient or configuration."
    assert data["detail"] == expected_detail
    assert "dkim_sec_xyz890" not in response.text
    assert sensitive_internal_msg not in response.text

    # Reservation released and quota refunded
    assert _stub_share_email_data_layer["visibility"] == "private"
    assert (
        "uid-sanitization-test",
        CONV_ID,
        ["alice@partner.com"],
    ) in _stub_share_email_data_layer["releases"]
    assert (UID, 1) in _stub_share_email_data_layer["refunds"]
    assert _stub_share_email_data_layer["sent"] == []

    # Server log records the underlying exception
    assert any(
        "invalid recipient or configuration" in record.message
        and sensitive_internal_msg in record.message
        for record in caplog.records
    )


def test_runtime_error_sanitizes_error_message(
    monkeypatch, _stub_share_email_data_layer, caplog
):
    """HTTP 502 on RuntimeError returns sanitized service unavailable detail and releases reservation."""
    sensitive_internal_msg = "Resend API cluster ratelimit reached at backend node worker-12.internal (re_live_key_999)"

    def fail_runtime_error(*, uid, conversation, recipient_emails):
        raise RuntimeError(sensitive_internal_msg)

    monkeypatch.setattr(
        conversations_router.share_email, "send_summary_email", fail_runtime_error
    )

    client = _create_test_client()
    with caplog.at_level(logging.WARNING):
        response = client.post(
            f"/v1/conversations/{CONV_ID}/share-email",
            json={"recipient_emails": ["alice@partner.com"]},
        )

    assert response.status_code == 502
    data = response.json()
    expected_detail = "Email delivery service temporarily unavailable."
    assert data["detail"] == expected_detail
    assert "re_live_key_999" not in response.text
    assert sensitive_internal_msg not in response.text

    # Reservation released and quota refunded
    assert _stub_share_email_data_layer["visibility"] == "private"
    assert (
        "uid-sanitization-test",
        CONV_ID,
        ["alice@partner.com"],
    ) in _stub_share_email_data_layer["releases"]
    assert (UID, 1) in _stub_share_email_data_layer["refunds"]
    assert _stub_share_email_data_layer["sent"] == []

    # Server log records the underlying exception
    assert any(
        "delivery service temporarily unavailable" in record.message
        and sensitive_internal_msg in record.message
        for record in caplog.records
    )
