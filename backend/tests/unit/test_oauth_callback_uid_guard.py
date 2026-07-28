"""The OAuth callback must not 500 when the consumed state record has no uid.

handle_oauth_callback read uid = state_data['uid'] via direct subscript, so a state record that passed the
app_key check but lacked uid raised KeyError -> 500. It now returns the normal invalid-state response.
routers/integrations.py has a heavy import graph, so we import it under a stub finder.
"""

import asyncio
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
_snap = _snapshot()
_clear()
_rm = _install_python_multipart_stub()
sys.meta_path.insert(0, _finder)
try:
    from routers import integrations as int_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)
    if _rm:
        sys.modules.pop('python_multipart', None)


def test_state_without_uid_returns_invalid_state_not_500():
    sentinel = object()

    # The state consume is offloaded via run_blocking; under the stub finder utils.executors is
    # auto-mocked, so run_blocking would return a MagicMock that cannot be awaited. Pass through
    # to the (patched) validate_and_consume_oauth_state so the handler sees the state record.
    async def _run_blocking(_executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    with patch.object(
        int_mod, 'validate_and_consume_oauth_state', return_value={'app_key': 'google_calendar'}
    ), patch.object(int_mod, 'render_oauth_response', return_value=sentinel) as render, patch.object(
        int_mod, 'run_blocking', _run_blocking
    ):
        result = asyncio.run(
            int_mod.handle_oauth_callback(
                request=MagicMock(), app_key='google_calendar', code='abc', state='xyz', provider_config=MagicMock()
            )
        )
    assert result is sentinel
    assert render.call_args.kwargs.get('error_type') == 'invalid_state'
