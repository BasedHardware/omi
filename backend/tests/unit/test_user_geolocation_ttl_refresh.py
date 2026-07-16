"""Regression: a stationary user's cached geolocation must not expire.

set_user_geolocation dedups repeated submissions of the same coordinates (rounded to 4 decimals)
by returning early. Before the fix it returned without touching the cache, so the 30-minute TTL set
at the last real move was never refreshed. A phone's foreground task re-sends the same location every
~5 minutes while stationary, all of which were deduped, so after 30 minutes the key expired and every
conversation / daily-recap created afterward got no location (issue #9782). The unchanged path now
refreshes the TTL. routers/users.py has a heavy import graph, so we import it under a stub finder and
call the handler directly.
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
        if _is_stubbed_name(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_finder = _Finder()
_snap = _snapshot_stubbed_modules()
_clear_stubbed_modules()
_rm_mp = _install_python_multipart_stub()
sys.meta_path.insert(0, _finder)
try:
    from routers import users as users_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_snap)
    if _rm_mp:
        sys.modules.pop('python_multipart', None)

from models.geolocation import Geolocation  # noqa: E402


def test_unchanged_location_refreshes_ttl_without_rewriting():
    cached = Geolocation(latitude=37.7749, longitude=-122.4194).model_dump()
    same = Geolocation(latitude=37.77491, longitude=-122.41939)  # within 4-decimal dedup window
    with patch.object(users_mod, 'get_cached_user_geolocation', return_value=cached), patch.object(
        users_mod, 'refresh_user_geolocation_ttl'
    ) as refresh, patch.object(users_mod, 'cache_user_geolocation') as cache:
        result = users_mod.set_user_geolocation(same, uid='u1')

    assert result['message'] == 'Location not changed significantly.'
    refresh.assert_called_once_with('u1')  # TTL kept alive so the location doesn't expire
    cache.assert_not_called()  # value unchanged, no rewrite


def test_changed_location_rewrites_cache():
    cached = Geolocation(latitude=37.7749, longitude=-122.4194).model_dump()
    moved = Geolocation(latitude=40.7128, longitude=-74.0060)
    with patch.object(users_mod, 'get_cached_user_geolocation', return_value=cached), patch.object(
        users_mod, 'refresh_user_geolocation_ttl'
    ) as refresh, patch.object(users_mod, 'cache_user_geolocation') as cache:
        result = users_mod.set_user_geolocation(moved, uid='u1')

    assert result == {'status': 'ok'}
    cache.assert_called_once()  # new coordinates written (which also resets the TTL)
    refresh.assert_not_called()
