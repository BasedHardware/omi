"""The admin `secret-key` verifiers must fail closed when ADMIN_KEY is unset/empty (and compare
in constant time). `secret_key != os.getenv('ADMIN_KEY')` is False when both are "", so a
deployment where ADMIN_KEY resolves to "" authenticated an empty `secret-key` as admin.
"""

import pytest
from fastapi import HTTPException

import utils.admin_key as admin_key
from routers import memory_admin


def test_matches_only_a_nonempty_equal_key(monkeypatch):
    monkeypatch.delenv('ADMIN_KEY', raising=False)
    assert admin_key.admin_key_matches('') is False
    assert admin_key.admin_key_matches('x') is False

    # The empty-key bypass this guards against.
    monkeypatch.setenv('ADMIN_KEY', '')
    assert admin_key.admin_key_matches('') is False
    assert admin_key.admin_key_matches('x') is False

    monkeypatch.setenv('ADMIN_KEY', 'super-secret-admin-key')
    assert admin_key.admin_key_matches('super-secret-admin-key') is True
    assert admin_key.admin_key_matches('') is False
    assert admin_key.admin_key_matches('wrong') is False
    assert admin_key.admin_key_matches(None) is False
    # A non-ASCII header value must be rejected, not raise TypeError (500).
    assert admin_key.admin_key_matches('é') is False


def test_memory_admin_require_key_rejects_empty_and_wrong(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', '')
    with pytest.raises(HTTPException) as empty:
        memory_admin._require_admin_key('')
    assert empty.value.status_code == 403

    monkeypatch.setenv('ADMIN_KEY', 'real-admin-key')
    with pytest.raises(HTTPException) as wrong:
        memory_admin._require_admin_key('')
    assert wrong.value.status_code == 403
    with pytest.raises(HTTPException):
        memory_admin._require_admin_key('nope')

    memory_admin._require_admin_key('real-admin-key')  # correct key does not raise
