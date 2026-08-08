"""The durable account-deletion marker is an authentication access barrier."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, WebSocketException

from utils.other import endpoints
from database import users


def _request():
    request = MagicMock()
    request.method = "GET"
    request.url.path = "/v1/users"
    request.headers = {}
    return request


@pytest.fixture(autouse=True)
def _quiet_auth_side_effects(monkeypatch):
    monkeypatch.setattr(endpoints, "verify_token", lambda _token: "old-uid")
    monkeypatch.setattr(endpoints, "record_user_platform", MagicMock())
    monkeypatch.setattr(endpoints, "record_client_device", MagicMock())
    monkeypatch.setattr(endpoints, "validate_byok_request", MagicMock())


@pytest.mark.parametrize("status", ["deleting_auth", "pending", "retrying", "running", "failed", "completed"])
def test_http_auth_fences_every_actionable_deletion_state(monkeypatch, status):
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", lambda _uid: status)

    with pytest.raises(HTTPException) as error:
        endpoints.get_current_user_uid(request=_request(), authorization="Bearer token")

    assert error.value.status_code == 403
    assert error.value.detail == {
        "code": "account_deletion_in_progress",
        "status": status,
        "retryable": False,
    }
    endpoints.record_user_platform.assert_not_called()
    endpoints.validate_byok_request.assert_not_called()


@pytest.mark.parametrize("status", [None, "cancelled", "billing_failed"])
def test_terminal_or_pre_acceptance_state_allows_auth(monkeypatch, status):
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", lambda _uid: status)

    assert endpoints.get_current_user_uid(request=_request(), authorization="Bearer token") == "old-uid"


def test_same_provider_fresh_uid_has_no_old_uid_marker(monkeypatch):
    statuses = {"deleted-uid": "completed", "fresh-firebase-uid": None}
    monkeypatch.setattr(endpoints, "verify_token", lambda _token: "fresh-firebase-uid")
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", statuses.get)

    assert (
        endpoints.get_current_user_uid(request=_request(), authorization="Bearer fresh-token") == "fresh-firebase-uid"
    )


def test_deletion_state_read_failure_fails_closed(monkeypatch):
    def unavailable(_uid):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", unavailable)

    with pytest.raises(HTTPException) as error:
        endpoints.get_current_user_uid(request=_request(), authorization="Bearer token")

    assert error.value.status_code == 503
    assert error.value.detail == {"code": "account_deletion_state_unavailable", "retryable": True}


def test_websocket_auth_uses_typed_account_deletion_close(monkeypatch):
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", lambda _uid: "running")

    with pytest.raises(WebSocketException) as error:
        endpoints.enforce_account_deletion_ws_access("old-uid")

    assert error.value.code == endpoints.WS_AUTH_CODE_ACCOUNT_DELETION
    assert error.value.reason == "Account deletion in progress"


def test_deletion_status_reads_the_injected_firestore_client():
    snapshot = MagicMock(exists=True)
    snapshot.to_dict.return_value = {"wipe_status": "running"}
    client = MagicMock()
    client.collection.return_value.document.return_value.get.return_value = snapshot

    assert users.get_user_deletion_wipe_status("old-uid", firestore_client=client) == "running"
    client.collection.assert_called_once_with("account_deletions")
