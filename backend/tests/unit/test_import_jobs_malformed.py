"""GET /v1/import/jobs must skip a malformed/legacy job instead of 500ing the whole list.

get_import_jobs built ImportJobResponse(job_id=job['id'], status=ImportJobStatus(job['status']), ...) per
job, so a job missing 'id' (KeyError) or holding a status value not in the enum (ValueError) failed the
whole page. routers/imports.py has a heavy import graph, so we import it under a stub finder that
auto-mocks those namespaces (keeping models real), then call get_import_jobs directly.
"""

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
    from routers import imports as imports_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)

_PENDING = imports_mod.ImportJobStatus.pending.value


def _get(page):
    with patch.object(imports_mod.import_jobs_db, 'get_import_jobs', return_value=page):
        return imports_mod.get_import_jobs(uid='uid1', limit=50)


def test_malformed_import_job_skipped_not_500():
    page = [
        {'id': 'j1', 'status': _PENDING},
        {'id': 'j2', 'status': 'not_a_real_status'},  # ValueError on enum
        {'status': _PENDING},  # KeyError on missing id
        {'id': 'j4', 'status': _PENDING},
    ]
    result = _get(page)
    assert [r.job_id for r in result] == ['j1', 'j4']


def test_all_valid_jobs_returned():
    page = [{'id': 'a', 'status': _PENDING}, {'id': 'b', 'status': _PENDING}]
    result = _get(page)
    assert [r.job_id for r in result] == ['a', 'b']


def test_limit_is_clamped_before_firestore():
    # get_import_jobs passed the request limit straight to get_import_jobs -> Firestore .limit(), so
    # ?limit=-1 raised (HTTP 500) and an oversized limit could stream the whole collection. Mirrors the
    # clamp the sibling dev-API list endpoints already apply.
    with patch.object(imports_mod.import_jobs_db, 'get_import_jobs', return_value=[]) as m:
        imports_mod.get_import_jobs(uid='uid1', limit=-1)
        imports_mod.get_import_jobs(uid='uid1', limit=99999)
        imports_mod.get_import_jobs(uid='uid1', limit=0)
    assert m.call_args_list[0].kwargs['limit'] == 1  # -1 -> 1
    assert m.call_args_list[1].kwargs['limit'] == 1000  # 99999 -> 1000
    assert m.call_args_list[2].kwargs['limit'] == 1  # 0 -> 1
