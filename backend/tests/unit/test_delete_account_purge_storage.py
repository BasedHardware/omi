"""Regression test for issue #5088 — account deletion must purge derived data outside Firestore.

Before the fix, _background_wipe_user_data only cleaned Twilio + Firestore, leaving the user's
Pinecone vectors and GCS conversation recordings behind. The wipe now enumerates IDs (before the
Firestore delete removes them) and purges Pinecone (conversations/memories/action-items/screen-
activity) + recordings. Required derived purge failures block the Firestore wipe so deleted
Firestore IDs do not hide leftover vectors; best-effort recording failures do not block it.

routers/users.py has a heavy import graph, so we install a meta-path finder that auto-stubs the
database/utils/external namespaces, import routers.users, then drive _background_wipe_user_data
with the collaborators patched.
"""

import importlib.abc
import importlib.machinery
import os
import sys
import types
from unittest.mock import MagicMock, patch

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault(
    'ENCRYPTION_SECRET',
    'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv',
)


class _AutoMockModule(types.ModuleType):
    __path__ = []  # behave as a package so submodule imports resolve to stubs

    def __getattr__(self, name):
        if name.startswith('__') and name.endswith('__'):
            raise AttributeError(name)
        mock = MagicMock()
        setattr(self, name, mock)
        return mock


_STUB_PREFIXES = (
    'database',
    'utils',
    'firebase_admin',
    'google.cloud',
    'google.api_core',
    'pinecone',
    'typesense',
    'opuslib',
    'pydub',
    'pusher',
    'modal',
    'ulid',
    'pytz',
    'twilio',
)


def _should_stub(name: str) -> bool:
    if name == 'utils.other.endpoints':  # provided as a real shim below
        return False
    return any(name == p or name.startswith(p + '.') for p in _STUB_PREFIXES)


def _remove_module_tree(prefix: str) -> None:
    for name in list(sys.modules):
        if name == prefix or name.startswith(prefix + '.'):
            sys.modules.pop(name, None)


for _prefix in _STUB_PREFIXES:
    _remove_module_tree(_prefix)


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self):
        self.created = set()

    def find_spec(self, name, path=None, target=None):
        if _should_stub(name):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        self.created.add(spec.name)
        return _AutoMockModule(spec.name)

    def exec_module(self, module):
        pass


_finder = _StubFinder()
sys.meta_path.insert(0, _finder)

_endpoints = types.ModuleType('utils.other.endpoints')
_endpoints.get_current_user_uid = lambda: 'uid1'
_endpoints.with_rate_limit = lambda dependency, _policy: dependency
_endpoints.delete_account = MagicMock()
_endpoints.get_user = MagicMock()
sys.modules['utils.other.endpoints'] = _endpoints

try:
    import firebase_admin.auth as _fa_auth  # stubbed

    _fa_auth.InvalidIdTokenError = type('InvalidIdTokenError', (Exception,), {})
    from services.users import account_deletion as users_service  # noqa: E402  (deps stubbed above)
finally:
    if _finder in sys.meta_path:
        sys.meta_path.remove(_finder)
    for _name in list(_finder.created) + ['utils.other.endpoints']:
        sys.modules.pop(_name, None)


def _purge_patches(**overrides):
    """Patch every purge collaborator on the users service. overrides set return_value/side_effect."""
    enumerators = {
        'get_conversation_ids': ['c1', 'c2'],
        'get_memory_ids': ['m1'],
        'get_action_item_ids': ['a1', 'a2'],
        'get_screen_activity_ids': ['s1'],
    }
    patchers = {}
    # create=True: some collaborators are pulled into users.py via `from database.users import *`,
    # which doesn't bind names on the stubbed module, so the attribute may not pre-exist here.
    for name, ids in enumerators.items():
        patchers[name] = patch.object(
            users_service, name, create=True, **(overrides.get(name) or {'return_value': ids})
        )
    for name in (
        'delete_conversation_vectors_batch',
        'delete_transcript_chunk_vectors_batch',
        'delete_memory_vectors_batch',
        'delete_action_item_vectors_batch',
        'delete_screen_activity_vectors',
        'delete_all_conversation_recordings',
        'delete_user_caller_ids',
    ):
        patchers[name] = patch.object(users_service, name, create=True, **(overrides.get(name) or {}))
    patchers['delete_user_data'] = patch.object(
        users_service.users_db, 'delete_user_data', create=True, **(overrides.get('delete_user_data') or {})
    )
    for name in (
        'mark_user_deletion_wipe_running',
        'mark_user_deletion_wipe_failed',
        'mark_user_deletion_wipe_completed',
    ):
        patchers[name] = patch.object(users_service.users_db, name, create=True, **(overrides.get(name) or {}))
    started = {name: p.start() for name, p in patchers.items()}
    return patchers, started


def _stop(patchers):
    for p in patchers.values():
        p.stop()


def test_purge_runs_all_backends_before_firestore_wipe():
    patchers, m = _purge_patches()
    try:
        users_service.background_wipe_user_data('uid1')
    finally:
        _stop(patchers)

    # Pinecone: one batched call per namespace (no per-item loop to abandon on a transient failure)
    m['delete_conversation_vectors_batch'].assert_called_once_with('uid1', ['c1', 'c2'])
    m['delete_memory_vectors_batch'].assert_called_once_with('uid1', ['m1'])
    m['delete_action_item_vectors_batch'].assert_called_once_with('uid1', ['a1', 'a2'])
    m['delete_screen_activity_vectors'].assert_called_once_with('uid1', ['s1'])
    # GCS + Firestore
    m['delete_all_conversation_recordings'].assert_called_once_with('uid1')
    m['delete_user_data'].assert_called_once_with('uid1')


def test_id_enumeration_happens_before_firestore_wipe():
    # Enumerators must run before delete_user_data removes the docs that hold the IDs.
    order = []
    patchers, m = _purge_patches(
        get_conversation_ids={'side_effect': lambda uid: order.append('enumerate') or ['c1']},
        delete_user_data={'side_effect': lambda uid: order.append('wipe')},
    )
    try:
        users_service.background_wipe_user_data('uid1')
    finally:
        _stop(patchers)
    assert order == ['enumerate', 'enumerate', 'wipe'], order


def test_pinecone_failure_blocks_firestore_wipe_but_not_best_effort_recordings():
    patchers, m = _purge_patches(delete_conversation_vectors_batch={'side_effect': Exception('pinecone down')})
    try:
        users_service.background_wipe_user_data('uid1')
    finally:
        _stop(patchers)
    # Required vector purge failure must not stop other derived purges, but it
    # must block Firestore deletion because Firestore holds the retryable IDs.
    m['delete_memory_vectors_batch'].assert_called_once()
    m['delete_all_conversation_recordings'].assert_called_once_with('uid1')
    m['delete_user_data'].assert_not_called()
    m['mark_user_deletion_wipe_failed'].assert_called_with('uid1')
    m['mark_user_deletion_wipe_completed'].assert_not_called()


def test_gcs_failure_does_not_block_firestore_wipe():
    patchers, m = _purge_patches(delete_all_conversation_recordings={'side_effect': Exception('gcs down')})
    try:
        users_service.background_wipe_user_data('uid1')
    finally:
        _stop(patchers)
    m['delete_all_conversation_recordings'].assert_called_once_with('uid1')  # purge was wired + attempted
    m['delete_user_data'].assert_called_once_with('uid1')  # and the failure didn't block the wipe


def test_enumeration_failure_blocks_firestore_wipe():
    patchers, m = _purge_patches(get_conversation_ids={'side_effect': Exception('firestore read error')})
    try:
        users_service.background_wipe_user_data('uid1')
    finally:
        _stop(patchers)
    # conversation enumeration blew up, but the other backends still run
    m['delete_memory_vectors_batch'].assert_called_once_with('uid1', ['m1'])
    m['delete_all_conversation_recordings'].assert_called_once_with('uid1')
    m['delete_user_data'].assert_not_called()
    m['mark_user_deletion_wipe_failed'].assert_called_with('uid1')
