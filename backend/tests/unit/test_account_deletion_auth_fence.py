"""The durable account-deletion marker is an authentication access barrier."""

import logging
import inspect
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, WebSocketException

from utils.other import endpoints
from database import users
from database.account_deletion_marker import account_deletion_blocks_user_work
from routers import account_deletion as deletion_router


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


def test_pending_deletion_has_a_distinct_owner_facing_auth_error(monkeypatch):
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", lambda _uid: "pending_deletion")

    with pytest.raises(HTTPException) as error:
        endpoints.get_current_user_uid(authorization="Bearer token")

    assert error.value.status_code == 403
    assert error.value.detail == {
        "code": "account_pending_deletion",
        "status": "pending_deletion",
        "retryable": False,
    }


def test_deletion_status_authentication_keeps_pending_account_recovery_route_open(monkeypatch):
    monkeypatch.setattr(
        endpoints,
        "get_user_deletion_wipe_status",
        lambda _uid: pytest.fail("status authentication must not open ordinary account access"),
    )

    assert endpoints.get_current_user_uid_for_deletion_status(authorization="Bearer token") == "old-uid"


@pytest.mark.parametrize(
    ("status", "erase_now", "allowed"),
    [
        (None, True, True),
        ("pending_deletion", True, True),
        ("pending_deletion", False, False),
        ("pending", True, False),
        ("running", True, False),
    ],
)
def test_erase_now_auth_is_limited_to_restorable_grace_status(monkeypatch, status, erase_now, allowed):
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", lambda _uid: status)

    if allowed:
        endpoints.enforce_account_deletion_http_access("old-uid", allow_grace_erase_now=erase_now)
    else:
        with pytest.raises(HTTPException) as error:
            endpoints.enforce_account_deletion_http_access("old-uid", allow_grace_erase_now=erase_now)
        assert error.value.status_code == 403


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


def test_deletion_state_read_failure_logs_no_uid_or_error_detail(monkeypatch, caplog):
    sentinel_uid = "uid-sentinel-a1b2c3"
    monkeypatch.setattr(endpoints, "verify_token", lambda _token: sentinel_uid)

    def unavailable(_uid):
        raise RuntimeError("firestore unreachable via credential-secret-xyz")

    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", unavailable)

    with caplog.at_level(logging.ERROR, logger="utils.other.endpoints"):
        with pytest.raises(HTTPException) as error:
            endpoints.get_current_user_uid(authorization="Bearer token")

    assert error.value.status_code == 503
    assert error.value.detail == {"code": "account_deletion_state_unavailable", "retryable": True}
    assert sentinel_uid not in caplog.text
    assert "credential-secret-xyz" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text


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


@pytest.mark.parametrize(
    ('status', 'blocked'),
    [
        (None, False),
        ('cancelled', False),
        ('billing_failed', False),
        ('pending_deletion', True),
        ('pending', True),
        ('running', True),
        ('completed', True),
        ('unexpected', True),
    ],
)
def test_shared_background_predicate_matches_access_fence(status, blocked):
    docs = {} if status is None else {'account_deletions/u': {'wipe_status': status}}
    assert account_deletion_blocks_user_work('u', firestore_client=_PlaneClient(docs)) is blocked


def test_erase_now_route_uses_the_recovery_auth_dependency_and_promotes_pending(monkeypatch):
    route_parameters = inspect.signature(deletion_router.delete_account).parameters
    dependency = route_parameters['uid'].default.dependency
    assert dependency is endpoints.get_current_user_uid_for_deletion_status
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", lambda _uid: "pending_deletion")
    assert {
        inspect.signature(dependency).parameters[name].default.alias
        for name in ('_x_app_platform', '_x_device_id_hash', '_x_app_version')
    } == {'X-App-Platform', 'X-Device-Id-Hash', 'X-App-Version'}
    uid = dependency(authorization='Bearer token')
    observed = {}

    def promote(actual_uid, **kwargs):
        observed.update(uid=actual_uid, **kwargs)
        return {'status': 'pending', 'message': 'Wipe scheduled'}

    monkeypatch.setattr(deletion_router, 'start_account_deletion', promote)
    result = deletion_router.delete_account(
        request=deletion_router.DeleteAccountRequest(erase_now=True),
        uid=uid,
    )

    assert observed == {'uid': 'old-uid', 'reason': None, 'reason_details': None, 'grace': False, 'erase_now': True}
    assert result['status'] == 'pending'


def test_erase_now_route_rejects_an_already_queued_immediate_wipe(monkeypatch):
    monkeypatch.setattr(endpoints, "get_user_deletion_wipe_status", lambda _uid: "pending")
    start = MagicMock()
    monkeypatch.setattr(deletion_router, 'start_account_deletion', start)

    with pytest.raises(HTTPException) as error:
        deletion_router.delete_account(
            request=deletion_router.DeleteAccountRequest(erase_now=True),
            uid='old-uid',
        )

    assert error.value.status_code == 403
    start.assert_not_called()


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


def test_reset_recovery_runs_only_after_auth_deletion_cutover_and_byok_checks(monkeypatch):
    from types import SimpleNamespace
    from utils import locked_content_recovery

    events = []
    monkeypatch.setattr(endpoints, 'get_user_deletion_wipe_status', lambda uid: events.append('deletion') or None)
    monkeypatch.setattr(endpoints, '_enforce_cutover_http_if_request', lambda uid, request: events.append('cutover'))
    monkeypatch.setattr(endpoints, 'validate_byok_request', lambda uid: events.append('byok'))
    monkeypatch.setattr(locked_content_recovery, 'recover_locked_content', lambda uid: events.append('recovery'))
    assert (
        endpoints.get_current_user_uid(authorization='Bearer token', request=SimpleNamespace(method='GET')) == 'old-uid'
    )
    assert events == ['deletion', 'cutover', 'byok', 'recovery']


def test_deleting_account_never_runs_reset_recovery(monkeypatch):
    from types import SimpleNamespace
    from utils import locked_content_recovery

    recovery = MagicMock()
    monkeypatch.setattr(endpoints, 'get_user_deletion_wipe_status', lambda uid: 'running')
    monkeypatch.setattr(locked_content_recovery, 'recover_locked_content', recovery)
    with pytest.raises(HTTPException):
        endpoints.get_current_user_uid(authorization='Bearer token', request=SimpleNamespace(method='GET'))
    recovery.assert_not_called()


def test_delete_request_does_not_run_reset_recovery(monkeypatch):
    from types import SimpleNamespace
    from utils import locked_content_recovery

    recovery = MagicMock()
    monkeypatch.setattr(endpoints, 'get_user_deletion_wipe_status', lambda uid: None)
    monkeypatch.setattr(endpoints, '_enforce_cutover_http_if_request', lambda uid, request: None)
    monkeypatch.setattr(locked_content_recovery, 'recover_locked_content', recovery)
    assert (
        endpoints.get_current_user_uid(authorization='Bearer token', request=SimpleNamespace(method='DELETE'))
        == 'old-uid'
    )
    recovery.assert_not_called()
