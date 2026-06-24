"""GET /v2/messages/shared/{token} must return 404 (not 500) when the stored share record is malformed.

The public handler read share_data['uid'] / ['message_ids'] / ['display_name'] via direct subscript, so a
corrupted/legacy share record missing a key raised KeyError -> 500. routers/chat.py has a heavy import
graph, so we import it under a stub finder, then call the handler directly.
"""

import importlib.abc
import importlib.machinery
import importlib.util
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
    from routers import chat as chat_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)

from fastapi import HTTPException  # noqa: E402


def test_share_missing_uid_returns_404():
    with patch.object(chat_mod, 'get_chat_share', return_value={'message_ids': ['m1'], 'display_name': 'X'}):
        with pytest.raises(HTTPException) as e:
            chat_mod.get_shared_chat_messages(token='t')
    assert e.value.status_code == 404


def test_share_missing_message_ids_returns_404():
    with patch.object(chat_mod, 'get_chat_share', return_value={'uid': 'u1', 'display_name': 'X'}):
        with pytest.raises(HTTPException) as e:
            chat_mod.get_shared_chat_messages(token='t')
    assert e.value.status_code == 404


def test_valid_share_returns_response():
    with patch.object(
        chat_mod, 'get_chat_share', return_value={'uid': 'u1', 'message_ids': ['m1'], 'display_name': 'X'}
    ), patch.object(chat_mod.chat_db, 'get_message', return_value=None):
        result = chat_mod.get_shared_chat_messages(token='t')
    assert result['sender_name'] == 'X'
    assert result['count'] == 0
