import asyncio
import importlib.abc
import importlib.machinery
import sys
import types
from unittest.mock import MagicMock, patch

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

# Save the prior entry so it can be restored after the test module finishes —
# otherwise this minimal shim leaks into sys.modules and can be reused by later
# test modules (e.g. ones expecting the real _enforce_rate_limit), making
# results depend on collection order.
_prior_endpoints = sys.modules.get('utils.other.endpoints')
sys.modules['utils.other.endpoints'] = _endpoints

import firebase_admin.auth as _fa_auth  # noqa: E402

_fa_auth.InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

from routers import users as users_router  # noqa: E402

sys.meta_path.remove(_finder)
for _module_name, _module in list(sys.modules.items()):
    if isinstance(_module, _AutoMockModule):
        del sys.modules[_module_name]


@pytest.fixture(autouse=True, scope='module')
def _restore_endpoints_shim():
    yield
    if _prior_endpoints is None:
        sys.modules.pop('utils.other.endpoints', None)
    else:
        sys.modules['utils.other.endpoints'] = _prior_endpoints


def _account_deletion_module(start_account_deletion):
    module = types.ModuleType('services.users.account_deletion')
    module.start_account_deletion = start_account_deletion
    return module


def test_delete_account_delegates_to_service():
    start_account_deletion = MagicMock(return_value={'status': 'ok', 'message': 'Account deletion started'})
    request = users_router.DeleteAccountRequest(reason='reason', reason_details='details')

    with patch.object(users_router, 'start_account_deletion', start_account_deletion):
        result = users_router.delete_account(request=request, uid='uid1')

    assert result == {'status': 'ok', 'message': 'Account deletion started'}
    start_account_deletion.assert_called_once_with('uid1', reason='reason', reason_details='details')


def test_delete_account_maps_unexpected_service_error_to_500():
    start_account_deletion = MagicMock(side_effect=Exception('boom'))
    with patch.object(users_router, 'start_account_deletion', start_account_deletion):
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
