"""get_import_jobs must not 500 when a stored job has an out-of-enum status.

routers/imports.py constructs ImportJobStatus(job['status']) for every job in the list. A job whose
persisted status is not one of {pending, processing, completed, failed} (or is missing) raises
ValueError and 500s the whole list endpoint. The fix coerces an unknown/missing status to
ImportJobStatus.failed inline at the call site, so the list still returns.

routers/imports.py pulls in heavy namespaces (database, utils, ...), so we import it under a stub
finder that auto-mocks those, keeping models/fastapi/pydantic real (we need the real ImportJobStatus
enum and ImportJobResponse validation), then call get_import_jobs directly with the jobs getter
patched.
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


def _is_stubbed(name):
    return any(name == p or name.startswith(p + '.') for p in _STUB)


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
_remove_multipart = _install_python_multipart_stub()
sys.meta_path.insert(0, _f)
try:
    from routers import imports as imports_mod
finally:
    sys.meta_path.remove(_f)
    for n in list(sys.modules):
        if _is_stubbed(n) and n not in _saved:
            sys.modules.pop(n, None)
    sys.modules.update(_saved)
    if _remove_multipart:
        sys.modules.pop('python_multipart', None)

from models.import_job import ImportJobStatus  # noqa: E402


def _job(job_id, status):
    return {
        'id': job_id,
        'uid': 'u1',
        'status': status,
        'total_files': 1,
        'processed_files': 1,
        'conversations_created': 0,
        'created_at': None,
        'error': None,
    }


def test_bogus_status_is_coerced_not_500():
    """A job with an out-of-enum status is returned (coerced to failed), not raised as ValueError."""
    jobs = [_job('good', 'completed'), _job('bad', 'bogus_status_value')]
    with patch.object(imports_mod.import_jobs_db, 'get_import_jobs', return_value=jobs):
        result = imports_mod.get_import_jobs(uid='u1', limit=50)

    assert len(result) == 2
    by_id = {r.job_id: r for r in result}
    assert by_id['good'].status == ImportJobStatus.completed
    assert by_id['bad'].status == ImportJobStatus.failed


def test_missing_status_is_coerced_not_500():
    """A job whose status is missing/None degrades to failed instead of raising."""
    job = {'id': 'nostat', 'uid': 'u1'}  # no 'status' key at all
    with patch.object(imports_mod.import_jobs_db, 'get_import_jobs', return_value=[job]):
        result = imports_mod.get_import_jobs(uid='u1', limit=50)

    assert len(result) == 1
    assert result[0].status == ImportJobStatus.failed
