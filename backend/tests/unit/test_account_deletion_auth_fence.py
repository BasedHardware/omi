"""The durable account-deletion marker is an authentication access barrier."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, WebSocketException

from utils.other import endpoints
from database import users


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
        endpoints.get_current_user_uid(authorization="Bearer token")

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

    assert endpoints.get_current_user_uid(authorization="Bearer token") == "old-uid"


def test_same_provider_fresh_uid_has_no_old_uid_marker(monkeypatch):
    statuses = {"deleted-uid": "completed", "fresh-firebase-uid": None}
    monkeypatch.setattr(endpoints, "verify_token", lambda _token: "fresh-firebase-uid")
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", statuses.get)

    assert endpoints.get_current_user_uid(authorization="Bearer fresh-token") == "fresh-firebase-uid"


def test_deletion_state_read_failure_fails_closed(monkeypatch):
    def unavailable(_uid):
        raise RuntimeError("firestore unavailable")

    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", unavailable)

    with pytest.raises(HTTPException) as error:
        endpoints.get_current_user_uid(authorization="Bearer token")

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


class _PlaneSnapshot:
    def __init__(self, payload):
        self.exists = payload is not None
        self._payload = payload or {}

    def to_dict(self):
        return dict(self._payload)


class _PlaneDocument:
    def __init__(self, docs, path):
        self._docs = docs
        self._path = path

    def get(self):
        return _PlaneSnapshot(self._docs.get(self._path))


class _PlaneCollection:
    def __init__(self, docs, name):
        self._docs = docs
        self._name = name

    def document(self, uid):
        return _PlaneDocument(self._docs, f"{self._name}/{uid}")


class _PlaneClient:
    """Minimal Firestore stand-in that only serves collection/document/get."""

    def __init__(self, docs):
        self._docs = docs

    def collection(self, name):
        return _PlaneCollection(self._docs, name)


def test_auth_fence_refuses_when_the_deletion_marker_is_only_on_the_data_plane(monkeypatch):
    """The Beta serving plane's compute Firestore is empty; the marker lives on the data plane.

    A clean miss on the compute plane must not reopen access. This is the
    2026-08-30 adversarial finding: get_user_deletion_wipe_status fell back to
    get_firestore_client(), every caller passed no client, and 503 only fired
    on an exception.
    """
    compute_plane = _PlaneClient({})
    data_plane = _PlaneClient({"account_deletions/old-uid": {"wipe_status": "running"}})

    monkeypatch.setattr(users, "get_firestore_client", lambda: compute_plane)
    monkeypatch.setattr(users, "get_data_plane_firestore_client", lambda: data_plane, raising=False)
    monkeypatch.setattr("database._client.get_firestore_client", lambda: compute_plane)
    monkeypatch.setattr("database._client.get_data_plane_firestore_client", lambda: data_plane)
    monkeypatch.setattr(
        "database.account_deletion_marker.get_data_plane_firestore_client", lambda: data_plane, raising=False
    )
    monkeypatch.setattr("database.account_deletion_marker.get_firestore_client", lambda: compute_plane, raising=False)

    with pytest.raises(HTTPException) as error:
        endpoints.enforce_account_deletion_http_access("old-uid")

    assert error.value.status_code == 403
    assert error.value.detail == {
        "code": "account_deletion_in_progress",
        "status": "running",
        "retryable": False,
    }


def test_auth_fence_fails_closed_when_the_data_plane_client_cannot_be_resolved(monkeypatch):
    compute_plane = _PlaneClient({})

    def unresolved():
        raise RuntimeError("OMI_FIRESTORE_DATA_PLANE_PROJECT is required on desktop-backend")

    monkeypatch.setattr(users, "get_firestore_client", lambda: compute_plane)
    monkeypatch.setattr(users, "get_data_plane_firestore_client", unresolved, raising=False)
    monkeypatch.setattr("database._client.get_firestore_client", lambda: compute_plane)
    monkeypatch.setattr("database._client.get_data_plane_firestore_client", unresolved)
    monkeypatch.setattr("database.account_deletion_marker.get_data_plane_firestore_client", unresolved, raising=False)
    monkeypatch.setattr("database.account_deletion_marker.get_firestore_client", lambda: compute_plane, raising=False)

    with pytest.raises(HTTPException) as error:
        endpoints.enforce_account_deletion_http_access("old-uid")

    assert error.value.status_code == 503
    assert error.value.detail == {"code": "account_deletion_state_unavailable", "retryable": True}


class _RaisingGetClient:
    """Resolved data-plane client whose document get() fails after the client is already in hand."""

    def collection(self, name):
        document = MagicMock()
        document.get.side_effect = RuntimeError("firestore ServiceUnavailable")
        collection = MagicMock()
        collection.document.return_value = document
        return collection


def test_auth_fence_fails_closed_when_the_resolved_data_plane_read_raises(monkeypatch):
    """A timeout/ServiceUnavailable after client resolution must be HTTP 503, not a clean miss.

    The production marker has no except around snapshot.get(). Swallowing only that
    get() into None is the mutation this test is for: the fence would then allow.
    """
    compute_plane = _PlaneClient({})
    data_plane = _RaisingGetClient()

    monkeypatch.setattr(users, "get_firestore_client", lambda: compute_plane)
    monkeypatch.setattr(users, "get_data_plane_firestore_client", lambda: data_plane, raising=False)
    monkeypatch.setattr("database._client.get_firestore_client", lambda: compute_plane)
    monkeypatch.setattr("database._client.get_data_plane_firestore_client", lambda: data_plane)
    monkeypatch.setattr(
        "database.account_deletion_marker.get_data_plane_firestore_client", lambda: data_plane, raising=False
    )
    monkeypatch.setattr("database.account_deletion_marker.get_firestore_client", lambda: compute_plane, raising=False)

    with pytest.raises(HTTPException) as error:
        endpoints.enforce_account_deletion_http_access("old-uid")

    assert error.value.status_code == 503
    assert error.value.detail == {"code": "account_deletion_state_unavailable", "retryable": True}
