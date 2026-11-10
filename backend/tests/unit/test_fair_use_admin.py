import inspect
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.params import Header
from pydantic_core import PydanticUndefined

import routers.fair_use_admin as fua


def test_verify_admin_key_empty(monkeypatch):
    """Empty string passed as x_admin_key returns HTTP 403."""
    monkeypatch.setattr(fua, 'ADMIN_KEY', 'secret_admin_key_abc')

    with pytest.raises(HTTPException) as exc_info:
        fua._verify_admin_key(x_admin_key='')
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == 'Invalid admin key'


def test_verify_admin_key_invalid(monkeypatch):
    """Invalid string returns HTTP 403."""
    monkeypatch.setattr(fua, 'ADMIN_KEY', 'secret_admin_key_abc')

    with pytest.raises(HTTPException) as exc_info:
        fua._verify_admin_key(x_admin_key='wrong_token')
    assert exc_info.value.status_code == 403


def test_verify_admin_key_success(monkeypatch):
    """Matching key returns admin audit identity with exact truncated sha256 hash."""
    monkeypatch.setattr(fua, 'ADMIN_KEY', 'secret_admin_key_abc')

    res = fua._verify_admin_key(x_admin_key='secret_admin_key_abc')
    assert res == 'admin:352d6b69'


def test_verify_admin_key_header_is_required_in_signature():
    """Verify that x_admin_key is marked as required via Header(alias='X-Admin-Key')."""
    sig = inspect.signature(fua._verify_admin_key)
    param = sig.parameters['x_admin_key']
    assert isinstance(param.default, Header)
    assert param.default.alias == 'X-Admin-Key'
    assert param.default.default is PydanticUndefined or param.default.default is ...


def test_get_flagged_users_clamps_limits(monkeypatch):
    """Confirm in-function clamping of limit to [1, 200]."""
    mock_get_flagged = MagicMock(return_value=[{'uid': 'u1', 'stage': 'warning'}])
    monkeypatch.setattr(fua.fair_use_db, 'get_flagged_users', mock_get_flagged)

    # Test limit > 200 clamped to 200
    res = fua.get_flagged_users(admin_id='admin:test', stage='warning', limit=500)
    mock_get_flagged.assert_called_with(stage_filter='warning', limit=200)
    assert res['users'] == [{'uid': 'u1', 'stage': 'warning'}]

    # Test limit < 1 clamped to 1
    fua.get_flagged_users(admin_id='admin:test', stage=None, limit=-10)
    mock_get_flagged.assert_called_with(stage_filter=None, limit=1)
