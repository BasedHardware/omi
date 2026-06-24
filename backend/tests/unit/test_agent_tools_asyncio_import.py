"""Regression test for routers/agent_tools.py missing `import asyncio`.

`_start_vm_and_wait` calls `await asyncio.sleep(...)` on its VM-restart path, but
`asyncio` was never imported at module level (only `from datetime import ...`). The
reachable path therefore raised `NameError: name 'asyncio' is not defined`.

Two complementary checks, both red-before / green-after:
  1. Source-assert: the module text contains a top-level `import asyncio`.
  2. Functional: drive `_start_vm_and_wait` to the first `await asyncio.sleep(...)`
     call site. With the import missing this raises NameError; with the import
     present it resolves `asyncio` and hits our patched sleep sentinel instead.
"""

import asyncio as _real_asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import inspect
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

_STUB = (
    'database',
    'utils',
    'firebase_admin',
    'google',
    'pinecone',
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'langchain_core',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
    'httpx',
)


def _is(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


class _AM(types.ModuleType):
    __path__ = []

    def __getattr__(s, n):
        if n.startswith('__') and n.endswith('__'):
            raise AttributeError(n)
        m = MagicMock()
        setattr(s, n, m)
        return m


class _F(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(s, n, p=None, t=None):
        return importlib.machinery.ModuleSpec(n, s, is_package=True) if _is(n) else None

    def create_module(s, sp):
        return _AM(sp.name)

    def exec_module(s, m):
        pass


_f = _F()
_sav = {n: m for n, m in sys.modules.items() if _is(n)}
for n in list(sys.modules):
    if _is(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from routers import agent_tools as mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is(n) and n not in _sav:
            sys.modules.pop(n, None)
    sys.modules.update(_sav)


def test_module_imports_asyncio_at_top_level():
    """Source-assert: the fix adds a module-level `import asyncio`."""
    src = inspect.getsource(mod)
    assert 'import asyncio' in src, "agent_tools.py must import asyncio at module top"
    # asyncio must be resolvable as a module attribute (the actual stdlib module).
    assert getattr(mod, 'asyncio', None) is _real_asyncio


class _ReachedSleep(Exception):
    """Sentinel: raised from the patched asyncio.sleep to prove the path resolved."""


class _FakeResp:
    status_code = 200

    @staticmethod
    def json():
        return {"name": "op-123"}


class _FakeAsyncClient:
    """Minimal async context manager standing in for httpx.AsyncClient."""

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, *a, **k):
        return _FakeResp()

    async def get(self, *a, **k):
        return _FakeResp()


def test_start_vm_and_wait_reaches_sleep_without_nameerror():
    """The VM-restart path must reach `await asyncio.sleep(...)` without NameError.

    Pre-fix: line `await asyncio.sleep(5)` raises NameError (asyncio undefined) ->
    our _ReachedSleep is never raised -> test fails.
    Post-fix: asyncio resolves; the patched sleep raises _ReachedSleep -> test passes.
    """

    async def _boom(*a, **k):
        raise _ReachedSleep()

    async def _await_value(*a, **k):
        # Stand-in for run_blocking: returns the token coroutine-style.
        return "fake-token"

    # Patch the real asyncio.sleep so reaching it raises our sentinel instead of
    # actually sleeping. Once `import asyncio` exists, mod.asyncio IS this module.
    with patch.object(_real_asyncio, 'sleep', _boom), patch.object(mod, 'run_blocking', _await_value), patch.object(
        mod, 'httpx', MagicMock(AsyncClient=_FakeAsyncClient)
    ):
        with pytest.raises(_ReachedSleep):
            _real_asyncio.run(mod._start_vm_and_wait("vm-1", "us-central1-a"))
