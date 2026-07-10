"""The action-items list endpoints must skip a malformed item instead of 500ing the whole list.

Each built ActionItemResponse(**item) per item, so one malformed/legacy item (missing a required field
like 'completed') raised ValidationError and failed the whole response. A shared _safe_action_item_responses
helper now skips bad records. This covers the conversation list, the main list (GET /v1/action-items), and
search. routers/action_items.py has a heavy import graph, so we import it under a stub finder, then call the
endpoints directly.
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
    from routers import action_items as ai_mod
finally:
    sys.meta_path.remove(_finder)
    _restore_stubbed_modules(_stubbed_modules_snapshot)
    if _remove_python_multipart_stub:
        sys.modules.pop('python_multipart', None)


def _valid(aid, completed=False):
    return {'id': aid, 'description': 'do a thing', 'completed': completed}


def test_conversation_list_skips_malformed_not_500():
    bad = {'id': 'a2', 'description': 'missing completed'}  # missing required field -> ValidationError
    page = [_valid('a1'), bad]
    with patch.object(
        ai_mod.conversations_db, 'get_conversation', return_value={'id': 'c1', 'is_locked': False}
    ), patch.object(ai_mod.action_items_db, 'get_action_items_by_conversation', return_value=page):
        resp = ai_mod.get_conversation_action_items(conversation_id='c1', uid='uid1')
    assert [i.id for i in resp['action_items']] == ['a1']


def test_main_list_skips_malformed_not_500():
    bad = {'id': 'a2', 'description': 'missing completed'}  # missing required 'completed' -> ValidationError
    page = [_valid('a1'), bad]
    with patch.object(ai_mod.action_items_db, 'get_action_items', return_value=page):
        # Pass params explicitly: calling the handler directly leaves Query() defaults unresolved.
        resp = ai_mod.get_action_items(
            limit=50,
            offset=0,
            completed=None,
            conversation_id=None,
            start_date=None,
            end_date=None,
            due_start_date=None,
            due_end_date=None,
            uid='uid1',
        )
    assert [i.id for i in resp['action_items']] == ['a1']


def test_search_skips_malformed_not_500():
    bad = {'id': 'a2', 'description': 'missing completed'}
    page = [_valid('a1'), bad]
    with patch.object(ai_mod, 'search_action_items_by_vector', return_value=['a1', 'a2']), patch.object(
        ai_mod.action_items_db, 'get_action_items_by_ids', return_value=page
    ):
        resp = ai_mod.search_action_items(query='meeting', limit=10, uid='uid1')
    assert [i.id for i in resp['action_items']] == ['a1']
