"""GET /v3/memories must clamp limit/offset so an out-of-range value can't 500 the request.

The endpoint passed limit/offset straight to Firestore .limit()/.offset(), which raise on a negative
argument, so /v3/memories?offset=-1 returned HTTP 500. routers/memories.py has a heavy import graph, so
we import it under a stub finder, then call get_memories directly with its db call mocked.
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
    from routers import memories as mem_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)


def _call(limit, offset):
    db = MagicMock(return_value=[])
    runtime = mem_mod.V3GetRuntime(enabled=False, source_decision='disabled')
    scope_request = types.SimpleNamespace(device_scope='all', client_device_id=None)
    with (
        patch.object(mem_mod.memories_db, 'get_memories', db),
        patch.object(mem_mod, 'canonical_read_enabled', return_value=False),
        patch.object(mem_mod, '_resolve_get_memories_device_scope', return_value=scope_request),
    ):
        mem_mod.get_memories(
            response=MagicMock(),
            limit=limit,
            offset=offset,
            uid='uid1',
            device_scope='all',
            client_device_id=None,
            x_app_platform=None,
            x_device_id_hash=None,
            memory_runtime=runtime,
        )
    # get_memories(uid, limit, offset)
    return db.call_args.args[1], db.call_args.args[2]


def test_negative_offset_is_clamped_not_500():
    _, offset = _call(50, -1)
    assert offset == 0


def test_huge_limit_is_capped():
    # offset != 0 so the first-page override does not apply; limit must be capped at 5000.
    limit, _ = _call(99999, 10)
    assert limit == 5000


def test_negative_limit_is_floored():
    limit, _ = _call(-5, 10)
    assert limit == 1
