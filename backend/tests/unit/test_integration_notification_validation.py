"""POST /v1/integrations/notification must return 400 (not 500) when message is missing.

It read data['message'] via direct subscript, so a body without message raised KeyError -> 500.
routers/notifications.py has a heavy import graph, so we import it under a stub finder.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
)


def _is_stubbed_name(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


def _snapshot():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


class _AutoMock(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        m = MagicMock()
        setattr(self, name, m)
        return m


class _Finder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot()
_clear()
sys.meta_path.insert(0, _finder)
try:
    from routers import notifications as notif_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)

from fastapi import HTTPException  # noqa: E402
from models.other import SendAppNotificationRequest, SendNotificationRequest  # noqa: E402
from pydantic import ValidationError  # noqa: E402


def test_missing_message_returns_400():
    with pytest.raises(HTTPException) as e:
        notif_mod.send_app_notification_to_user(
            request=MagicMock(),
            data=SendAppNotificationRequest(aid='app1', message='', uid='uid1'),
            authorization=None,
        )
    assert e.value.status_code == 400


def test_whitespace_message_returns_400():
    with pytest.raises(HTTPException) as e:
        notif_mod.send_app_notification_to_user(
            request=MagicMock(),
            data=SendAppNotificationRequest(aid='app1', message='   ', uid='uid1'),
            authorization=None,
        )
    assert e.value.status_code == 400


def test_send_notification_admin_key_unauthorized():
    req = SendNotificationRequest(uid='u1', title='Test Title', body='Test Body')
    with patch.dict(os.environ, {'ADMIN_KEY': 'secret_pass'}):
        with pytest.raises(HTTPException) as exc:
            notif_mod.send_notification_to_user(data=req, secret_key='wrong_key')
        assert exc.value.status_code == 403


def test_send_notification_admin_key_unset():
    req = SendNotificationRequest(uid='u1', title='Test Title', body='Test Body')
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(HTTPException) as exc:
            notif_mod.send_notification_to_user(data=req, secret_key='')
        assert exc.value.status_code == 403


def test_send_notification_success():
    req = SendNotificationRequest(uid='u1', title='Test Title', body='Test Body', data={'custom': 'val'})
    with patch.dict(os.environ, {'ADMIN_KEY': 'secret_pass'}):
        with patch.object(notif_mod, 'send_notification') as mock_send:
            res = notif_mod.send_notification_to_user(data=req, secret_key='secret_pass')
            assert res == {'status': 'Ok'}
            mock_send.assert_called_once_with('u1', 'Test Title', 'Test Body', {'custom': 'val'})


def test_send_notification_request_validation():
    # Blank/empty title or body should be rejected by model validation
    with pytest.raises(ValidationError):
        SendNotificationRequest(uid='u1', title='   ', body='Valid Body')

    with pytest.raises(ValidationError):
        SendNotificationRequest(uid='u1', title='Valid Title', body='   ')

    with pytest.raises(ValidationError):
        SendNotificationRequest(uid='   ', title='Valid Title', body='Valid Body')
