"""Behavioral tests for whole-account cohort cutover foundation."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import account_cutover as account_cutover_db
from database.read_boundary import MalformedDocError
from models.account_cutover import (
    AccountCutoverCheckpointPhase,
    AccountCutoverClientAction,
    AccountCutoverRecord,
    AccountCutoverState,
    AccountCutoverTransitionRequest,
    OfflineQueueInstruction,
)
from routers import account_cutover as account_cutover_router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
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


@pytest.fixture
def fake_db():
    return StrictFirestore()


@pytest.fixture
def enroll_uid(monkeypatch):
    def _enroll(uid: str):
        monkeypatch.setattr(
            'utils.account_cutover.coordinator.is_account_cutover_cohort_member',
            lambda value: value == uid,
        )

    return _enroll


def test_legal_transitions_cover_accepted_cutover_graph():
    assert AccountCutoverState.migrating in legal_transitions(AccountCutoverState.legacy)
    assert AccountCutoverState.new in legal_transitions(AccountCutoverState.migrating)
    assert AccountCutoverState.rolled_back_stranded in legal_transitions(AccountCutoverState.new)
    assert AccountCutoverState.migrating in legal_transitions(AccountCutoverState.rolled_back_stranded)
    assert AccountCutoverState.legacy not in legal_transitions(AccountCutoverState.new)


def test_transition_bumps_generation_and_quarantines_at_fence():
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
    assert next_record.offline_queue_instruction == OfflineQueueInstruction.quarantine


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


def test_control_projection_migration_maintenance_quarantines():
    record = AccountCutoverRecord(
        uid='u1',
        state=AccountCutoverState.migrating,
        account_generation=3,
        offline_queue_instruction=OfflineQueueInstruction.drain,
    )
    control = build_account_cutover_control(record, platform='macos', client_build=100)
    assert control.client_action == AccountCutoverClientAction.migration_maintenance
    assert control.offline_queue_instruction == OfflineQueueInstruction.quarantine
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


def test_malformed_cutover_document_fails_closed(fake_db):
    path = ('users', 'broken-uid', 'account_cutover', 'state')
    fake_db.rows[path] = {'schema_version': 1, 'uid': 'broken-uid', 'state': 'not-a-real-state'}
    with pytest.raises(MalformedDocError):
        account_cutover_db.get_account_cutover_record('broken-uid', firestore_client=fake_db)


def test_access_fails_closed_on_malformed_cutover_document(monkeypatch, fake_db):
    monkeypatch.setenv('ACCOUNT_CUTOVER_ENFORCEMENT', 'on')

    def _boom(uid, firestore_client=None):
        raise MalformedDocError(
            document_path='users/u1/account_cutover/state', error_types=('enum',), error_fields=('state',)
        )

    monkeypatch.setattr(account_cutover_db, 'get_account_cutover_record', _boom)
    with pytest.raises(AccountCutoverAccessDenial) as exc:
        evaluate_account_cutover_access(
            'u1',
            method='POST',
            path='/v1/conversations',
            headers={'X-App-Platform': 'ios', 'X-App-Build': '99'},
            force=True,
        )
    assert exc.value.code == 'account_cutover_state_unavailable'


def test_positive_generation_requires_matching_header_on_mutations(monkeypatch):
    monkeypatch.setenv('ACCOUNT_CUTOVER_ENFORCEMENT', 'on')
    record = AccountCutoverRecord(
        uid='u1',
        state=AccountCutoverState.legacy,
        account_generation=2,
    )
    monkeypatch.setattr(
        account_cutover_db,
        'get_account_cutover_record',
        lambda uid, firestore_client=None: record,
    )
    with pytest.raises(AccountCutoverAccessDenial) as missing:
        evaluate_account_cutover_access(
            'u1',
            method='POST',
            path='/v1/conversations',
            headers={'X-App-Platform': 'ios', 'X-App-Build': '99'},
            force=True,
        )
    assert missing.value.code == 'account_generation_mismatch'

    with pytest.raises(AccountCutoverAccessDenial) as stale:
        evaluate_account_cutover_access(
            'u1',
            method='POST',
            path='/v1/conversations',
            headers={
                'X-App-Platform': 'ios',
                'X-App-Build': '99',
                'X-Account-Generation': '1',
            },
            force=True,
        )
    assert stale.value.code == 'account_generation_mismatch'

    evaluate_account_cutover_access(
        'u1',
        method='POST',
        path='/v1/conversations',
        headers={
            'X-App-Platform': 'ios',
            'X-App-Build': '99',
            'X-Account-Generation': '2',
        },
        force=True,
    )


def test_generation_zero_remains_compatible_without_header(monkeypatch):
    monkeypatch.setenv('ACCOUNT_CUTOVER_ENFORCEMENT', 'on')
    record = AccountCutoverRecord(uid='u1')
    monkeypatch.setattr(
        account_cutover_db,
        'get_account_cutover_record',
        lambda uid, firestore_client=None: record,
    )
    evaluate_account_cutover_access(
        'u1',
        method='POST',
        path='/v1/conversations',
        headers={'X-App-Platform': 'android', 'X-App-Build': '12'},
        force=True,
    )


def test_coordinator_begin_requires_explicit_enrollment(fake_db):
    coordinator = AccountCutoverCoordinator(firestore_client=fake_db)
    with pytest.raises(AccountCutoverTransitionError) as exc:
        coordinator.begin('user-abc')
    assert exc.value.code == 'cutover_not_enrolled'


def test_coordinator_begin_is_idempotent(fake_db, enroll_uid):
    enroll_uid('user-abc')
    coordinator = AccountCutoverCoordinator(firestore_client=fake_db)
    first = coordinator.begin('user-abc')
    second = coordinator.begin('user-abc')
    assert first.created is True
    assert second.resumed is True
    assert first.record.manifest_id == second.record.manifest_id
    assert first.record.state == AccountCutoverState.migrating
    assert first.record.offline_queue_instruction == OfflineQueueInstruction.quarantine


def test_prepare_offline_drain_only_before_fence(fake_db, enroll_uid):
    enroll_uid('user-drain')
    coordinator = AccountCutoverCoordinator(firestore_client=fake_db)
    drained = coordinator.prepare_offline_drain('user-drain')
    assert drained.state == AccountCutoverState.legacy
    assert drained.offline_queue_instruction == OfflineQueueInstruction.drain
    begun = coordinator.begin('user-drain')
    assert begun.record.offline_queue_instruction == OfflineQueueInstruction.quarantine
    with pytest.raises(AccountCutoverTransitionError) as exc:
        coordinator.prepare_offline_drain('user-drain')
    assert exc.value.code == 'offline_drain_after_fence'


def test_coordinator_refuses_import_without_destination_binding(fake_db, enroll_uid):
    enroll_uid('user-xyz')
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


def test_bind_product_generations_refuses_without_destination(fake_db, enroll_uid):
    enroll_uid('user-bind')
    coordinator = AccountCutoverCoordinator(firestore_client=fake_db)
    begun = coordinator.begin('user-bind')
    with pytest.raises(AccountCutoverTransitionError) as exc:
        coordinator.bind_destination_product_generations(
            'user-bind',
            ui_generation=1,
            api_generation=1,
            expected_account_generation=begun.record.account_generation,
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
            headers={
                'X-App-Platform': 'ios',
                'X-App-Build': '99',
                'X-Account-Generation': '1',
            },
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


def test_direct_auth_call_api_preserved(monkeypatch):
    monkeypatch.setattr(auth, 'verify_token', lambda _token: 'direct-uid')
    monkeypatch.setattr(auth, 'get_user_deletion_wipe_status', lambda _uid: None)
    monkeypatch.setattr(auth, 'record_user_platform', lambda *args, **kwargs: None)
    monkeypatch.setattr(auth, 'record_client_device', lambda *args, **kwargs: None)
    monkeypatch.setattr(auth, 'validate_byok_request', lambda *args, **kwargs: None)
    assert auth.get_current_user_uid(authorization='Bearer token') == 'direct-uid'
