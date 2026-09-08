"""validate_and_consume_oauth_state must consume an OAuth state atomically (single-use).

The consume previously did GET then DELETE. Once it is offloaded to the db_executor thread pool, two
concurrent callbacks carrying the same state can both read the value before either delete runs, which
weakens replay protection. It now uses an atomic Redis GETDEL, so only one caller ever receives the
value and a second consume of the same state returns None.

routers/integrations.py has a heavy import graph, so it is imported under a stub finder that
auto-mocks those namespaces (keeping models/fastapi/pydantic real), then the helper is called
directly with the redis client patched.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import json
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
    from routers import integrations as integ
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


def test_consume_uses_atomic_getdel_not_get_then_delete():
    fake_r = MagicMock()
    fake_r.getdel.return_value = json.dumps({'uid': 'u1', 'app_key': 'a1'}).encode()
    with patch.object(integ.redis_db, 'r', fake_r):
        result = integ.validate_and_consume_oauth_state('tok')

    assert result == {'uid': 'u1', 'app_key': 'a1'}
    # One atomic operation -- not a separate GET then DELETE that two callbacks could interleave.
    fake_r.getdel.assert_called_once_with('oauth_state:tok')
    fake_r.get.assert_not_called()
    fake_r.delete.assert_not_called()


def test_consume_is_single_use():
    # Two consumes of the same state (e.g. concurrent same-state callbacks): only the first wins,
    # because GETDEL removes the value atomically on the first read.
    store = {'oauth_state:tok': json.dumps({'uid': 'u1', 'app_key': 'a1'}).encode()}
    fake_r = MagicMock()
    fake_r.getdel.side_effect = lambda key: store.pop(key, None)

    with patch.object(integ.redis_db, 'r', fake_r):
        first = integ.validate_and_consume_oauth_state('tok')
        second = integ.validate_and_consume_oauth_state('tok')

    assert first == {'uid': 'u1', 'app_key': 'a1'}
    assert second is None
