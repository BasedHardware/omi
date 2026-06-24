"""GET /v1/calendar/meetings must clamp the limit so a negative/oversized value can't reach Firestore.

list_calendar_meetings passed the raw limit straight into the Firestore .limit() call, so ?limit=-5 hit
calendar_db.list_meetings with a negative limit (Firestore raises ValueError -> 500). routers/
calendar_meetings.py has a heavy import graph, so we import it under a stub finder, then call the endpoint
directly.
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
    from routers import calendar_meetings as cm_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)

_NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _valid(eid):
    return {'calendar_event_id': eid, 'title': 'Standup', 'start_time': _NOW, 'duration_minutes': 30}


def test_negative_limit_is_clamped():
    db = MagicMock(return_value=[])
    with patch.object(cm_mod.calendar_db, 'list_meetings', db):
        cm_mod.list_calendar_meetings(uid='uid1', start_date=None, end_date=None, limit=-5)
    assert db.call_args.kwargs['limit'] == 1


def test_oversized_limit_is_clamped():
    db = MagicMock(return_value=[])
    with patch.object(cm_mod.calendar_db, 'list_meetings', db):
        cm_mod.list_calendar_meetings(uid='uid1', start_date=None, end_date=None, limit=10_000)
    assert db.call_args.kwargs['limit'] == 1000
