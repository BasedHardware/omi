"""Regression tests ensuring soft-deleted action-item tombstones (deleted: True) are rejected across Candidate lifecycle surfaces."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import database.action_items as action_items_db
import database.candidate_integration_outbox as integration_outbox_db
import database.candidates as candidates_db
from database import _client
from database.summary_task_links import SummaryTaskConflictError
from models.candidate import CandidateCreate, CandidateStatus, SummaryTaskReference
import routers.staged_tasks as staged_tasks_router
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.task_intelligence import candidate_service, summary_tasks


@pytest.fixture(autouse=True)
def _no_outbound_reminders(monkeypatch):
    import utils.notifications as notifications

    monkeypatch.setattr(notifications, 'send_action_item_update_message', lambda **kwargs: None)
    monkeypatch.setattr(notifications, 'send_action_item_deletion_message', lambda **kwargs: None)


@pytest.fixture
def fake_db(monkeypatch):
    database = StrictFirestore()
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

    def transactional(function):
        def run(transaction):
            with transaction.lock:
                return function(transaction)

        return run

    monkeypatch.setattr(_client, '_firestore_client', database)
    monkeypatch.setattr(candidates_db, 'db', database)
    monkeypatch.setattr(candidates_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(integration_outbox_db, 'db', database)
    monkeypatch.setattr(integration_outbox_db, 'get_firestore_client', lambda: database)
    monkeypatch.setattr(integration_outbox_db.firestore, 'transactional', transactional)
    monkeypatch.setattr(candidate_service, 'account_deletion_blocks_user_work', lambda uid: False)
    candidate_service.clear_workstream_candidate_resolver()
    candidate_service.task_links.clear_workstream_goal_resolver()
    candidate_service.task_links.register_goal_existence_resolver(lambda uid, goal_id: goal_id == 'goal-1')
    yield database
    candidate_service.clear_workstream_candidate_resolver()
    candidate_service.task_links.clear_workstream_goal_resolver()


def _mutation_proposal(task_id: str = 'task-deleted-1') -> CandidateCreate:
    return CandidateCreate.model_validate(
        {
            'subject_kind': 'task',
            'proposed_action': 'complete',
            'task_id': task_id,
            'task_change': {'status': 'completed'},
            'capture_confidence': 0.95,
            'ownership_confidence': 1.0,
            'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
            'source_surface': 'conversation',
        }
    )


def test_accept_candidate_rejects_soft_deleted_task_tombstone(fake_db, monkeypatch):
    record = candidates_db.create_candidate(
        'user-1',
        _mutation_proposal('task-deleted-1'),
        idempotency_key='conv-1:complete-deleted',
        account_generation=3,
    )
    monkeypatch.setattr(
        action_items_db,
        'get_action_item',
        lambda uid, tid: {'id': tid, 'description': 'Old task', 'deleted': True, 'goal_id': None, 'workstream_id': None},
    )

    with pytest.raises(candidates_db.CandidateNotFoundError, match='task:task-deleted-1'):
        candidate_service.accept_candidate('user-1', record.candidate_id, account_generation=3)


def test_resolve_task_candidate_transaction_rejects_soft_deleted_tombstone(fake_db):
    fake_db.rows[('users', 'user-1', 'action_items', 'task-deleted-2')] = {
        'id': 'task-deleted-2',
        'task_id': 'task-deleted-2',
        'description': 'Soft-deleted task',
        'status': 'active',
        'completed': False,
        'deleted': True,
        'account_generation': 3,
    }
    record = candidates_db.create_candidate(
        'user-1',
        _mutation_proposal('task-deleted-2'),
        idempotency_key='conv-1:complete-deleted-tx',
        account_generation=3,
    )

    with pytest.raises(candidates_db.CandidateNotFoundError, match='task:task-deleted-2'):
        candidates_db.resolve_task_candidate('user-1', record.candidate_id, account_generation=3)


def test_claim_task_integration_fails_missing_task_on_soft_deleted_tombstone(monkeypatch):
    monkeypatch.setattr(
        integration_outbox_db,
        'claim_candidate_integration_dispatch',
        lambda uid, cid, **kw: 'lease-token-1',
    )
    monkeypatch.setattr(
        action_items_db,
        'get_action_item',
        lambda uid, tid: {'id': tid, 'description': 'Deleted before outbox export', 'deleted': True},
    )
    failed_mock = MagicMock()
    monkeypatch.setattr(candidate_service, '_fail_missing_task', failed_mock)

    lease_token, task = candidate_service._claim_task_integration(
        'user-1',
        'cand-1',
        'task-deleted-3',
        account_generation=3,
    )

    assert lease_token == 'lease-token-1'
    assert task is None
    failed_mock.assert_called_once_with(
        'user-1',
        'cand-1',
        account_generation=3,
        lease_token='lease-token-1',
        firestore_client=None,
    )


def test_prepare_summary_task_rejects_soft_deleted_linked_task_tombstone(fake_db, monkeypatch):
    fake_db.rows[('users', 'user-1', 'action_items', 'task-deleted-4')] = {
        'id': 'task-deleted-4',
        'candidate_id': 'cand-accepted-4',
        'deleted': True,
    }
    fake_row = SimpleNamespace(
        item=SimpleNamespace(target_task_id='task-deleted-4'),
        proposal=lambda: None,
    )
    monkeypatch.setattr(summary_tasks, 'read_summary_task_row', lambda uid, selected: fake_row)

    with pytest.raises(SummaryTaskConflictError, match='Linked task is unavailable'):
        summary_tasks.prepare_summary_task(
            'user-1',
            SummaryTaskReference(
                conversation_id='conversation-1',
                action_item_index=0,
                expected_description='Send the budget',
            ),
            idempotency_key='summary-deleted-1',
            account_generation=3,
        )


def test_staged_tasks_accept_candidate_does_not_return_soft_deleted_tombstone(monkeypatch):
    monkeypatch.setattr(
        action_items_db,
        'get_action_item',
        lambda uid, tid: {'id': tid, 'description': 'Tombstone', 'deleted': True},
    )
    accepted_candidate = SimpleNamespace(
        candidate_id='cand-staged-1',
        status=CandidateStatus.accepted,
        result_task_id='task-deleted-5',
    )

    result = staged_tasks_router._accept_candidate('user-1', accepted_candidate, account_generation=3)

    assert result == {'id': 'task-deleted-5', 'candidate_id': 'cand-staged-1'}
    assert 'deleted' not in result


def test_resolve_task_candidate_accepted_summary_replay_rejects_soft_deleted_tombstone(fake_db, monkeypatch):
    create_proposal = CandidateCreate.model_validate(
        {
            'subject_kind': 'task',
            'proposed_action': 'create',
            'task_change': {'description': 'Send the budget'},
            'capture_confidence': 0.95,
            'ownership_confidence': 1.0,
            'evidence_refs': [{'kind': 'conversation', 'id': 'conversation-1', 'scope': 'canonical'}],
            'source_surface': 'conversation',
        }
    )
    record = candidates_db.create_candidate(
        'user-1',
        create_proposal,
        idempotency_key='conv-1:summary-replay-deleted',
        account_generation=3,
    )
    receipt = candidates_db.resolve_task_candidate('user-1', record.candidate_id, account_generation=3)
    assert receipt.task_id is not None

    fake_db.rows[('users', 'user-1', 'action_items', receipt.task_id)] = {
        **fake_db.rows[('users', 'user-1', 'action_items', receipt.task_id)],
        'conversation_id': 'conversation-1',
        'deleted': True,
    }
    fake_row = SimpleNamespace(
        conversation_id='conversation-1',
        item=SimpleNamespace(target_task_id=receipt.task_id),
        proposal=lambda: create_proposal,
        reference=SimpleNamespace(),
        linked_patch=lambda tid: {},
    )
    monkeypatch.setattr(candidates_db, 'read_summary_task_row', lambda uid, selected, transaction=None: fake_row)

    with pytest.raises(candidates_db.CandidateNotFoundError, match='Linked task not found'):
        candidates_db.resolve_task_candidate(
            'user-1',
            record.candidate_id,
            account_generation=3,
            summary_item=SummaryTaskReference(
                conversation_id='conversation-1',
                action_item_index=0,
                expected_description='Send the budget',
            ),
        )

