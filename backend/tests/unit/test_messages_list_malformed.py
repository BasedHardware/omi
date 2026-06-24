"""GET /v2/messages must skip a malformed message instead of 500ing the whole list.

The endpoint returned raw dicts under response_model=List[Message], so one malformed/legacy record 500'd
the whole page. We patch the Message model with a simple stand-in to exercise the skip loop. routers/
chat.py has a heavy import graph, so we import it under a stub finder.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

from pydantic import BaseModel

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
    from routers import chat as chat_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)
    if _rm:
        sys.modules.pop('python_multipart', None)


class _FakeMsg(BaseModel):
    id: str


def test_malformed_message_skipped_not_500():
    page = [{'id': 'm1'}, {}, {'id': 'm2'}]
    with patch.object(chat_mod, 'Message', _FakeMsg), patch.object(
        chat_mod.chat_db, 'get_chat_session', return_value=None
    ), patch.object(chat_mod.chat_db, 'get_messages', return_value=page):
        result = chat_mod.get_messages(plugin_id=None, app_id=None, uid='u1')
    assert [m.id for m in result] == ['m1', 'm2']
