"""add_mcp_server must not 500 when the user lookup returns None.

routers/apps.py has a very heavy import graph (langchain, utils.llm, stripe, ...), so we import it
under a stub finder that auto-mocks those namespaces (keeping models/fastapi/pydantic real), then
call add_mcp_server directly with its collaborators patched so get_user_from_uid yields None.

Without the `or {}` guard, `user.get('display_name', '')` raises AttributeError -> 500.
With the guard, `user` becomes {} and the endpoint returns its normal dict.
"""

import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


def _run_blocking_side_effect(executor, func, *args, **kwargs):
    """Mimic run_blocking: actually invoke the offloaded sync fn (here, the patched mocks)."""
    return func(*args, **kwargs)


def _call(user_value):
    """Drive add_mcp_server through the no-OAuth branch with the user lookup returning user_value."""
    data = apps_mod.McpServerRequest(name='Test MCP', mcp_server_url='https://mcp.example.com')

    tool = MagicMock()
    tool.endpoint = 'https://mcp.example.com/http'
    tool.name = 'do_thing'
    tool.model_dump.return_value = {'name': 'do_thing', 'parameters': None, 'endpoint': 'https://mcp.example.com/http'}

    with patch.object(apps_mod, 'get_user_from_uid', return_value=user_value), patch.object(
        apps_mod, 'run_blocking', new=AsyncMock(side_effect=_run_blocking_side_effect)
    ), patch.object(apps_mod, 'fetch_brandfetch_logo', new=AsyncMock(return_value='')), patch.object(
        apps_mod, 'discover_oauth_metadata', new=AsyncMock(return_value=None)
    ), patch.object(
        apps_mod, 'discover_mcp_tools', new=AsyncMock(return_value=[tool])
    ), patch.object(
        apps_mod, 'add_app_to_db'
    ):
        return asyncio.run(apps_mod.add_mcp_server(data, uid='u1'))


def test_user_none_does_not_500():
    # Red on current code: get_user_from_uid -> None -> user.get(...) AttributeError -> 500.
    result = _call(None)
    assert result['app_id']
    assert result['requires_oauth'] is False


def test_user_present_still_works():
    result = _call({'display_name': 'Jane', 'email': 'jane@example.com'})
    assert result['app_id']
    assert result['requires_oauth'] is False
