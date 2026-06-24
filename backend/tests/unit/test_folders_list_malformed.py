"""GET /v1/folders must skip a malformed folder instead of 500ing the whole list.

The endpoint returned raw dicts under response_model=List[Folder], so a folder missing a required field
(name/id/created_at/updated_at) 500'd the whole list. routers/folders.py has a heavy import graph, so we
import it under a stub finder, then call get_folders directly.
"""

import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys
import types
from datetime import datetime, timezone
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
    from routers import folders as folders_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _valid(fid, name):
    return {'id': fid, 'name': name, 'created_at': _NOW, 'updated_at': _NOW}


def test_malformed_folder_skipped_not_500():
    bad = {'id': 'f2', 'created_at': _NOW, 'updated_at': _NOW}  # missing required name
    page = [_valid('f1', 'Work'), bad, _valid('f3', 'Home')]
    with patch.object(folders_mod.folders_db, 'get_folders', return_value=page):
        result = folders_mod.get_folders(uid='u1')
    assert [f.id for f in result] == ['f1', 'f3']


def test_all_valid_folders_returned():
    page = [_valid('a', 'A'), _valid('b', 'B')]
    with patch.object(folders_mod.folders_db, 'get_folders', return_value=page):
        result = folders_mod.get_folders(uid='u1')
    assert [f.id for f in result] == ['a', 'b']
