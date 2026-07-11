from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from threading import RLock
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import database.candidates as candidates_db
from models.candidate import CandidateCreate, CandidateStatus
from utils.task_intelligence import candidate_service


class FakeSnapshot:
    def __init__(self, data=None):
        self._data = deepcopy(data)
        self.exists = data is not None

    def to_dict(self):
        return deepcopy(self._data)


class FakeRef:
    def __init__(self, database, path):
        self.database = database
        self.path = path

    def collection(self, name):
        return FakeCollection(self.database, (*self.path, name))

    def get(self, transaction=None):
        return FakeSnapshot(self.database.rows.get(self.path))

    def update(self, patch):
        self.database.rows[self.path].update(deepcopy(patch))


class FakeCollection:
    def __init__(self, database, path):
        self.database = database
        self.path = path

    def document(self, name):
        return FakeRef(self.database, (*self.path, name))


class FakeTransaction:
    def __init__(self, database):
        self.database = database
        self.lock = database.lock

    def set(self, ref, data):
        self.database.rows[ref.path] = deepcopy(data)

    def update(self, ref, patch):
        if ref.path not in self.database.rows:
            raise RuntimeError('missing row')
        self.database.rows[ref.path].update(deepcopy(patch))


class FakeDB:
    def __init__(self):
        self.rows = {}
        self.lock = RLock()

    def collection(self, name):
        return FakeCollection(self, (name,))

    def transaction(self):
        return FakeTransaction(self)


@pytest.fixture
def fake_db(monkeypatch):
    database = FakeDB()
    database.rows[('users', 'user-1', 'task_intelligence_control', 'state')] = {
        'workflow_mode': 'read',
        'account_generation': 3,
    }
    database.rows[('users', 'user-1', 'goals', 'goal-1')] = {
        'id': 'goal-1',
        'goal_id': 'goal-1',
        'title': 'Goal 1',
        'status': 'focused',
        'is_active': True,
        'account_generation': 3,
    }
    database.rows[('users', 'user-1', 'workstreams', 'workstream-1')] = {
        'workstream_id': 'workstream-1',
        'goal_id': 'goal-1',
        'account_generation': 3,
    }

    def transactional(function):
        def run(transaction):
            with transaction.lock:
                return function(transaction)

        return run

    monkeypatch.setattr(candidates_db, 'db', database)
    monkeypatch.setattr(candidates_db.firestore, 'transactional', transactional)
    candidate_service.clear_workstream_candidate_resolver()
    candidate_service.task_links.clear_workstream_goal_resolver()
    candidate_service.task_links.register_goal_existence_resolver(lambda uid, goal_id: goal_id == 'goal-1')
    yield database
    candidate_service.clear_workstream_candidate_resolver()
    candidate_service.task_links.clear_workstream_goal_resolver()


def task_create_proposal(**overrides):
    payload = {
        'subject_kind': 'task',
        'proposed_action': 'create',
        'task_change': {'description': 'Send the budget', 'owner': 'user', 'due_confidence': 0.9},
        'capture_confidence': 0.95,
        'ownership_confidence': 1,
        'goal_id': 'goal-1',
        'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
        'source_surface': 'conversation',
    }
    payload.update(overrides)
    return CandidateCreate.model_validate(payload)


def create_record(fake_db, **overrides):
    return candidates_db.create_candidate(
        'user-1',
        task_create_proposal(**overrides),
        idempotency_key='conversation-1:item-1',
        account_generation=3,
        now=datetime(2026, 7, 9, tzinfo=timezone.utc),
    )


def test_candidate_union_accepts_each_task_arm_and_workstream_create():
    create = task_create_proposal()
    update = task_create_proposal(
        proposed_action='update',
        task_id='task-1',
        task_change={'description': 'Send the revised budget'},
    )
    complete = task_create_proposal(
        proposed_action='complete',
        task_id='task-1',
        task_change={'status': 'completed'},
    )
    cancel = task_create_proposal(
        proposed_action='cancel',
        task_id='task-1',
        task_change={'status': 'cancelled'},
    )
    supersede = task_create_proposal(
        proposed_action='supersede',
        task_id='task-1',
        task_change={'status': 'superseded', 'superseded_by': 'task-2'},
    )
    workstream = CandidateCreate.model_validate(
        {
            'subject_kind': 'workstream',
            'proposed_action': 'create',
            'workstream_proposal': {
                'title': 'Investor follow-up',
                'objective': 'Send the updated note',
                'anchor_task': {'description': 'Draft the updated note'},
            },
            'capture_confidence': 0.8,
            'ownership_confidence': 1,
            'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
            'source_surface': 'agent',
        }
    )

    assert [item.proposed_action.value for item in (create, update, complete, cancel, supersede, workstream)] == [
        'create',
        'update',
        'complete',
        'cancel',
        'supersede',
        'create',
    ]


@pytest.mark.parametrize(
    'patch',
    [
        {'workstream_proposal': {'title': 'x', 'objective': 'y', 'anchor_task': {'description': 'z'}}},
        {'proposed_action': 'update', 'task_id': None, 'task_change': {'description': 'x'}},
        {'proposed_action': 'complete', 'task_id': 'task-1', 'task_change': {'status': 'active'}},
        {
            'subject_kind': 'workstream',
            'proposed_action': 'update',
            'task_change': None,
            'workstream_proposal': {'title': 'x', 'objective': 'y', 'anchor_task': {'description': 'z'}},
        },
        {'goal_id': 'goal-1', 'task_change': {'description': 'x', 'goal_id': 'goal-1'}},
    ],
)
def test_candidate_union_rejects_mixed_or_invalid_payloads(patch):
    with pytest.raises(ValidationError):
        task_create_proposal(**patch)


def test_candidate_create_and_accept_are_idempotent_and_preserve_envelope(fake_db):
    record = create_record(fake_db)
    duplicate = create_record(fake_db)
    first = candidates_db.resolve_task_candidate(
        'user-1', record.candidate_id, account_generation=3, now=datetime(2026, 7, 10, tzinfo=timezone.utc)
    )
    second = candidates_db.resolve_task_candidate(
        'user-1', record.candidate_id, account_generation=3, now=datetime(2026, 7, 11, tzinfo=timezone.utc)
    )

    assert duplicate.candidate_id == record.candidate_id
    assert first.task_id == second.task_id
    assert first.newly_resolved is True
    assert second.newly_resolved is False
    task_rows = [data for path, data in fake_db.rows.items() if 'action_items' in path]
    assert len(task_rows) == 1
    task = task_rows[0]
    assert task['goal_id'] == 'goal-1'
    assert task['source'] == 'conversation'
    assert task['provenance'][0]['id'] == 'conversation-1'
    assert task['due_confidence'] == 0.9
    assert task['capture_confidence'] == 0.95
    assert task['ownership_confidence'] == 1


def test_task_mutation_preserves_origin_and_merges_provenance(fake_db):
    original = {'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}
    added = {'kind': 'artifact', 'id': 'artifact-2', 'scope': 'canonical'}
    task_path = ('users', 'user-1', 'action_items', 'task-1')
    fake_db.rows[task_path] = {
        'id': 'task-1',
        'task_id': 'task-1',
        'description': 'Original task',
        'status': 'active',
        'completed': False,
        'goal_id': 'goal-1',
        'workstream_id': 'workstream-1',
        'source': 'manual',
        'provenance': [original],
    }
    candidate = candidates_db.create_candidate(
        'user-1',
        task_create_proposal(
            proposed_action='update',
            task_id='task-1',
            task_change={'description': 'Updated task'},
            source_surface='feedback',
            evidence_refs=[original, added],
        ),
        idempotency_key='feedback:update-task-1',
        account_generation=3,
    )

    first = candidates_db.resolve_task_candidate('user-1', candidate.candidate_id, account_generation=3)
    replay = candidates_db.resolve_task_candidate('user-1', candidate.candidate_id, account_generation=3)
    task = fake_db.rows[task_path]

    assert first.newly_resolved is True
    assert replay.newly_resolved is False
    assert task['description'] == 'Updated task'
    assert task['source'] == 'manual'
    assert task['provenance'] == [original, added]


def test_candidate_idempotency_key_rejects_a_different_proposal(fake_db):
    create_record(fake_db)

    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.create_candidate(
            'user-1',
            task_create_proposal(task_change={'description': 'Send a different budget'}),
            idempotency_key='conversation-1:item-1',
            account_generation=3,
        )


def test_concurrent_accept_creates_one_task_and_one_new_resolution(fake_db):
    record = create_record(fake_db)

    def accept():
        return candidates_db.resolve_task_candidate('user-1', record.candidate_id, account_generation=3)

    with ThreadPoolExecutor(max_workers=8) as executor:
        receipts = list(executor.map(lambda _: accept(), range(16)))

    assert sum(receipt.newly_resolved for receipt in receipts) == 1
    assert len({receipt.task_id for receipt in receipts}) == 1
    assert len([path for path in fake_db.rows if 'action_items' in path]) == 1


def test_reject_and_expire_are_idempotent_and_generation_safe(fake_db):
    record = create_record(fake_db)
    with pytest.raises(candidates_db.CandidateGenerationMismatchError):
        candidates_db.resolve_task_candidate('user-1', record.candidate_id, account_generation=4)

    first = candidates_db.resolve_candidate_without_mutation(
        'user-1',
        record.candidate_id,
        status=CandidateStatus.rejected,
        reason='not_mine',
        account_generation=3,
    )
    second = candidates_db.resolve_candidate_without_mutation(
        'user-1',
        record.candidate_id,
        status=CandidateStatus.rejected,
        reason='not_mine',
        account_generation=3,
    )
    assert first.newly_resolved is True
    assert second.newly_resolved is False
    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.resolve_candidate_without_mutation(
            'user-1',
            record.candidate_id,
            status=CandidateStatus.expired,
            reason=None,
            account_generation=3,
        )


def test_legacy_promotion_claim_fences_concurrent_rejection_and_is_retryable(fake_db):
    record = create_record(fake_db)
    token = candidates_db.claim_candidate_for_legacy_promotion('user-1', record.candidate_id, account_generation=3)
    resumed_token = candidates_db.claim_candidate_for_legacy_promotion(
        'user-1', record.candidate_id, account_generation=3, resume_active_claim=True
    )

    assert resumed_token == token
    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.claim_candidate_for_legacy_promotion('user-1', record.candidate_id, account_generation=3)
    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.resolve_candidate_without_mutation(
            'user-1',
            record.candidate_id,
            status=CandidateStatus.rejected,
            reason='concurrent_reject',
            account_generation=3,
        )

    candidates_db.begin_candidate_legacy_promotion(
        'user-1',
        record.candidate_id,
        account_generation=3,
        claim_token=token,
        result_task_id='task-legacy',
    )

    resolved = candidates_db.reconcile_migrated_candidate(
        'user-1',
        record.candidate_id,
        status=CandidateStatus.accepted,
        account_generation=3,
        result_task_id='task-legacy',
        reason='legacy_promoted',
        claim_token=token,
    )

    assert resolved.status == CandidateStatus.accepted
    assert resolved.result_task_id == 'task-legacy'
    claim = fake_db.rows[('users', 'user-1', 'candidate_resolution_claims', record.candidate_id)]
    assert claim['status'] == 'consumed'


def test_mutation_started_fence_survives_lease_and_recovers_crash_after_legacy_write(fake_db):
    record = create_record(fake_db)
    start = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)
    first_token = candidates_db.claim_candidate_for_legacy_promotion(
        'user-1', record.candidate_id, account_generation=3, now=start, lease_seconds=60
    )
    reserved_task_id = candidates_db.task_id_for_candidate('user-1', 3, record.candidate_id)
    candidates_db.begin_candidate_legacy_promotion(
        'user-1',
        record.candidate_id,
        account_generation=3,
        claim_token=first_token,
        result_task_id=reserved_task_id,
        now=start,
        lease_seconds=60,
    )
    task_path = ('users', 'user-1', 'action_items', reserved_task_id)
    fake_db.rows[task_path] = {'id': reserved_task_id, 'description': 'Send the budget'}

    recovery_time = start + timedelta(minutes=2)
    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.resolve_candidate_without_mutation(
            'user-1',
            record.candidate_id,
            status=CandidateStatus.rejected,
            reason='concurrent_reject_after_lease',
            account_generation=3,
            now=recovery_time,
        )

    recovery_token = candidates_db.claim_candidate_for_legacy_promotion(
        'user-1',
        record.candidate_id,
        account_generation=3,
        now=recovery_time,
        lease_seconds=60,
    )
    claim_path = ('users', 'user-1', 'candidate_resolution_claims', record.candidate_id)
    claim = fake_db.rows[claim_path]
    assert recovery_token != first_token
    assert claim['phase'] == 'mutation_started'
    assert claim['result_task_id'] == reserved_task_id

    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.reconcile_migrated_candidate(
            'user-1',
            record.candidate_id,
            status=CandidateStatus.accepted,
            account_generation=3,
            result_task_id=reserved_task_id,
            claim_token=first_token,
            resolved_at=recovery_time,
        )

    recovered_task_id = candidates_db.begin_candidate_legacy_promotion(
        'user-1',
        record.candidate_id,
        account_generation=3,
        claim_token=recovery_token,
        result_task_id='newly-planned-task-must-not-replace-reservation',
        now=recovery_time,
        lease_seconds=60,
    )
    assert recovered_task_id.task_id == reserved_task_id
    assert recovered_task_id.kind == 'create'
    resolved = candidates_db.reconcile_migrated_candidate(
        'user-1',
        record.candidate_id,
        status=CandidateStatus.accepted,
        account_generation=3,
        result_task_id=reserved_task_id,
        claim_token=recovery_token,
        resolved_at=recovery_time,
    )

    assert resolved.status == CandidateStatus.accepted
    assert resolved.result_task_id == reserved_task_id
    assert fake_db.rows[claim_path]['status'] == 'consumed'
    assert len([path for path in fake_db.rows if 'action_items' in path]) == 1


def test_begin_revalidates_preferred_existing_task_after_concurrent_delete(fake_db):
    record = create_record(fake_db)
    preferred_id = 'task-existing'
    preferred_path = ('users', 'user-1', 'action_items', preferred_id)
    fake_db.rows[preferred_path] = {
        'id': preferred_id,
        'description': 'Send the budget',
        'completed': False,
        'status': 'active',
    }
    token = candidates_db.claim_candidate_for_legacy_promotion('user-1', record.candidate_id, account_generation=3)
    # The router observed this row as active, but the user deleted it before
    # the reservation transaction read it.
    fake_db.rows[preferred_path]['deleted'] = True
    fallback_id = candidates_db.task_id_for_candidate('user-1', 3, record.candidate_id)

    reservation = candidates_db.begin_candidate_legacy_promotion(
        'user-1',
        record.candidate_id,
        account_generation=3,
        claim_token=token,
        result_task_id=fallback_id,
        preferred_existing_task_id=preferred_id,
    )

    assert reservation.task_id == fallback_id
    assert reservation.kind == 'create'
    assert reservation.task_id != preferred_id
    claim = fake_db.rows[('users', 'user-1', 'candidate_resolution_claims', record.candidate_id)]
    assert claim['reservation_kind'] == 'create'


def test_begin_atomically_reserves_still_active_preferred_task(fake_db):
    record = create_record(fake_db)
    preferred_id = 'task-existing'
    fake_db.rows[('users', 'user-1', 'action_items', preferred_id)] = {
        'id': preferred_id,
        'description': 'Send the budget',
        'completed': False,
        'status': 'active',
    }
    token = candidates_db.claim_candidate_for_legacy_promotion('user-1', record.candidate_id, account_generation=3)

    reservation = candidates_db.begin_candidate_legacy_promotion(
        'user-1',
        record.candidate_id,
        account_generation=3,
        claim_token=token,
        result_task_id=candidates_db.task_id_for_candidate('user-1', 3, record.candidate_id),
        preferred_existing_task_id=preferred_id,
    )

    assert reservation == candidates_db.LegacyPromotionReservation(task_id=preferred_id, kind='existing')
    claim = fake_db.rows[('users', 'user-1', 'candidate_resolution_claims', record.candidate_id)]
    assert claim['result_task_id'] == preferred_id
    assert claim['reservation_kind'] == 'existing'


def test_expired_legacy_promotion_claim_gets_new_owner(fake_db):
    record = create_record(fake_db)
    start = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)
    first = candidates_db.claim_candidate_for_legacy_promotion(
        'user-1', record.candidate_id, account_generation=3, now=start, lease_seconds=60
    )
    second = candidates_db.claim_candidate_for_legacy_promotion(
        'user-1',
        record.candidate_id,
        account_generation=3,
        now=start.replace(minute=2),
        lease_seconds=60,
    )

    assert second != first
    with pytest.raises(candidates_db.CandidateConflictError):
        candidates_db.reconcile_migrated_candidate(
            'user-1',
            record.candidate_id,
            status=CandidateStatus.accepted,
            account_generation=3,
            result_task_id='task-legacy',
            claim_token=first,
        )


@pytest.mark.parametrize('mode', ['off', 'shadow'])
def test_authoritative_control_blocks_candidate_writes_in_nonvisible_modes(fake_db, mode):
    fake_db.rows[('users', 'user-1', 'task_intelligence_control', 'state')]['workflow_mode'] = mode

    with pytest.raises(candidates_db.CandidateConflictError):
        create_record(fake_db)

    assert not [path for path in fake_db.rows if 'candidates' in path]


def test_generation_rollover_fences_acceptance_inside_transaction(fake_db):
    record = create_record(fake_db)
    fake_db.rows[('users', 'user-1', 'task_intelligence_control', 'state')]['account_generation'] = 4

    with pytest.raises(candidates_db.CandidateGenerationMismatchError):
        candidates_db.resolve_task_candidate('user-1', record.candidate_id, account_generation=3)

    assert candidates_db.get_candidate('user-1', record.candidate_id).status == CandidateStatus.pending
    assert not [path for path in fake_db.rows if 'action_items' in path]


def test_task_candidate_validates_final_existing_links_and_fences_races(fake_db, monkeypatch):
    task_path = ('users', 'user-1', 'action_items', 'task-1')
    fake_db.rows[task_path] = {
        'id': 'task-1',
        'description': 'Send the budget',
        'completed': False,
        'status': 'active',
        'goal_id': 'goal-1',
        'workstream_id': 'workstream-1',
    }
    monkeypatch.setattr(
        candidate_service.action_items_db,
        'get_action_item',
        lambda uid, task_id: deepcopy(fake_db.rows[task_path]),
    )
    candidate_service.task_links.register_workstream_goal_resolver(
        lambda uid, workstream_id: 'goal-1' if workstream_id == 'workstream-1' else None
    )
    candidate_service.task_links.register_goal_existence_resolver(lambda uid, goal_id: goal_id == 'goal-1')
    valid = candidates_db.create_candidate(
        'user-1',
        task_create_proposal(
            proposed_action='update',
            task_id='task-1',
            task_change={'due_confidence': 0.8},
            goal_id=None,
        ),
        idempotency_key='update-valid',
        account_generation=3,
    )
    candidate_service.accept_candidate('user-1', valid.candidate_id, account_generation=3)
    assert fake_db.rows[task_path]['goal_id'] == 'goal-1'
    assert fake_db.rows[task_path]['workstream_id'] == 'workstream-1'

    invalid = candidates_db.create_candidate(
        'user-1',
        task_create_proposal(
            proposed_action='update',
            task_id='task-1',
            task_change={'description': 'Send the revised budget'},
            goal_id='goal-2',
        ),
        idempotency_key='update-invalid',
        account_generation=3,
    )
    with pytest.raises(candidate_service.task_links.TaskLinkValidationError):
        candidate_service.accept_candidate('user-1', invalid.candidate_id, account_generation=3)
    assert fake_db.rows[task_path]['description'] == 'Send the budget'

    race = candidates_db.create_candidate(
        'user-1',
        task_create_proposal(
            proposed_action='update',
            task_id='task-1',
            task_change={'description': 'Send the final budget'},
            goal_id=None,
        ),
        idempotency_key='update-race',
        account_generation=3,
    )

    def stale_read(uid, task_id):
        snapshot = deepcopy(fake_db.rows[task_path])
        fake_db.rows[task_path]['goal_id'] = 'goal-raced'
        return snapshot

    monkeypatch.setattr(candidate_service.action_items_db, 'get_action_item', stale_read)
    with pytest.raises(candidates_db.CandidateConflictError):
        candidate_service.accept_candidate('user-1', race.candidate_id, account_generation=3)


def test_description_update_reloads_as_task_change_and_applies(fake_db, monkeypatch):
    task_path = ('users', 'user-1', 'action_items', 'task-description')
    fake_db.rows[task_path] = {
        'id': 'task-description',
        'description': 'Send the budget',
        'completed': False,
        'status': 'active',
    }
    monkeypatch.setattr(
        candidate_service.action_items_db,
        'get_action_item',
        lambda uid, task_id: deepcopy(fake_db.rows[task_path]),
    )
    record = candidates_db.create_candidate(
        'user-1',
        task_create_proposal(
            proposed_action='update',
            task_id='task-description',
            task_change={'description': 'Send the revised budget'},
            goal_id=None,
        ),
        idempotency_key='description-update',
        account_generation=3,
    )

    candidate_service.accept_candidate('user-1', record.candidate_id, account_generation=3)

    assert fake_db.rows[task_path]['description'] == 'Send the revised budget'


def test_workstream_candidate_is_invisible_until_resolver_registered(fake_db):
    proposal = CandidateCreate.model_validate(
        {
            'subject_kind': 'workstream',
            'proposed_action': 'create',
            'workstream_proposal': {
                'title': 'Investor follow-up',
                'objective': 'Send the updated note',
                'anchor_task': {'description': 'Draft the note'},
            },
            'capture_confidence': 0.8,
            'ownership_confidence': 1,
            'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
            'source_surface': 'agent',
        }
    )
    record = candidates_db.create_candidate('user-1', proposal, idempotency_key='ws-1', account_generation=3)

    with pytest.raises(candidates_db.WorkstreamCandidateResolverUnavailableError):
        candidate_service.accept_candidate('user-1', record.candidate_id, account_generation=3)


def test_integration_outbox_dispatches_once_and_retry_observes_completion(fake_db, monkeypatch):
    record = create_record(fake_db)
    dispatched = []

    async def sync(uid, task, **kwargs):
        dispatched.append(task['id'])
        return {'synced': True}

    monkeypatch.setattr(candidate_service.action_items_db, 'get_action_item', lambda uid, task_id: {'id': task_id})
    monkeypatch.setattr(candidate_service, 'auto_sync_action_item', sync)
    monkeypatch.setattr(candidate_service, 'submit_with_context', lambda executor, function: function())

    first = candidate_service.accept_candidate('user-1', record.candidate_id, account_generation=3)
    second = candidate_service.accept_candidate('user-1', record.candidate_id, account_generation=3)

    assert first.newly_resolved is True
    assert second.newly_resolved is False
    assert dispatched == [first.task_id]
    outbox = next(data for path, data in fake_db.rows.items() if 'candidate_integration_outbox' in path)
    assert outbox['status'] == 'completed'
    assert outbox['attempt_count'] == 1


def test_failed_integration_outbox_is_retryable_without_reaccepting_task(fake_db):
    record = create_record(fake_db)
    candidates_db.resolve_task_candidate('user-1', record.candidate_id, account_generation=3)

    first_lease = candidates_db.claim_candidate_integration_dispatch(
        'user-1', record.candidate_id, account_generation=3
    )
    assert first_lease is not None
    assert (
        candidates_db.claim_candidate_integration_dispatch('user-1', record.candidate_id, account_generation=3) is None
    )
    assert candidates_db.complete_candidate_integration_dispatch(
        'user-1',
        record.candidate_id,
        account_generation=3,
        lease_token=first_lease,
        succeeded=False,
    )
    assert (
        candidates_db.claim_candidate_integration_dispatch('user-1', record.candidate_id, account_generation=3)
        is not None
    )
    outbox = next(data for path, data in fake_db.rows.items() if 'candidate_integration_outbox' in path)
    assert outbox['attempt_count'] == 2


def test_unsynced_integration_result_stays_retryable(fake_db, monkeypatch):
    record = create_record(fake_db)

    async def unsynced(uid, task, **kwargs):
        return {'synced': False, 'platform': 'todoist', 'error': 'temporary'}

    monkeypatch.setattr(candidate_service.action_items_db, 'get_action_item', lambda uid, task_id: {'id': task_id})
    monkeypatch.setattr(candidate_service, 'auto_sync_action_item', unsynced)
    monkeypatch.setattr(candidate_service, 'submit_with_context', lambda executor, function: function())

    candidate_service.accept_candidate('user-1', record.candidate_id, account_generation=3)

    outbox = next(data for path, data in fake_db.rows.items() if 'candidate_integration_outbox' in path)
    assert outbox['status'] == 'failed'


def test_drain_recovers_crash_after_accept_commit(fake_db, monkeypatch):
    record = create_record(fake_db)
    receipt = candidates_db.resolve_task_candidate('user-1', record.candidate_id, account_generation=3)
    dispatched = []

    async def sync(uid, task, **kwargs):
        dispatched.append(task['id'])
        return {'synced': True}

    monkeypatch.setattr(candidate_service.action_items_db, 'get_action_item', lambda uid, task_id: {'id': task_id})
    monkeypatch.setattr(candidate_service, 'auto_sync_action_item', sync)
    monkeypatch.setattr(candidate_service, 'submit_with_context', lambda executor, function: function())
    monkeypatch.setattr(
        candidates_db,
        'list_candidate_integration_dispatches',
        lambda uid, account_generation, limit=100: [
            {
                'candidate_id': record.candidate_id,
                'task_id': receipt.task_id,
                'status': 'pending',
                'account_generation': account_generation,
            }
        ],
    )

    assert candidate_service.drain_candidate_integrations('user-1', account_generation=3) == 1
    assert candidate_service.drain_candidate_integrations('user-1', account_generation=3) == 0
    assert dispatched == [receipt.task_id]


def test_integration_outbox_is_generation_fenced_at_claim_and_completion(fake_db):
    first = create_record(fake_db)
    candidates_db.resolve_task_candidate('user-1', first.candidate_id, account_generation=3)
    control_path = ('users', 'user-1', 'task_intelligence_control', 'state')
    fake_db.rows[control_path]['account_generation'] = 4

    assert (
        candidates_db.claim_candidate_integration_dispatch('user-1', first.candidate_id, account_generation=3) is None
    )
    first_outbox = fake_db.rows[('users', 'user-1', 'candidate_integration_outbox', first.candidate_id)]
    assert first_outbox['status'] == 'suppressed'
    assert first_outbox['resolution_reason'] == 'account_generation_mismatch'

    fake_db.rows[control_path]['account_generation'] = 3
    second = candidates_db.create_candidate(
        'user-1',
        task_create_proposal(task_change={'description': 'Send the forecast'}),
        idempotency_key='conversation-1:item-2',
        account_generation=3,
    )
    candidates_db.resolve_task_candidate('user-1', second.candidate_id, account_generation=3)
    second_lease = candidates_db.claim_candidate_integration_dispatch(
        'user-1', second.candidate_id, account_generation=3
    )
    assert second_lease is not None
    fake_db.rows[control_path]['account_generation'] = 4
    candidates_db.complete_candidate_integration_dispatch(
        'user-1',
        second.candidate_id,
        account_generation=3,
        lease_token=second_lease,
        succeeded=True,
    )
    second_outbox = fake_db.rows[('users', 'user-1', 'candidate_integration_outbox', second.candidate_id)]
    assert second_outbox['status'] == 'suppressed'


def test_integration_outbox_rejects_completion_from_an_expired_lease(fake_db):
    record = create_record(fake_db)
    candidates_db.resolve_task_candidate('user-1', record.candidate_id, account_generation=3)
    start = datetime(2026, 7, 9, 12, tzinfo=timezone.utc)
    lease_a = candidates_db.claim_candidate_integration_dispatch(
        'user-1', record.candidate_id, account_generation=3, now=start, lease_seconds=300
    )
    lease_b = candidates_db.claim_candidate_integration_dispatch(
        'user-1',
        record.candidate_id,
        account_generation=3,
        now=start.replace(minute=6),
        lease_seconds=300,
    )

    assert lease_a is not None
    assert lease_b is not None and lease_b != lease_a
    assert (
        candidates_db.complete_candidate_integration_dispatch(
            'user-1',
            record.candidate_id,
            account_generation=3,
            lease_token=lease_a,
            succeeded=True,
        )
        is False
    )
    outbox_path = ('users', 'user-1', 'candidate_integration_outbox', record.candidate_id)
    assert fake_db.rows[outbox_path]['status'] == 'processing'
    assert fake_db.rows[outbox_path]['lease_token'] == lease_b
    assert candidates_db.complete_candidate_integration_dispatch(
        'user-1',
        record.candidate_id,
        account_generation=3,
        lease_token=lease_b,
        succeeded=True,
    )
    assert fake_db.rows[outbox_path]['status'] == 'completed'


def test_candidate_queries_have_required_firestore_composite_indexes():
    config = json.loads((Path(__file__).resolve().parents[3] / 'firestore.indexes.json').read_text())
    signatures = {
        (
            index['collectionGroup'],
            tuple(field['fieldPath'] for field in index['fields']),
        )
        for index in config['indexes']
    }

    assert ('candidates', ('account_generation', 'created_at', '__name__')) in signatures
    assert ('candidates', ('status', 'account_generation', 'created_at', '__name__')) in signatures
    assert ('candidate_integration_outbox', ('account_generation', 'status', '__name__')) in signatures
