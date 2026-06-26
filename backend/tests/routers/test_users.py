import asyncio
import importlib.abc
import importlib.machinery
import sys
import types
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException


class _AutoMockModule(types.ModuleType):
    __path__ = []

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_STUB_PREFIXES = (
    'database',
    'firebase_admin',
    'google.cloud',
    'google.api_core',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'pytz',
    'twilio',
    'utils',
)


def _should_stub(name: str) -> bool:
    if name in {'utils.other.endpoints', 'services.users'}:
        return False
    return any(name == prefix or name.startswith(prefix + '.') for prefix in _STUB_PREFIXES)


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path=None, target=None):
        if _should_stub(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


_finder = _StubFinder()
sys.meta_path.insert(0, _finder)

_endpoints = types.ModuleType('utils.other.endpoints')
_endpoints.get_current_user_uid = lambda: 'uid1'
_endpoints.with_rate_limit = lambda dependency, _policy: dependency
_endpoints.delete_account = MagicMock()
_endpoints.get_user = MagicMock()
sys.modules['utils.other.endpoints'] = _endpoints

_services_users = types.ModuleType('services.users')
_services_users.iter_user_data_export = MagicMock(return_value=iter(['{"ok": true}\n']))
_services_users.start_account_deletion = MagicMock(return_value={'status': 'ok', 'message': 'Account deletion started'})
sys.modules['services.users'] = _services_users

import firebase_admin.auth as _fa_auth  # noqa: E402

_fa_auth.InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

from routers import users as users_router  # noqa: E402


def test_delete_account_delegates_to_service():
    users_router.start_account_deletion = MagicMock(
        return_value={'status': 'ok', 'message': 'Account deletion started'}
    )
    request = users_router.DeleteAccountRequest(reason='reason', reason_details='details')

    result = users_router.delete_account(request=request, uid='uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    users_router.start_account_deletion.assert_called_once_with('uid1', reason='reason', reason_details='details')


def test_delete_account_maps_unexpected_service_error_to_500():
    users_router.start_account_deletion = MagicMock(side_effect=Exception('boom'))

    with pytest.raises(HTTPException) as exc:
        users_router.delete_account(request=users_router.DeleteAccountRequest(), uid='uid1')

    assert exc.value.status_code == 500
    assert exc.value.detail == 'Could not delete account. Please try again.'


def test_export_all_user_data_keeps_streaming_headers():
    users_router.iter_user_data_export = MagicMock(return_value=iter(['{"ok": true}\n']))

    response = users_router.export_all_user_data(uid='uid1')

    assert response.media_type == 'application/json'
    assert response.headers['content-disposition'] == 'attachment; filename="omi-export.json"'
    users_router.iter_user_data_export.assert_called_once_with('uid1')

    async def _consume():
        parts = []
        async for chunk in response.body_iterator:
            parts.append(chunk)
        return ''.join(parts)

    assert asyncio.run(_consume()) == '{"ok": true}\n'
