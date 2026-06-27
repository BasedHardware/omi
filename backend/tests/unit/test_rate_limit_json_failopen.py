"""rate_limit_custom must fail open (not 500) when its cache entry is corrupt.

It did current = json.loads(cached.get(key)) then current['remaining']/['timestamp'] with no guard, so a
corrupt or partial cache entry raised JSONDecodeError/KeyError -> HTTP 500 on any rate-limited endpoint.
utils/other/endpoints.py has a heavy import graph, so we import it under a stub finder.
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
    'utils.other.auth',
    'firebase_admin',
    'google',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'redis',
    'sentry_sdk',
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
    from utils.other import endpoints as ep_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


def _req():
    r = MagicMock()
    r.client.host = '1.2.3.4'
    return r


def test_corrupt_cache_fails_open_not_500():
    with patch.object(ep_mod, 'cached', {'rate_limit:ep:1.2.3.4': 'not valid json{'}):
        result = ep_mod.rate_limit_custom('ep', _req(), 60, 60)
    assert result is True


def test_partial_cache_entry_fails_open():
    with patch.object(ep_mod, 'cached', {'rate_limit:ep:1.2.3.4': '{"foo": 1}'}):  # missing remaining/timestamp
        result = ep_mod.rate_limit_custom('ep', _req(), 60, 60)
    assert result is True
