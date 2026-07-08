"""get_import_job_status must not 500 when a stored job has an out-of-enum status.

routers/imports.py pulls in database.* and utils.* (Firestore SDK, executors, ...), so we import it
under a meta-path stub finder that auto-mocks those namespaces while keeping models/fastapi/pydantic
real (we need the genuine ImportJobStatus enum + ImportJobResponse). Then we patch the single-job
getter to return a job whose stored status is bogus and call get_import_job_status directly.

Without the fix, ImportJobStatus(job['status']) raises ValueError -> 500. With the fix the status is
coerced to ImportJobStatus.failed and a normal ImportJobResponse is returned.
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
    'opuslib',
    'pydub',
    'redis',
    'langchain',
    'stripe',
    'openai',
    'anthropic',
    'modal',
    'ulid',
    'sentry_sdk',
    'requests',
    'typesense',
    'pusher',
)


def _is_stubbed(n):
    return any(n == p or n.startswith(p + '.') for p in _STUB)


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
        return importlib.machinery.ModuleSpec(name, self, is_package=True) if _is_stubbed(name) else None

    def create_module(self, spec):
        return _AutoMock(spec.name)

    def exec_module(self, module):
        pass


_f = _Finder()
_saved = {n: m for n, m in sys.modules.items() if _is_stubbed(n)}
for n in list(sys.modules):
    if _is_stubbed(n):
        sys.modules.pop(n, None)
sys.meta_path.insert(0, _f)
try:
    from routers import imports as imports_mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)

from models.import_job import ImportJobStatus  # noqa: E402


def _job_with_status(status):
    return {
        'id': 'job-1',
        'uid': 'u1',
        'status': status,
        'total_files': 3,
        'processed_files': 1,
        'conversations_created': 0,
        'created_at': None,
        'error': None,
    }


def _call(status):
    job = _job_with_status(status)
    with patch.object(imports_mod.import_jobs_db, 'get_import_job', return_value=job):
        return imports_mod.get_import_job_status('job-1', uid='u1')


def test_bogus_status_is_coerced_to_failed():
    # Out-of-enum stored status must degrade to failed, not 500 the request.
    resp = _call('bogus')
    assert resp.status == ImportJobStatus.failed
    assert resp.job_id == 'job-1'


def test_missing_status_is_coerced_to_failed():
    resp = _call(None)
    assert resp.status == ImportJobStatus.failed


def test_valid_status_is_preserved():
    resp = _call('completed')
    assert resp.status == ImportJobStatus.completed
