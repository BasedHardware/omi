"""create_persona must not 500 with AttributeError when the user lookup returns None.

routers/apps.py has a very heavy import graph (langchain, utils.llm, stripe, ...), so we import it
under a stub finder that auto-mocks those namespaces (keeping models/fastapi/pydantic real), then
call create_persona directly with its collaborators patched and get_user_from_uid returning None.

Without the fix, `user = await run_blocking(db_executor, get_user_from_uid, uid)` is None and the
next line `user.get('display_name', '')` raises AttributeError (-> 500). With the guard (`or {}`)
the handler proceeds cleanly.
"""

import asyncio
import importlib.abc
import importlib.machinery
import importlib.util
import json
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


class _FakeUpload:
    """Minimal stand-in for fastapi UploadFile used by create_persona."""

    filename = 'avatar.png'

    async def read(self):
        return b'imgbytes'


def _run_create_persona(user_value):
    """Drive create_persona end to end with get_user_from_uid returning ``user_value``.

    run_blocking is the only async-offload primitive in the function; we make it execute the
    wrapped sync collaborator but force the get_user_from_uid result to ``user_value`` so we can
    exercise the None-user branch. generate_persona_prompt is awaited directly, so it gets its own
    async stub. AppCreate / file IO / db writes are stubbed so only the user-dereference is tested.
    """

    async def fake_run_blocking(executor, func, *args):
        if func is apps_mod.get_user_from_uid:
            return user_value
        if func is apps_mod.increment_username:
            return args[0]
        # save_username / _write_file / add_app_to_db / generate_persona_desc, etc.
        return MagicMock()

    async def fake_generate_persona_prompt(uid, data):
        return 'prompt'

    persona_data = json.dumps({'name': 'Ada', 'username': 'ada', 'connected_accounts': ['omi']})

    fake_app_create = MagicMock()
    fake_app_create.model_dump.return_value = {}

    with patch.object(apps_mod, 'run_blocking', side_effect=fake_run_blocking), patch.object(
        apps_mod, 'get_user_from_uid', MagicMock()
    ), patch.object(apps_mod, 'increment_username', MagicMock()), patch.object(
        apps_mod, 'save_username', MagicMock()
    ), patch.object(
        apps_mod, 'generate_persona_prompt', side_effect=fake_generate_persona_prompt
    ), patch.object(
        apps_mod, 'generate_persona_desc', MagicMock()
    ), patch.object(
        apps_mod, '_write_file', MagicMock()
    ), patch.object(
        apps_mod, 'upload_app_logo', MagicMock(return_value='http://img')
    ), patch.object(
        apps_mod, 'add_app_to_db', MagicMock()
    ), patch.object(
        apps_mod.AppCreate, 'model_validate', return_value=fake_app_create
    ), patch.object(
        apps_mod.os, 'makedirs', MagicMock()
    ):
        return asyncio.run(apps_mod.create_persona(persona_data=persona_data, file=_FakeUpload(), uid='uid1'))


def test_create_persona_user_none_does_not_crash():
    """User lookup returning None must not raise AttributeError/TypeError (the bug)."""
    result = _run_create_persona(None)
    assert isinstance(result, dict)
    assert result['status'] == 'ok'
    # author/email degrade gracefully instead of crashing.
    assert result['app_id']


def test_create_persona_with_user_populates_author_email():
    """When the user exists, author/email still flow through (no regression)."""
    result = _run_create_persona({'display_name': 'Ada Lovelace', 'email': 'ada@example.com'})
    assert isinstance(result, dict)
    assert result['status'] == 'ok'
