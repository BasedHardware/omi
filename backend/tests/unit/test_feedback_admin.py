import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from routers.feedback_admin import _verify_admin_key, _parse_date


def test_verify_admin_key_missing_or_empty(monkeypatch):
    import routers.feedback_admin as fa
    monkeypatch.setattr(fa, 'ADMIN_KEY', 'valid_secret_key_123')

    with pytest.raises(HTTPException) as exc_info:
        fa._verify_admin_key(x_admin_key='', x_admin_user=None)
    assert exc_info.value.status_code == 403


def test_verify_admin_key_invalid(monkeypatch):
    import routers.feedback_admin as fa
    monkeypatch.setattr(fa, 'ADMIN_KEY', 'valid_secret_key_123')

    with pytest.raises(HTTPException) as exc_info:
        fa._verify_admin_key(x_admin_key='wrong_key', x_admin_user='admin1')
    assert exc_info.value.status_code == 403


def test_verify_admin_key_success(monkeypatch):
    import routers.feedback_admin as fa
    monkeypatch.setattr(fa, 'ADMIN_KEY', 'valid_secret_key_123')

    user = fa._verify_admin_key(x_admin_key='valid_secret_key_123', x_admin_user='admin_operator')
    assert user.endswith('/admin_operator')
    assert user.startswith('admin:')


def test_verify_admin_key_success_default_user(monkeypatch):
    import routers.feedback_admin as fa
    monkeypatch.setattr(fa, 'ADMIN_KEY', 'valid_secret_key_123')

    user = fa._verify_admin_key(x_admin_key='valid_secret_key_123', x_admin_user=None)
    assert user.endswith('/unattributed')
    assert user.startswith('admin:')


def test_parse_date_valid():
    parsed = _parse_date('2026-10-01')
    assert parsed.year == 2026
    assert parsed.month == 10
    assert parsed.day == 1


def test_parse_date_invalid_format():
    with pytest.raises(HTTPException) as exc_info:
        _parse_date('2026/10/01')
    assert exc_info.value.status_code == 400


def test_parse_date_empty():
    with pytest.raises(HTTPException) as exc_info:
        _parse_date('')
    assert exc_info.value.status_code == 400
