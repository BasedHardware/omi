"""DELETE /v1/folders/{id}?move_to_folder_id=X must validate the target folder exists.

Before the fix, delete_folder passed an unvalidated client-supplied move_to_folder_id straight into
folders_db.delete_folder, which re-points conversations onto a non-existent folder and then calls
folder_ref.update() on a missing doc -> Firestore NotFound -> unhandled 500 (and orphaned conversations).

The fix mirrors move_conversation_to_folder: look up the target with folders_db.get_folder first and
raise HTTPException(404) if it is missing, before delegating to the DB layer.

routers/folders.py has a heavy import graph, so we import it under a stub finder (same pattern as
test_folder_conversations_malformed.py).
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

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


class _SimulatedNotFound(Exception):
    """Stands in for google.cloud.exceptions.NotFound raised by folder_ref.update() on a missing doc."""


def test_delete_folder_missing_target_returns_404_not_unhandled():
    source_folder = {'id': 'f-src', 'is_system': False}

    # First get_folder call resolves the folder being deleted; the second (target lookup, only
    # reached once the fix is in place) reports the client-supplied target as missing.
    get_folder_mock = MagicMock(side_effect=[source_folder, None])

    # Without the fix the handler skips the target check and calls into the DB layer, which on a
    # non-existent folder hits folder_ref.update() and raises a NotFound -> unhandled 500.
    delete_folder_mock = MagicMock(side_effect=_SimulatedNotFound('No document to update'))

    with patch.object(folders_mod.folders_db, 'get_folder', get_folder_mock), patch.object(
        folders_mod.folders_db, 'delete_folder', delete_folder_mock
    ):
        with pytest.raises(HTTPException) as exc_info:
            folders_mod.delete_folder(folder_id='f-src', move_to_folder_id='does-not-exist', uid='u1')

    # The fix converts the failure into a clean 404 BEFORE re-pointing/orphaning any conversations.
    assert exc_info.value.status_code == 404
    # And it must short-circuit before delegating to the DB delete (no orphaning).
    delete_folder_mock.assert_not_called()
