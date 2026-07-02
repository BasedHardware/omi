"""change_app_visibility must invalidate the public approved-apps list cache for an approved app.

Toggling an approved app's visibility changes whether it appears in the public marketplace list, but
the handler only cleared the per-app cache, so a newly public app did not show up (and a newly
private one kept showing) until the list cache TTL expired -- the apps-caching-on-edit bug (#3783).
Every sibling mutation (approve, reject, delete, update) already invalidates that list cache; this
verifies change_app_visibility now does too, and that it skips it for an unapproved app (which is not
in the public list).

routers/apps.py has a heavy import graph (langchain, utils.llm, stripe, ...), so it is imported under
a stub finder that auto-mocks those namespaces (keeping models/fastapi/pydantic real), then the
handler is called directly with its collaborators patched.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

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


def _snapshot_stubbed_modules():
    return {name: module for name, module in sys.modules.items() if _is_stubbed_name(name)}


def _clear_stubbed_modules():
    for name in list(sys.modules):
        if _is_stubbed_name(name):
            sys.modules.pop(name, None)


def _restore_stubbed_modules(snapshot):
    for name in list(sys.modules):
        if _is_stubbed_name(name) and name not in snapshot:
            sys.modules.pop(name, None)
    sys.modules.update(snapshot)


def _install_python_multipart_stub():
    if 'python_multipart' in sys.modules:
        return False
    if importlib.util.find_spec('python_multipart') is not None:
        return False

    mod = types.ModuleType('python_multipart')
    mod.__version__ = '0.0.20'
    sys.modules['python_multipart'] = mod
    return True


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
        if any(name == p or name.startswith(p + '.') for p in _STUB):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_stubbed_modules_snapshot = _snapshot_stubbed_modules()
_clear_stubbed_modules()
_remove_python_multipart_stub = _install_python_multipart_stub()
sys.meta_path.insert(0, _finder)
try:
    from routers import apps as apps_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)


def _change_visibility(approved, private):
    """Drive change_app_visibility for an owned app with the given approved/private state.

    Returns (invalidate_list_called, delete_per_app_cache_called).
    """
    app_obj = MagicMock(uid='uid1', approved=approved)
    with patch.object(apps_mod, 'get_available_app_by_id', return_value={'id': 'app-1', 'uid': 'uid1'}), patch.object(
        apps_mod, 'App', return_value=app_obj
    ), patch.object(apps_mod, 'update_app_visibility_in_db') as update_db, patch.object(
        apps_mod, 'invalidate_approved_apps_cache'
    ) as invalidate, patch.object(
        apps_mod, 'delete_app_cache_by_id'
    ) as delete_cache:
        result = apps_mod.change_app_visibility('app-1', private, uid='uid1')

    assert result == {'status': 'ok'}
    update_db.assert_called_once_with('app-1', private)
    return invalidate.called, delete_cache.called


def test_making_approved_app_public_invalidates_list_cache():
    invalidate_called, delete_called = _change_visibility(approved=True, private=False)
    assert invalidate_called, 'approved app made public must refresh the public marketplace list cache'
    assert delete_called


def test_making_approved_app_private_invalidates_list_cache():
    invalidate_called, delete_called = _change_visibility(approved=True, private=True)
    assert invalidate_called, 'approved app made private must leave the public list immediately'
    assert delete_called


def test_unapproved_app_visibility_change_skips_list_cache():
    invalidate_called, delete_called = _change_visibility(approved=False, private=False)
    assert not invalidate_called, 'unapproved app is not in the public list, so no list invalidation needed'
    assert delete_called, 'the per-app cache is always invalidated'
