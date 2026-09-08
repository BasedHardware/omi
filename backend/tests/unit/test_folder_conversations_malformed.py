"""GET /v1/folders/{id}/conversations must skip a malformed conversation instead of 500ing the list.

The endpoint returned raw dicts under response_model=List[Conversation], so one malformed/legacy record
500'd the whole list. We patch the Conversation model with a simple stand-in to exercise the skip loop.
routers/folders.py has a heavy import graph, so we import it under a stub finder.
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
    from routers import folders as folders_mod
finally:
    sys.meta_path.remove(_finder)
    _restore(_snap)


class _FakeConv(BaseModel):
    id: str


def test_malformed_conversation_skipped_not_500():
    page = [{'id': 'c1'}, {}, {'id': 'c2'}]  # middle one missing required id
    with patch.object(folders_mod, 'Conversation', _FakeConv), patch.object(
        folders_mod.folders_db, 'get_folder', return_value={'id': 'f1'}
    ), patch.object(folders_mod.folders_db, 'get_conversations_in_folder', return_value=page), patch.object(
        folders_mod, 'redact_conversations_for_list', lambda x: None
    ):
        result = folders_mod.get_folder_conversations(
            folder_id='f1', limit=100, offset=0, include_discarded=False, uid='u1'
        )
    assert [c.id for c in result] == ['c1', 'c2']
