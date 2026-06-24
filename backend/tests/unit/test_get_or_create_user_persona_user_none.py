"""get_or_create_user_persona must not 500 when the user lookup returns None.

routers/apps.py has a very heavy import graph (langchain, utils.llm, stripe, ...), so we import it
under a stub finder that auto-mocks those namespaces (keeping models/fastapi/pydantic real), then
call get_or_create_user_persona directly with its collaborators patched.

On current (unfixed) code, get_user_from_uid returning None makes the subsequent user.get(...)
dereference raise AttributeError -> HTTP 500. The fix (`... or {}`) lets the handler complete.
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


async def _run_blocking_sync(executor, fn, *args):
    """Stand-in for utils.executors.run_blocking that runs the callable inline."""
    return fn(*args)


def _drive_no_existing_persona():
    """Drive get_or_create_user_persona with no pre-existing persona and get_user_from_uid -> None."""
    with patch.object(apps_mod, 'run_blocking', side_effect=_run_blocking_sync), patch.object(
        apps_mod, 'get_user_persona_by_uid', return_value=None
    ), patch.object(apps_mod, 'get_user_from_uid', return_value=None), patch.object(
        apps_mod, 'increment_username', return_value='mypersona'
    ), patch.object(
        apps_mod, 'save_username'
    ), patch.object(
        apps_mod, 'add_app_to_db'
    ), patch.object(
        apps_mod, 'generate_persona_prompt', new=AsyncMock(return_value='prompt')
    ), patch.object(
        apps_mod.AppCreate, 'model_validate', return_value=MagicMock(model_dump=MagicMock(return_value={}))
    ):
        return asyncio.run(apps_mod.get_or_create_user_persona(uid='u1'))


def test_user_lookup_none_does_not_500():
    # Must not raise AttributeError/TypeError when the user lookup returns None.
    result = _drive_no_existing_persona()
    assert isinstance(result, dict)
    # The persona dict is still well-formed despite the missing user.
    assert result['uid'] == 'u1'
    assert result['email'] == ''
    assert result['author'] == ''
