from copy import deepcopy

import pytest
from google.api_core.exceptions import AlreadyExists

from database.memory_collections import MemoryCollections
from utils.memory.canonical_memory_onboarding import (
    CanonicalMemoryOnboardingValidationError,
    reconcile_canonical_memory_onboarding,
)
from utils.memory.v3.limited_rollout_config import build_whitelisted_user_control_state


class _Snapshot:
    def __init__(self, payload):
        self._payload = deepcopy(payload)
        self.exists = payload is not None

    def to_dict(self):
        return deepcopy(self._payload)


class _Document:
    def __init__(self, db, path):
        self.db = db
        self.path = path
        self.create_calls = []

    def get(self):
        self.db.read_paths.append(self.path)
        return _Snapshot(self.db.docs.get(self.path))

    def create(self, payload):
        self.create_calls.append(deepcopy(payload))
        self.db.create_paths.append(self.path)
        if self.path in self.db.docs:
            raise AlreadyExists('document already exists')
        self.db.docs[self.path] = deepcopy(payload)


class _Db:
    def __init__(self, docs=None):
        self.docs = deepcopy(docs or {})
        self.read_paths = []
        self.create_paths = []
        self.documents = {}

    def document(self, path):
        self.documents.setdefault(path, _Document(self, path))
        return self.documents[path]


def _path(uid):
    return MemoryCollections(uid=uid).memory_control_state


def test_reconciler_uses_code_cohort_and_creates_only_inert_control_state(monkeypatch):
    monkeypatch.setattr(
        'utils.memory.canonical_memory_onboarding.list_canonical_cohort_uids',
        lambda: ['uid-b', 'uid-a'],
    )
    db = _Db()

    report = reconcile_canonical_memory_onboarding(db)

    assert report.created_uids == ('uid-a', 'uid-b')
    assert report.preserved_uids == ()
    assert db.create_paths == [_path('uid-a'), _path('uid-b')]
    assert set(db.docs) == {_path('uid-a'), _path('uid-b')}
    for uid in ('uid-a', 'uid-b'):
        state = db.docs[_path(uid)]
        assert state == build_whitelisted_user_control_state(uid=uid, account_generation=0)
        assert state['mode'] == 'off'
        assert state['fallback_projection_ready'] is False
        assert state['writes_blocked'] is True
        assert state['grants']['omi_chat'] == {'default_memory': False, 'archive': False}
    assert not any('memory_state/head' in path for path in db.read_paths + db.create_paths)
    assert not any('v3_compatibility_projection' in path for path in db.read_paths + db.create_paths)


def test_reconciler_is_idempotent_and_preserves_existing_rollout_history(monkeypatch):
    monkeypatch.setattr(
        'utils.memory.canonical_memory_onboarding.list_canonical_cohort_uids',
        lambda: ['uid-a'],
    )
    db = _Db()
    first = reconcile_canonical_memory_onboarding(db)
    original = deepcopy(db.docs[_path('uid-a')])

    second = reconcile_canonical_memory_onboarding(db)

    assert first.created_uids == ('uid-a',)
    assert second.created_uids == ()
    assert second.preserved_uids == ('uid-a',)
    assert db.docs[_path('uid-a')] == original
    assert db.documents[_path('uid-a')].create_calls == [original]

    existing = build_whitelisted_user_control_state(uid='uid-a', account_generation=9)
    existing.update(
        {
            'mode': 'read',
            'mode_epoch': 4,
            'cutover_epoch': 4,
            'fallback_projection_ready': True,
            'persistent_memory_writes_started': True,
            'writes_blocked': False,
            'stage_gates': {'shadow': 'passed', 'write': 'passed', 'read': 'passed'},
            'grants': {'omi_chat': {'default_memory': True, 'archive': False}},
        }
    )
    db = _Db({_path('uid-a'): existing})

    report = reconcile_canonical_memory_onboarding(db)

    assert report.preserved_uids == ('uid-a',)
    assert db.docs[_path('uid-a')] == existing
    assert db.documents[_path('uid-a')].create_calls == []


def test_reconciler_does_not_overwrite_malformed_existing_state(monkeypatch):
    monkeypatch.setattr(
        'utils.memory.canonical_memory_onboarding.list_canonical_cohort_uids',
        lambda: ['uid-a'],
    )
    malformed = {'uid': 'uid-a', 'schema_version': 99, 'mode': 'read'}
    db = _Db({_path('uid-a'): malformed})

    with pytest.raises(CanonicalMemoryOnboardingValidationError, match='unsupported_rollout_schema'):
        reconcile_canonical_memory_onboarding(db)

    assert db.docs[_path('uid-a')] == malformed
    assert db.documents[_path('uid-a')].create_calls == []


def test_reconciler_wins_no_race_and_validates_the_concurrent_existing_state(monkeypatch):
    monkeypatch.setattr(
        'utils.memory.canonical_memory_onboarding.list_canonical_cohort_uids',
        lambda: ['uid-a'],
    )
    existing = build_whitelisted_user_control_state(uid='uid-a', account_generation=3)
    db = _Db()
    document = db.document(_path('uid-a'))

    original_create = document.create

    def concurrent_create(payload):
        db.docs[_path('uid-a')] = deepcopy(existing)
        return original_create(payload)

    document.create = concurrent_create

    report = reconcile_canonical_memory_onboarding(db)

    assert report.created_uids == ()
    assert report.preserved_uids == ('uid-a',)
    assert db.docs[_path('uid-a')] == existing
