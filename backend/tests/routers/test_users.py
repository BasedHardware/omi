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

# Save prior sys.modules entries BEFORE any stubbed import runs so the
# module-scoped teardown restores the real modules (not the stub-loaded
# versions) — otherwise the mock-backed shim leaks into later test modules.
_prior_endpoints = sys.modules.get('utils.other.endpoints')
sys.modules['utils.other.endpoints'] = _endpoints

_prior_routers_users = sys.modules.get('routers.users')
_prior_service_modules = {
    name: sys.modules.get(name)
    for name in (
        'services.users',
        'services.users.account_deletion',
        'services.users.data_export',
    )
}

import firebase_admin.auth as _fa_auth  # noqa: E402

_fa_auth.InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})

from routers import users as users_router  # noqa: E402

sys.meta_path.remove(_finder)
for _module_name, _module in list(sys.modules.items()):
    if isinstance(_module, _AutoMockModule):
        del sys.modules[_module_name]

# Pop ``routers.users`` and the service modules it transitively imported under
# the stub finder so later test modules in a full ``pytest tests`` run re-import
# the real modules instead of reusing mock-backed symbols.
sys.modules.pop('routers.users', None)
for _svc_name in _prior_service_modules:
    sys.modules.pop(_svc_name, None)
# Clear parent package attributes so ``from routers import users`` and
# ``from services.users import ...`` don't resolve to stub-loaded modules via
# attribute lookup on the already-imported package objects.
for _pkg_name, _attr in (
    ('routers', 'users'),
    ('services', 'users'),
    ('services.users', 'account_deletion'),
    ('services.users', 'data_export'),
):
    _pkg = sys.modules.get(_pkg_name)
    if _pkg is not None and hasattr(_pkg, _attr):
        delattr(_pkg, _attr)

# Restore utils.other.endpoints immediately too — pytest collects later test
# modules before any module-scoped fixture teardown runs, so the shim would
# persist in sys.modules during that window.  users_router already holds the
# reference it needs; the shim is no longer required after import.
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
