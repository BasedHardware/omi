"""#20239 — an empty/unset ADMIN_KEY must never authenticate the privileged routes.

Before the fix, `secret_key != os.getenv('ADMIN_KEY')` passed when both were
empty (and the != comparison wasn't constant-time). _verify_admin_key is
fail-closed and constant-time.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import pytest
from fastapi import HTTPException

import routers.updates as updates_router


def _set_key(monkeypatch, value):
    if value is None:
        monkeypatch.delenv('ADMIN_KEY', raising=False)
    else:
        monkeypatch.setenv('ADMIN_KEY', value)


@pytest.mark.parametrize('secret', ['', 'wrong', 'sekrit-but-not-the-key'])
def test_empty_configured_key_never_authenticates(monkeypatch, secret):
    _set_key(monkeypatch, '')
    with pytest.raises(HTTPException) as exc:
        updates_router._verify_admin_key(secret)
    assert exc.value.status_code == 403


def test_unset_configured_key_never_authenticates(monkeypatch):
    _set_key(monkeypatch, None)
    for secret in ('', 'anything'):
        with pytest.raises(HTTPException):
            updates_router._verify_admin_key(secret)


def test_empty_presented_secret_never_authenticates(monkeypatch):
    _set_key(monkeypatch, 'real-admin-key')
    with pytest.raises(HTTPException):
        updates_router._verify_admin_key('')


def test_wrong_key_rejected(monkeypatch):
    _set_key(monkeypatch, 'real-admin-key')
    for secret in ('REAL-ADMIN-KEY', 'real-admin-key ', 'x' * 200):
        with pytest.raises(HTTPException):
            updates_router._verify_admin_key(secret)


def test_correct_key_passes(monkeypatch):
    _set_key(monkeypatch, 'real-admin-key')
    updates_router._verify_admin_key('real-admin-key')  # no raise


def test_both_empty_no_longer_passes(monkeypatch):
    # The original bypass: secret_key='' == ADMIN_KEY='' -> authorized.
    _set_key(monkeypatch, '')
    with pytest.raises(HTTPException):
        updates_router._verify_admin_key('')
