"""Statusless deletion residue admits sign-in only; every other fence stays closed."""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, WebSocketException

from database.account_deletion_policy import ACCOUNT_DELETION_INVALID_STATUS
from utils.other import endpoints


@pytest.fixture(autouse=True)
def _quiet_auth_side_effects(monkeypatch):
    monkeypatch.setattr(endpoints, 'verify_token', lambda _token: 'uid-1')
    monkeypatch.setattr(endpoints, 'record_user_platform', MagicMock())
    monkeypatch.setattr(endpoints, 'record_client_device', MagicMock())
    monkeypatch.setattr(endpoints, 'validate_byok_request', MagicMock())


def test_sign_in_admits_statusless_residue(monkeypatch):
    monkeypatch.setattr(endpoints, 'get_user_deletion_wipe_status', lambda _uid: ACCOUNT_DELETION_INVALID_STATUS)

    assert endpoints.get_current_user_uid(authorization='Bearer token') == 'uid-1'


def test_default_http_fence_still_denies_statusless_residue(monkeypatch):
    monkeypatch.setattr(endpoints, 'get_user_deletion_wipe_status', lambda _uid: ACCOUNT_DELETION_INVALID_STATUS)

    with pytest.raises(HTTPException) as error:
        endpoints.enforce_account_deletion_http_access('uid-1')

    assert error.value.status_code == 403


def test_websocket_fence_still_denies_statusless_residue(monkeypatch):
    monkeypatch.setattr(endpoints, 'get_user_deletion_wipe_status', lambda _uid: ACCOUNT_DELETION_INVALID_STATUS)

    with pytest.raises(WebSocketException):
        endpoints.enforce_account_deletion_ws_access('uid-1')


def test_sign_in_still_denies_unknown_nonempty_status(monkeypatch):
    monkeypatch.setattr(endpoints, 'get_user_deletion_wipe_status', lambda _uid: 'unexpected')

    with pytest.raises(HTTPException) as error:
        endpoints.get_current_user_uid(authorization='Bearer token')

    assert error.value.status_code == 403
    endpoints.validate_byok_request.assert_not_called()
