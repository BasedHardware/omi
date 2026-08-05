from copy import deepcopy

import pytest

import utils.memory.canonical_memory_onboarding as onboarding_mod
from database.memory_collections import MemoryCollections
from database.store.errors import AlreadyExists
from tests.store_fakes import FakeDocumentStore
from utils.memory.canonical_memory_onboarding import (
    CanonicalMemoryOnboardingValidationError,
    reconcile_canonical_memory_onboarding,
)
from utils.memory.v3.limited_rollout_config import build_whitelisted_user_control_state


def _path(uid):
    return MemoryCollections(uid=uid).memory_control_state


def _install(monkeypatch, store):
    # The reconciler talks to the backend-neutral DocumentStore via its _store seam (ADR-0028), so the
    # tests inject an in-memory FakeDocumentStore instead of a raw Firestore client.
    monkeypatch.setattr(onboarding_mod, '_store', lambda: store)


def _set_cohort(monkeypatch, uids):
    monkeypatch.setattr(onboarding_mod, 'list_canonical_cohort_uids', lambda: uids)


def test_reconciler_uses_code_cohort_and_creates_only_inert_control_state(monkeypatch):
    _set_cohort(monkeypatch, ['uid-b', 'uid-a'])
    store = FakeDocumentStore()
    _install(monkeypatch, store)

    report = reconcile_canonical_memory_onboarding()

    assert report.created_uids == ('uid-a', 'uid-b')
    assert report.preserved_uids == ()
    for uid in ('uid-a', 'uid-b'):
        state = store.get(_path(uid)).to_dict()
        assert state == build_whitelisted_user_control_state(uid=uid, account_generation=0)
        assert state['mode'] == 'off'
        assert state['fallback_projection_ready'] is False
        assert state['writes_blocked'] is True
        assert state['grants']['omi_chat'] == {'default_memory': False, 'archive': False}
    # Only the inert control-state docs are created: no memory head / projection is touched.
    assert set(store._docs) == {_path('uid-a'), _path('uid-b')}
    assert not any('memory_state/head' in path or 'v3_compatibility_projection' in path for path in store._docs)


def test_reconciler_is_idempotent_and_preserves_existing_rollout_history(monkeypatch):
    _set_cohort(monkeypatch, ['uid-a'])
    store = FakeDocumentStore()
    _install(monkeypatch, store)

    first = reconcile_canonical_memory_onboarding()
    original = deepcopy(store.get(_path('uid-a')).to_dict())

    second = reconcile_canonical_memory_onboarding()

    assert first.created_uids == ('uid-a',)
    assert second.created_uids == ()
    assert second.preserved_uids == ('uid-a',)
    assert store.get(_path('uid-a')).to_dict() == original

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
    store = FakeDocumentStore()
    store.set(_path('uid-a'), deepcopy(existing))
    _install(monkeypatch, store)

    report = reconcile_canonical_memory_onboarding()

    assert report.preserved_uids == ('uid-a',)
    assert store.get(_path('uid-a')).to_dict() == existing


def test_reconciler_does_not_overwrite_malformed_existing_state(monkeypatch):
    _set_cohort(monkeypatch, ['uid-a'])
    malformed = {'uid': 'uid-a', 'schema_version': 99, 'mode': 'read'}
    store = FakeDocumentStore()
    store.set(_path('uid-a'), deepcopy(malformed))
    _install(monkeypatch, store)

    with pytest.raises(CanonicalMemoryOnboardingValidationError, match='unsupported_rollout_schema'):
        reconcile_canonical_memory_onboarding()

    assert store.get(_path('uid-a')).to_dict() == malformed


def test_reconciler_wins_no_race_and_validates_the_concurrent_existing_state(monkeypatch):
    _set_cohort(monkeypatch, ['uid-a'])
    existing = build_whitelisted_user_control_state(uid='uid-a', account_generation=3)
    store = FakeDocumentStore()
    _install(monkeypatch, store)

    def concurrent_create(path, data):
        # A concurrent rollout writer wins the create race: our create loses with AlreadyExists and
        # the reconciler must preserve (and validate) the concurrent state, never overwrite it.
        store.set(path, deepcopy(existing))
        raise AlreadyExists(path)

    monkeypatch.setattr(store, 'create', concurrent_create)

    report = reconcile_canonical_memory_onboarding()

    assert report.created_uids == ()
    assert report.preserved_uids == ('uid-a',)
    assert store.get(_path('uid-a')).to_dict() == existing
