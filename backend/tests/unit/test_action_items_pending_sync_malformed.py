"""GET /v1/action-items/pending-sync must skip a malformed action item instead of 500ing the whole page.

get_pending_sync_items built ActionItemResponse(**item) directly in a list comprehension for both
pending_export and synced_items. ActionItemResponse requires 'description' and 'completed' (no defaults),
so one legacy/malformed doc raised ValidationError that 500'd the endpoint and dropped ALL of the user's
sync items. The fix wraps each record in a per-item try/except (mirroring get_conversation_action_items).
routers/action_items.py has a heavy import graph, so we import it under a stub finder, then call the
handler directly.
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


def test_pending_sync_skips_malformed_not_500():
    # 'completed' is required on ActionItemResponse with no default -> a doc missing it raises
    # ValidationError. Both lists contain one valid + one malformed record.
    good_pending = _valid('p1')
    bad_pending = {'id': 'p2', 'description': 'missing completed'}
    good_synced = _valid('s1', completed=True)
    bad_synced = {'id': 's2', 'description': 'missing completed'}

    result = {
        'pending_export': [good_pending, bad_pending],
        'synced_items': [good_synced, bad_synced],
    }

    with patch.object(ai_mod.action_items_db, 'get_pending_apple_reminders_sync', return_value=result):
        resp = ai_mod.get_pending_sync_items(platform='apple_reminders', uid='uid1')

    # Only the valid records survive in each list; the malformed ones are skipped, not a 500.
    assert [i.id for i in resp['pending_export']] == ['p1']
    assert [i.id for i in resp['synced_items']] == ['s1']
