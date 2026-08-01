"""validate_and_consume_oauth_state must consume an OAuth state atomically (single-use).

The consume previously did GET then DELETE. Once it is offloaded to the db_executor thread pool, two
concurrent callbacks carrying the same state can both read the value before either delete runs, which
weakens replay protection. It now uses an atomic Redis GETDEL, so only one caller ever receives the
value and a second consume of the same state returns None.

utils/x_connector.py had the same GET-then-DELETE shape and was not covered here, so it is
exercised too: one uncovered consume path is enough to reintroduce the replay window.

Both modules have a heavy import graph, so they are imported under a stub finder that
auto-mocks those namespaces (keeping models/fastapi/pydantic real), then the helpers are called
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


def _load_by_path(module_name, relative_path):
    """Load a module that lives inside a stubbed namespace, so its own code is real."""
    spec = importlib.util.spec_from_file_location(
        module_name, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), relative_path)
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        # Do not leave a stub-wired module behind for other test files in this process.
        sys.modules.pop(module_name, None)
    return module


try:
    from routers import integrations as integ

    x_conn = _load_by_path('utils.x_connector', 'utils/x_connector.py')
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


def test_x_connector_consume_uses_atomic_getdel_not_get_then_delete():
    fake_r = MagicMock()
    fake_r.getdel.return_value = b'u1\nverifier-1\nhttps://example.test/done'
    with patch.object(x_conn.redis_db, 'r', fake_r):
        result = x_conn.consume_oauth_state('tok')

    assert result == {'uid': 'u1', 'verifier': 'verifier-1', 'success_redirect_url': 'https://example.test/done'}
    fake_r.getdel.assert_called_once_with('x_oauth_state:tok')
    fake_r.get.assert_not_called()
    fake_r.delete.assert_not_called()


def test_x_connector_consume_is_single_use():
    store = {'x_oauth_state:tok': b'u1\nverifier-1\n'}
    fake_r = MagicMock()
    fake_r.getdel.side_effect = lambda key: store.pop(key, None)

    with patch.object(x_conn.redis_db, 'r', fake_r):
        first = x_conn.consume_oauth_state('tok')
        second = x_conn.consume_oauth_state('tok')

    assert first == {'uid': 'u1', 'verifier': 'verifier-1', 'success_redirect_url': ''}
    assert second is None
