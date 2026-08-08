"""Behavioral tests for whole-account cohort cutover foundation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from database import account_cutover as account_cutover_db
from models.account_cutover import (
    AccountCutoverCheckpointPhase,
    AccountCutoverClientAction,
    AccountCutoverRecord,
    AccountCutoverState,
    AccountCutoverTransitionRequest,
    OfflineQueueInstruction,
)
from routers import account_cutover as account_cutover_router
from utils.account_cutover.access import (
    AccountCutoverAccessDenial,
    evaluate_account_cutover_access,
    is_cutover_control_path,
)
from utils.account_cutover.control import build_account_cutover_control
from utils.account_cutover.coordinator import AccountCutoverCoordinator
from utils.account_cutover.fence import (
    assert_legacy_product_write_allowed,
    background_job_should_skip_account,
    legacy_writes_allowed_for_state,
)
from utils.account_cutover.state import AccountCutoverTransitionError, apply_cutover_transition, legal_transitions
from utils.other import endpoints as auth


class _FakeSnapshot:
    def __init__(self, data=None):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _FakeDoc:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def get(self):
        return _FakeSnapshot(self._store.get(self._path))

    def set(self, payload):
        self._store[self._path] = dict(payload)

    def collection(self, name):
        return _FakeCollection(self._store, f'{self._path}/{name}')


class _FakeCollection:
    def __init__(self, store, path):
        self._store = store
        self._path = path

    def document(self, doc_id):
        return _FakeDoc(self._store, f'{self._path}/{doc_id}')

    def collection(self, name):
        return _FakeCollection(self._store, f'{self._path}/{name}')


class _FakeDb:
    def __init__(self):
        self._store = {}

    def collection(self, name):
        return _FakeCollection(self._store, name)


@pytest.fixture
def fake_db():
    return _FakeDb()


def test_legal_transitions_cover_accepted_cutover_graph():
    assert AccountCutoverState.migrating in legal_transitions(AccountCutoverState.legacy)
    assert AccountCutoverState.new in legal_transitions(AccountCutoverState.migrating)
    assert AccountCutoverState.rolled_back_stranded in legal_transitions(AccountCutoverState.new)
    assert AccountCutoverState.migrating in legal_transitions(AccountCutoverState.rolled_back_stranded)
    assert AccountCutoverState.legacy not in legal_transitions(AccountCutoverState.new)


def test_transition_bumps_generation_and_sets_offline_drain(fake_db):
    record = AccountCutoverRecord(uid='u1')
    next_record = apply_cutover_transition(
        record,
        AccountCutoverTransitionRequest(
            target_state=AccountCutoverState.migrating,
            expected_account_generation=0,
            reason='test',
        ),
    )
    assert next_record.state == AccountCutoverState.migrating
    assert next_record.account_generation == 1
    assert next_record.offline_queue_instruction == OfflineQueueInstruction.drain


def test_lossy_rollback_marks_stranded_data():
    record = AccountCutoverRecord(
        uid='u1',
        state=AccountCutoverState.new,
        account_generation=2,
    )
    rolled = apply_cutover_transition(
        record,
        AccountCutoverTransitionRequest(
            target_state=AccountCutoverState.rolled_back_stranded,
            expected_account_generation=2,
            reason='rollback',
        ),
    )
    assert rolled.state == AccountCutoverState.rolled_back_stranded
    assert rolled.stranded_new_data is True
    assert rolled.offline_queue_instruction == OfflineQueueInstruction.quarantine


def test_illegal_transition_rejected():
    record = AccountCutoverRecord(uid='u1', state=AccountCutoverState.legacy)
    with pytest.raises(AccountCutoverTransitionError):
        apply_cutover_transition(
            record,
            AccountCutoverTransitionRequest(
                target_state=AccountCutoverState.new,
                expected_account_generation=0,
                reason='skip',
            ),
        )


def test_control_projection_force_upgrade_when_below_floor():
    record = AccountCutoverRecord(uid='u1', state=AccountCutoverState.legacy)
    control = build_account_cutover_control(
        record,
        platform='ios',
        client_build=10,
        minimum_builds={'ios': 20},
    )
    assert control.client_action == AccountCutoverClientAction.force_upgrade
    assert control.product_traffic_allowed is False
    assert control.auth_bootstrap_reachable is True


def test_control_projection_migration_maintenance():
    record = AccountCutoverRecord(
        uid='u1',
        state=AccountCutoverState.migrating,
        account_generation=3,
        offline_queue_instruction=OfflineQueueInstruction.drain,
    )
    control = build_account_cutover_control(record, platform='macos', client_build=100)
    assert control.client_action == AccountCutoverClientAction.migration_maintenance
    assert control.offline_queue_instruction == OfflineQueueInstruction.drain
    assert control.legacy_writes_allowed is False


def test_legacy_default_remains_compatible():
    record = AccountCutoverRecord(uid='u1')
    control = build_account_cutover_control(record, platform='android', client_build=1)
    assert control.state == AccountCutoverState.legacy
    assert control.client_action == AccountCutoverClientAction.none
    assert control.product_traffic_allowed is True
    assert control.legacy_writes_allowed is True
    assert legacy_writes_allowed_for_state(record.state) is True


def test_generation_fence_blocks_migrating_writes():
    record = AccountCutoverRecord(uid='u1', state=AccountCutoverState.migrating, account_generation=2)
    with pytest.raises(Exception):
        assert_legacy_product_write_allowed(record, expected_account_generation=2)
    assert background_job_should_skip_account(record) is True


def test_coordinator_begin_is_idempotent(fake_db, monkeypatch):
    monkeypatch.setattr(account_cutover_db, 'get_firestore_client', lambda: fake_db)
    coordinator = AccountCutoverCoordinator(firestore_client=fake_db)
    first = coordinator.begin('user-abc')
    second = coordinator.begin('user-abc')
    assert first.created is True
    assert second.resumed is True
    assert first.record.manifest_id == second.record.manifest_id
    assert first.record.state == AccountCutoverState.migrating


def test_coordinator_refuses_import_without_destination_binding(fake_db):
    coordinator = AccountCutoverCoordinator(firestore_client=fake_db)
    begun = coordinator.begin('user-xyz')
    coordinator.checkpoint(
        'user-xyz',
        phase=AccountCutoverCheckpointPhase.offline_queue_fenced,
        expected_checkpoint_token=begun.record.checkpoint_token,
    )
    exporting = coordinator.checkpoint(
        'user-xyz',
        phase=AccountCutoverCheckpointPhase.exporting,
    )
    with pytest.raises(AccountCutoverTransitionError) as exc:
        coordinator.checkpoint(
            'user-xyz',
            phase=AccountCutoverCheckpointPhase.importing,
            expected_checkpoint_token=exporting.checkpoint_token,
        )
    assert exc.value.code == 'destination_backend_unbound'


def test_access_allowlists_control_paths():
    assert is_cutover_control_path('/v1/account/cutover/control') is True
    assert is_cutover_control_path('/v1/auth/authorize') is True
    assert is_cutover_control_path('/v1/conversations') is False


def test_access_denies_migrating_product_traffic(monkeypatch, fake_db):
    monkeypatch.setenv('ACCOUNT_CUTOVER_ENFORCEMENT', 'on')
    record = AccountCutoverRecord(uid='u1', state=AccountCutoverState.migrating, account_generation=1)
    monkeypatch.setattr(
        account_cutover_db,
        'get_account_cutover_record',
        lambda uid, firestore_client=None: record,
    )
    with pytest.raises(AccountCutoverAccessDenial) as exc:
        evaluate_account_cutover_access(
            'u1',
            method='POST',
            path='/v1/conversations',
            headers={'X-App-Platform': 'ios', 'X-App-Build': '99'},
            force=True,
        )
    assert exc.value.code == 'migration_maintenance'


def test_control_endpoint_projects_legacy_default(monkeypatch):
    app = FastAPI()
    app.include_router(account_cutover_router.router)
    app.dependency_overrides[auth.get_current_user_uid] = lambda: 'uid-legacy'
    monkeypatch.setattr(
        account_cutover_db,
        'get_account_cutover_record',
        lambda uid, firestore_client=None: AccountCutoverRecord(uid=uid),
    )

    async def _immediate(executor, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(account_cutover_router, 'run_blocking', _immediate)
    client = TestClient(app)
    response = client.get(
        '/v1/account/cutover/control',
        headers={'X-App-Platform': 'macos', 'X-App-Build': '12000'},
    )
    assert response.status_code == 200
    body = response.json()
    assert body['state'] == 'legacy'
    assert body['product_traffic_allowed'] is True
    assert body['auth_bootstrap_reachable'] is True
    assert body['migration']['destination_backend_bound'] is False
