"""Partner integration tasks/memories endpoints must skip a malformed record, not 500 the page.

routers/integration.py pulls a heavy import chain (routers.conversations -> speaker_identification
-> av, langchain, ...), so we import it under a stub finder that auto-mocks those namespaces while
keeping models/fastapi/pydantic real (the real TaskItem/MemoryItem are what raise ValidationError on
a malformed record). Then we call the endpoints directly with the auth/capability gates patched.
"""

import importlib.abc
import importlib.machinery
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
    'av',
    'stripe',
    'openai',
    'anthropic',
    'redis',
    'sentry_sdk',
    'requests',
    'routers.conversations',  # pulls speaker_identification -> av; integration only needs 2 symbols
)


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
sys.meta_path.insert(0, _finder)
try:
    from routers import integration as integ
finally:
    sys.meta_path.remove(_finder)
    for _n in list(sys.modules):
        if any(_n == p or _n.startswith(p + '.') for p in _STUB):
            sys.modules.pop(_n, None)


def _setup_gates():
    integ.apps_db.get_app_by_id_db = MagicMock(return_value={'id': 'app-1', 'name': 'test'})
    integ.redis_db.get_enabled_apps = MagicMock(return_value=['app-1'])


def _call_tasks():
    return integ.get_tasks_via_integration(
        request=MagicMock(),
        app_id='app-1',
        uid='test-uid',
        limit=100,
        offset=0,
        completed=None,
        conversation_id=None,
        start_date=None,
        end_date=None,
        due_start_date=None,
        due_end_date=None,
        authorization='Bearer test-key',
    )


def _make_memory(memory_id='good'):
    return {
        'id': memory_id,
        'uid': 'test-uid',
        'is_locked': False,
        'content': 'a memory',
        'category': 'interesting',
        'created_at': '2024-01-01T00:00:00',
        'updated_at': '2024-01-01T00:00:00',
    }


def test_get_tasks_skips_malformed_record():
    valid = {'id': 'good', 'description': 'do x', 'completed': False, 'is_locked': False}
    malformed = {'id': 'bad', 'is_locked': False}  # missing required description/completed
    integ.action_items_db.get_action_items = MagicMock(return_value=[valid, malformed])
    _setup_gates()

    with patch.object(integ, 'verify_api_key', return_value=True), patch.object(integ, 'apps_utils') as au:
        au.app_can_read_tasks.return_value = True
        result = _call_tasks()

    assert len(result['tasks']) == 1
    assert result['tasks'][0]['id'] == 'good'


def test_get_tasks_all_malformed_returns_empty():
    integ.action_items_db.get_action_items = MagicMock(return_value=[{'id': 'b1'}, {'id': 'b2'}])
    _setup_gates()

    with patch.object(integ, 'verify_api_key', return_value=True), patch.object(integ, 'apps_utils') as au:
        au.app_can_read_tasks.return_value = True
        result = _call_tasks()

    assert result['tasks'] == []


def test_get_memories_skips_malformed_record():
    valid = _make_memory('good')
    malformed = {'id': 'bad', 'is_locked': False}  # missing required uid/created_at/content
    integ.memory_db.get_memories = MagicMock(return_value=[valid, malformed])
    _setup_gates()

    with patch.object(integ, 'verify_api_key', return_value=True), patch.object(integ, 'apps_utils') as au:
        au.app_can_read_memories.return_value = True
        result = integ.get_memories_via_integration(
            request=MagicMock(),
            app_id='app-1',
            uid='test-uid',
            limit=100,
            offset=0,
            authorization='Bearer test-key',
        )

    assert len(result['memories']) == 1
    assert result['memories'][0].id == 'good'


def _call_memories():
    return integ.get_memories_via_integration(
        request=MagicMock(),
        app_id='app-1',
        uid='test-uid',
        limit=100,
        offset=0,
        authorization='Bearer test-key',
    )


def test_get_memories_all_malformed_returns_empty():
    integ.memory_db.get_memories = MagicMock(return_value=[{'id': 'b1'}, {'id': 'b2'}])
    _setup_gates()

    with patch.object(integ, 'verify_api_key', return_value=True), patch.object(integ, 'apps_utils') as au:
        au.app_can_read_memories.return_value = True
        result = _call_memories()

    assert result['memories'] == []
