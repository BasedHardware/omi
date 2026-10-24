"""Hermetic unit tests for notification router validation and constant-time admin auth."""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

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


def _is_stubbed_name(name: str) -> bool:
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

from models.other import SaveFcmTokenRequest, SendNotificationRequest  # noqa: E402


def _make_client():
    app = FastAPI()
    app.include_router(notif_mod.router)
    return TestClient(app)


# ============================================================================
# SendNotificationRequest Model Tests
# ============================================================================


def test_send_notification_request_normalizes_and_strips_whitespace():
    req = SendNotificationRequest(
        uid='  user_123  ',
        title='  New Update  ',
        body='  Check your summary now.  ',
        data={'route': 'summary'},
    )
    assert req.uid == 'user_123'
    assert req.title == 'New Update'
    assert req.body == 'Check your summary now.'
    assert req.data == {'route': 'summary'}


@pytest.mark.parametrize(
    'field,value',
    [
        ('uid', '   '),
        ('title', '   '),
        ('body', '   '),
        ('uid', ''),
        ('title', ''),
        ('body', ''),
        ('uid', 123),
        ('title', None),
        ('body', ['not', 'a', 'string']),
    ],
)
def test_send_notification_request_rejects_blank_or_invalid_fields(field, value):
    valid_data = {'uid': 'user_1', 'title': 'Title', 'body': 'Body'}
    valid_data[field] = value
    with pytest.raises(ValidationError):
        SendNotificationRequest(**valid_data)


# ============================================================================
# SaveFcmTokenRequest Model Tests
# ============================================================================


def test_save_fcm_token_request_normalizes_and_strips_token():
    req = SaveFcmTokenRequest(fcm_token='  fcm-token-xyz  ', time_zone='UTC')
    assert req.fcm_token == 'fcm-token-xyz'
    assert req.time_zone == 'UTC'


@pytest.mark.parametrize('invalid_token', ['', '   ', 123, None])
def test_save_fcm_token_request_rejects_blank_or_non_string_token(invalid_token):
    with pytest.raises(ValidationError):
        SaveFcmTokenRequest(fcm_token=invalid_token, time_zone='UTC')


# ============================================================================
# POST /v1/notification Route Tests
# ============================================================================


def test_send_notification_admin_auth_constant_time_success():
    client = _make_client()
    with patch.dict(os.environ, {'ADMIN_KEY': 'super-secret-admin-key'}), patch.object(
        notif_mod, 'send_notification'
    ) as mock_send:
        resp = client.post(
            '/v1/notification',
            headers={'secret-key': 'super-secret-admin-key'},
            json={'uid': 'user_456', 'title': 'Important', 'body': 'Action needed'},
        )
        assert resp.status_code == 200
        assert resp.json() == {'status': 'Ok'}
        mock_send.assert_called_once_with('user_456', 'Important', 'Action needed', {})


def test_send_notification_admin_auth_rejects_mismatched_or_empty_secret():
    client = _make_client()
    with patch.dict(os.environ, {'ADMIN_KEY': 'super-secret-admin-key'}), patch.object(
        notif_mod, 'send_notification'
    ) as mock_send:
        # Wrong secret
        resp = client.post(
            '/v1/notification',
            headers={'secret-key': 'wrong-secret'},
            json={'uid': 'user_456', 'title': 'Important', 'body': 'Action needed'},
        )
        assert resp.status_code == 403
        assert resp.json() == {'detail': 'You are not authorized to perform this action'}

        # Non-ASCII wrong secret (must not 500)
        resp_non_ascii = client.post(
            '/v1/notification',
            headers={b'secret-key': b'wrong-secret-\xe9'},
            json={'uid': 'user_456', 'title': 'Important', 'body': 'Action needed'},
        )
        assert resp_non_ascii.status_code == 403
        mock_send.assert_not_called()


def test_send_notification_admin_auth_fails_closed_when_admin_key_unset():
    client = _make_client()
    with patch.dict(os.environ, {'ADMIN_KEY': ''}, clear=True), patch.object(
        notif_mod, 'send_notification'
    ) as mock_send:
        resp = client.post(
            '/v1/notification',
            headers={'secret-key': 'any-secret'},
            json={'uid': 'user_456', 'title': 'Important', 'body': 'Action needed'},
        )
        assert resp.status_code == 403
        mock_send.assert_not_called()


def test_send_notification_rejects_missing_or_whitespace_payload_with_422():
    client = _make_client()
    with patch.dict(os.environ, {'ADMIN_KEY': 'admin-secret'}), patch.object(
        notif_mod, 'send_notification'
    ) as mock_send:
        # Missing title & body (previously raised KeyError -> 500)
        resp = client.post(
            '/v1/notification',
            headers={'secret-key': 'admin-secret'},
            json={'uid': 'user_123'},
        )
        assert resp.status_code == 422
        mock_send.assert_not_called()

        # Whitespace-only title
        resp2 = client.post(
            '/v1/notification',
            headers={'secret-key': 'admin-secret'},
            json={'uid': 'user_123', 'title': '   ', 'body': 'Valid body'},
        )
        assert resp2.status_code == 422
        mock_send.assert_not_called()
