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


def test_get_import_jobs_firestore_exception_handled():
    with patch.object(
        imports_mod.import_jobs_db,
        'get_import_jobs',
        side_effect=RuntimeError('Firestore transport failure'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            imports_mod.get_import_jobs(uid='u1', limit=50)
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to retrieve import jobs'


def test_get_import_job_status_firestore_exception_handled():
    with patch.object(
        imports_mod.import_jobs_db,
        'get_import_job',
        side_effect=RuntimeError('Database read error'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            imports_mod.get_import_job_status(job_id='job-123', uid='u1')
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to retrieve import job status'


def test_cancel_import_job_update_exception_handled():
    mock_job = {'id': 'job-123', 'uid': 'u1', 'status': 'pending'}
    with patch.object(imports_mod.import_jobs_db, 'get_import_job', return_value=mock_job):
        with patch.object(
            imports_mod.import_jobs_db,
            'update_import_job',
            side_effect=RuntimeError('Database write error'),
        ):
            with pytest.raises(HTTPException) as exc_info:
                imports_mod.cancel_import_job(job_id='job-123', uid='u1')
            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == 'Failed to cancel import job'


def test_delete_import_job_exception_handled():
    mock_job = {'id': 'job-123', 'uid': 'u1', 'status': 'completed'}
    with patch.object(imports_mod.import_jobs_db, 'get_import_job', return_value=mock_job):
        with patch.object(
            imports_mod.import_jobs_db,
            'delete_import_job',
            side_effect=RuntimeError('Database delete error'),
        ):
            with pytest.raises(HTTPException) as exc_info:
                imports_mod.delete_import_job(job_id='job-123', uid='u1')
            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == 'Failed to delete import job'
