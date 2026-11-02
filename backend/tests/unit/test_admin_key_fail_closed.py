"""The admin `secret-key` route verifiers must fail closed when ADMIN_KEY is unset or empty.

`secret_key != os.getenv('ADMIN_KEY')` is False when both sides are empty, so a deployment where
ADMIN_KEY resolves to "" (an operator error the repo's own desktop-beta workflow treats as fatal)
authenticated an empty `secret-key` as an admin.
"""

import pytest
from fastapi import HTTPException

from routers import memory_admin, notifications


def test_memory_admin_requires_a_nonempty_admin_key(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', '')
    with pytest.raises(HTTPException) as empty:
        memory_admin._require_admin_key('')
    assert empty.value.status_code == 403

    monkeypatch.delenv('ADMIN_KEY', raising=False)
    with pytest.raises(HTTPException):
        memory_admin._require_admin_key('')

    monkeypatch.setenv('ADMIN_KEY', 'real-admin-key')
    with pytest.raises(HTTPException):
        memory_admin._require_admin_key('')
    with pytest.raises(HTTPException):
        memory_admin._require_admin_key('nope')
    memory_admin._require_admin_key('real-admin-key')  # correct key passes


def test_notification_route_rejects_an_empty_key_when_admin_key_is_empty(monkeypatch):
    monkeypatch.setenv('ADMIN_KEY', '')
    with pytest.raises(HTTPException) as empty:
        notifications.send_notification_to_user({'uid': 'someone'}, '')
    assert empty.value.status_code == 403
