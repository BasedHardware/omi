"""Staged-task review controls: promote-by-id and clear-all.

Staged tasks are the buffer of AI-extracted task candidates a user reviews before they become
action items (Nik's #5079 "Task Detection Is Too Aggressive"). This adds the two missing review
verbs: promote a specific chosen candidate (POST /v1/staged-tasks/{task_id}/promote) and clear the
whole active queue in one call (DELETE /v1/staged-tasks).

- promote_staged_task now takes an optional task_id: when given it promotes that candidate through
  the same dedup/merge/create tail as the top-scored path (default task_id=None is unchanged).
- clear_staged_tasks batch-deletes only active (completed==False) staged tasks, preserving history.

Test isolation: the modules import cleanly, so they are imported normally and the collection is
faked via monkeypatch.setattr(staged_tasks_db, '_user_col'/'db') (no sys.modules mutation).
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from database import action_items as action_items_db
from database import candidates as candidates_db
from database import staged_tasks as staged_tasks_db
import routers.staged_tasks as r
from datetime import datetime, timezone

from models.candidate import CandidateCreate, CandidateRecord, CandidateStatus
from models.task_intelligence import TaskWorkflowControl


@pytest.fixture(autouse=True)
def legacy_workflow_mode(monkeypatch):
    monkeypatch.setattr(r.task_control_db, 'get_task_workflow_control', lambda uid: TaskWorkflowControl())


def _make_doc(doc_id, data):
    doc = MagicMock()
    doc.id = doc_id
    doc.to_dict.return_value = data
    return doc


def _stub_staged_by_id(monkeypatch, task_id, data):
    """Stub _user_col so document(task_id).get() returns a doc with `data` (exists=False if None)."""
    snap = MagicMock()
    snap.exists = data is not None
    snap.id = task_id
    snap.to_dict.return_value = data

    update_calls = {}
    ref = MagicMock()
    ref.get.return_value = snap
    ref.update.side_effect = lambda payload: update_calls.update(payload)

    fake_col = MagicMock()
    fake_col.document.return_value = ref
    monkeypatch.setattr(staged_tasks_db, "_user_col", lambda uid, name: fake_col)
    return fake_col, update_calls


def _stub_clear(monkeypatch, doc_ids):
    """Stub _user_col + db.batch for clear_staged_tasks."""
    fake_query = MagicMock()
    fake_query.select.return_value = fake_query
    fake_query.stream.return_value = iter([_make_doc(d, {}) for d in doc_ids])

    fake_col = MagicMock()
    fake_col.where.return_value = fake_query

    batch = MagicMock()
    monkeypatch.setattr(staged_tasks_db, "_user_col", lambda uid, name: fake_col)
    monkeypatch.setattr(staged_tasks_db, "db", MagicMock(batch=MagicMock(return_value=batch)))
    return fake_col, fake_query, batch


# --- promote_staged_task(task_id=...) ---


class TestPromoteById:
    def test_promotes_the_specified_candidate(self, monkeypatch):
        fake_col, update_calls = _stub_staged_by_id(
            monkeypatch, "staged-x", {"id": "staged-x", "description": "Unique task", "completed": False}
        )
        monkeypatch.setattr(action_items_db, "get_active_action_item_by_description", lambda uid, desc: None)
        monkeypatch.setattr(action_items_db, "create_action_item", lambda uid, data: "fresh-1")
        monkeypatch.setattr(
            action_items_db, "get_action_item", lambda uid, aid: {"id": aid, "description": "Unique task"}
        )

        result = staged_tasks_db.promote_staged_task("uid", task_id="staged-x")

        assert result == {"id": "fresh-1", "description": "Unique task"}
        fake_col.document.assert_any_call("staged-x")  # promoted the chosen doc, not a scored query
        assert update_calls.get("completed") is True
        assert update_calls.get("promoted_to") == "fresh-1"

    def test_dedup_tail_still_applies_when_promoting_by_id(self, monkeypatch):
        _stub_staged_by_id(
            monkeypatch, "staged-y", {"id": "staged-y", "description": "Follow up on Volt", "completed": False}
        )
        existing = {"id": "existing-1", "description": "Follow up on Volt", "completed": False}
        monkeypatch.setattr(action_items_db, "get_active_action_item_by_description", lambda uid, desc: existing)
        create_called = []
        monkeypatch.setattr(
            action_items_db, "create_action_item", lambda uid, data: create_called.append(data) or "nope"
        )

        result = staged_tasks_db.promote_staged_task("uid", task_id="staged-y")

        assert result == existing
        assert create_called == []  # dedup guard fired instead of creating a duplicate

    def test_nonexistent_id_returns_none(self, monkeypatch):
        _stub_staged_by_id(monkeypatch, "ghost", None)  # snap.exists = False
        assert staged_tasks_db.promote_staged_task("uid", task_id="ghost") is None

    def test_already_completed_returns_none(self, monkeypatch):
        _stub_staged_by_id(monkeypatch, "done-1", {"id": "done-1", "description": "x", "completed": True})
        assert staged_tasks_db.promote_staged_task("uid", task_id="done-1") is None


# --- clear_staged_tasks ---


class TestClearStagedTasks:
    def test_deletes_active_and_returns_count(self, monkeypatch):
        fake_col, fake_query, batch = _stub_clear(monkeypatch, ["a", "b", "c"])
        count = staged_tasks_db.clear_staged_tasks("uid")
        assert count == 3
        assert batch.delete.call_count == 3
        batch.commit.assert_called_once()
        fake_col.where.assert_called_once()  # scoped, not an unfiltered wipe
        fake_query.select.assert_called_once()  # IDs-only projection

    def test_empty_queue_returns_zero_without_commit(self, monkeypatch):
        _fake_col, _fake_query, batch = _stub_clear(monkeypatch, [])
        assert staged_tasks_db.clear_staged_tasks("uid") == 0
        batch.delete.assert_not_called()
        batch.commit.assert_not_called()

    def test_terminal_candidate_suppression_closes_row_without_promoted_task(self, monkeypatch):
        ref = MagicMock()
        collection = MagicMock()
        collection.document.return_value = ref
        monkeypatch.setattr(staged_tasks_db, '_user_col', lambda uid, name: collection)

        staged_tasks_db.suppress_staged_task_for_terminal_candidate('user-1', 'staged-1', reason='rejected')

        patch = ref.update.call_args.args[0]
        assert patch['completed'] is True
        assert patch['candidate_terminal_reason'] == 'rejected'
        assert patch['promotion_skipped'] == 'candidate_terminal'
        assert 'promoted_to' not in patch


# --- router handlers (called directly) ---


class TestRouterHandlers:
    def test_promote_by_id_success_shape(self, monkeypatch):
        monkeypatch.setattr(
            r.staged_tasks_db,
            "promote_staged_task",
            lambda uid, task_id, **kwargs: {"id": "a1", "description": "x"},
        )
        result = r.promote_staged_task_by_id("a1", uid="u1")
        assert result == {"promoted": True, "reason": None, "promoted_task": {"id": "a1", "description": "x"}}

    def test_promote_by_id_404_when_missing(self, monkeypatch):
        monkeypatch.setattr(r.staged_tasks_db, "promote_staged_task", lambda uid, task_id, **kwargs: None)
        with pytest.raises(HTTPException) as ei:
            r.promote_staged_task_by_id("ghost", uid="u1")
        assert ei.value.status_code == 404

    def test_clear_returns_deleted_count(self, monkeypatch):
        monkeypatch.setattr(r.staged_tasks_db, "clear_staged_tasks", lambda uid: 5)
        assert r.clear_staged_tasks(uid="u1") == {"status": "ok", "deleted_count": 5}


class TestModeAwareSidecarReconciliation:
    @staticmethod
    def _write_control(monkeypatch):
        monkeypatch.setattr(
            r.task_control_db,
            'get_task_workflow_control',
            lambda uid: TaskWorkflowControl(workflow_mode='write', account_generation=7),
        )

    def test_normal_and_duplicate_promotion_resolve_the_exact_sidecar(self, monkeypatch):
        self._write_control(monkeypatch)
        reconciled = []
        rows = {
            'normal': {'id': 'normal', 'description': 'Normal', 'completed': False},
            'duplicate': {
                'id': 'duplicate',
                'description': 'Duplicate',
                'completed': False,
                'promotion_skipped': 'duplicate',
            },
        }
        monkeypatch.setattr(r, '_staged_row', lambda uid, staged_id: rows[staged_id])
        monkeypatch.setattr(
            r,
            '_reconcile_write_sidecar',
            lambda uid, row, **kwargs: reconciled.append((row['id'], kwargs)) or True,
        )
        monkeypatch.setattr(
            r,
            '_claim_write_promotion',
            lambda *args, **kwargs: (MagicMock(status=CandidateStatus.pending), 'claim-token'),
        )
        monkeypatch.setattr(
            r,
            '_begin_write_promotion',
            lambda uid, row, candidate, claim_token, **kwargs: candidates_db.LegacyPromotionReservation(
                task_id='task-existing' if row['id'] == 'duplicate' else 'task-1',
                kind='existing' if row['id'] == 'duplicate' else 'create',
            ),
        )
        results = iter(
            [
                {'id': 'task-1', '_staged_task_id': 'normal'},
                {'id': 'task-existing', '_staged_task_id': 'duplicate'},
            ]
        )

        def promote(*args, **kwargs):
            result = next(results)
            task_id = kwargs['task_id']
            rows[task_id].update(completed=True, promoted_to=result['id'])
            return result

        monkeypatch.setattr(r.staged_tasks_db, 'promote_staged_task', promote)

        r.promote_staged_task_by_id('normal', uid='u1')
        r.promote_staged_task_by_id('duplicate', uid='u1')

        assert reconciled[0][1]['status'].value == 'accepted'
        assert reconciled[0][1]['result_task_id'] == 'task-1'
        assert reconciled[1][1]['reason'] == 'duplicate'
        assert reconciled[1][1]['result_task_id'] == 'task-existing'

    def test_delete_and_clear_reject_every_write_mode_sidecar(self, monkeypatch):
        self._write_control(monkeypatch)
        rows = [{'id': f'staged-{index}', 'description': f'Task {index}', 'completed': False} for index in range(501)]
        reconciled = []
        monkeypatch.setattr(r.staged_tasks_db, 'get_all_staged_tasks_for_migration', lambda uid: rows)
        monkeypatch.setattr(r.staged_tasks_db, 'delete_staged_task', lambda uid, task_id: True)
        monkeypatch.setattr(r.staged_tasks_db, 'clear_staged_tasks', lambda uid: len(rows))
        monkeypatch.setattr(
            r,
            '_reconcile_write_sidecar',
            lambda uid, row, **kwargs: reconciled.append((row['id'], kwargs['reason'])) or True,
        )

        r.delete_staged_task('staged-0', uid='u1')
        assert reconciled == [('staged-0', 'legacy_delete')]
        reconciled.clear()
        result = r.clear_staged_tasks(uid='u1')
        assert result['deleted_count'] == 501
        assert len(reconciled) == 501
        assert {reason for _, reason in reconciled} == {'legacy_clear'}

    def test_promote_surfaces_reconciliation_failure_and_retry_heals_terminal_row(self, monkeypatch):
        self._write_control(monkeypatch)
        row = {'id': 'staged-1', 'description': 'Send budget', 'completed': False}
        promote_calls = []

        def promote(*args, **kwargs):
            promote_calls.append(kwargs)
            row.update(completed=True, promoted_to='task-1')
            return {'id': 'task-1', 'description': 'Send budget', '_staged_task_id': 'staged-1'}

        outcomes = iter([False, True])
        monkeypatch.setattr(r, '_staged_row', lambda uid, staged_id: row)
        monkeypatch.setattr(
            r,
            '_claim_write_promotion',
            lambda *args, **kwargs: (MagicMock(status=CandidateStatus.pending), 'claim-token'),
        )
        monkeypatch.setattr(
            r,
            '_begin_write_promotion',
            lambda *args, **kwargs: candidates_db.LegacyPromotionReservation(task_id='task-1', kind='create'),
        )
        monkeypatch.setattr(
            r.candidates_db,
            'begin_candidate_legacy_promotion',
            lambda *args, **kwargs: candidates_db.LegacyPromotionReservation(task_id='task-1', kind='committed'),
        )
        monkeypatch.setattr(r.staged_tasks_db, 'promote_staged_task', promote)
        monkeypatch.setattr(r, '_reconcile_write_sidecar', lambda *args, **kwargs: next(outcomes))
        monkeypatch.setattr(
            r.action_items_db,
            'get_action_item',
            lambda uid, task_id: {'id': task_id, 'description': 'Send budget'},
        )

        with pytest.raises(HTTPException) as first:
            r.promote_staged_task_by_id('staged-1', uid='u1')
        assert first.value.status_code == 503

        retried = r.promote_staged_task_by_id('staged-1', uid='u1')
        assert retried['promoted_task']['id'] == 'task-1'
        assert len(promote_calls) == 1

    @pytest.mark.parametrize('status', [CandidateStatus.rejected, CandidateStatus.expired])
    def test_route_never_mutates_legacy_state_for_terminal_sidecar(self, monkeypatch, status):
        self._write_control(monkeypatch)
        row = {'id': 'staged-1', 'description': 'Send budget', 'completed': False}
        proposal = r.proposal_from_legacy_staged(row)
        candidate = CandidateRecord(
            **proposal.model_dump(mode='python'),
            candidate_id='candidate-1',
            account_generation=7,
            idempotency_key='idem',
            status=status,
            resolution_reason=status.value,
            created_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
            resolved_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
        )
        monkeypatch.setattr(r, '_staged_row', lambda uid, staged_id: row)
        monkeypatch.setattr(
            r,
            '_create_candidate_from_staged_row',
            lambda *args, **kwargs: candidate,
        )
        suppressed = []
        monkeypatch.setattr(
            r.staged_tasks_db,
            'suppress_staged_task_for_terminal_candidate',
            lambda uid, staged_id, **kwargs: suppressed.append((staged_id, kwargs['reason']))
            or row.update(completed=True),
        )
        monkeypatch.setattr(
            r.staged_tasks_db,
            'promote_staged_task',
            lambda *args, **kwargs: pytest.fail('terminal Candidate must fence legacy action-item creation'),
        )

        with pytest.raises(HTTPException) as error:
            r.promote_staged_task_by_id('staged-1', uid='u1')

        assert error.value.status_code == 404
        assert row['completed'] is True
        assert suppressed == [('staged-1', status.value)]

    def test_top_promotion_suppresses_terminal_row_and_advances_to_pending(self, monkeypatch):
        self._write_control(monkeypatch)
        terminal_row = {'id': 'staged-terminal', 'description': 'Old task', 'completed': False}
        pending_row = {'id': 'staged-pending', 'description': 'Next task', 'completed': False}
        terminal = MagicMock(status=CandidateStatus.rejected)
        pending = MagicMock(status=CandidateStatus.pending)
        selected_rows = iter([terminal_row, pending_row])
        promoted = []
        monkeypatch.setattr(r.staged_tasks_db, 'get_all_staged_tasks_for_migration', lambda uid: [])
        monkeypatch.setattr(
            r.staged_tasks_db,
            'get_top_staged_task_for_promotion',
            lambda uid: next(selected_rows),
        )

        def claim(uid, row, **kwargs):
            if row['id'] == 'staged-terminal':
                row['completed'] = True
                return terminal, None
            return pending, 'claim-token'

        def promote(uid, task_id, **kwargs):
            promoted.append(task_id)
            pending_row.update(completed=True, promoted_to='task-next')
            return {'id': 'task-next', '_staged_task_id': task_id}

        monkeypatch.setattr(r, '_claim_write_promotion', claim)
        monkeypatch.setattr(
            r,
            '_begin_write_promotion',
            lambda *args, **kwargs: candidates_db.LegacyPromotionReservation(task_id='task-next', kind='create'),
        )
        monkeypatch.setattr(r.staged_tasks_db, 'promote_staged_task', promote)
        monkeypatch.setattr(r, '_staged_row', lambda uid, staged_id: pending_row)
        monkeypatch.setattr(r, '_reconcile_write_sidecar', lambda *args, **kwargs: True)

        result = r.promote_staged_task(uid='u1')

        assert terminal_row['completed'] is True
        assert promoted == ['staged-pending']
        assert result['promoted_task']['id'] == 'task-next'

    @pytest.mark.parametrize(
        ('status', 'result_task_id'),
        [
            (CandidateStatus.rejected, None),
            (CandidateStatus.expired, None),
            (CandidateStatus.accepted, 'another-task'),
        ],
    )
    def test_promotion_reconciliation_rejects_wrong_terminal_sidecar(self, monkeypatch, status, result_task_id):
        proposal = r.proposal_from_legacy_staged({'id': 'staged-1', 'description': 'Send budget'})
        candidate = CandidateRecord(
            **proposal.model_dump(mode='python'),
            candidate_id='candidate-1',
            account_generation=7,
            idempotency_key='idem',
            status=status,
            result_task_id=result_task_id,
            resolution_reason=status.value,
            created_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
            resolved_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
        )
        monkeypatch.setattr(r, '_create_candidate_from_staged_row', lambda *args, **kwargs: candidate)

        assert (
            r._reconcile_write_sidecar(
                'u1',
                {'id': 'staged-1', 'description': 'Send budget'},
                account_generation=7,
                status=CandidateStatus.accepted,
                result_task_id='task-1',
                reason='legacy_promoted',
            )
            is False
        )

    def test_read_mode_legacy_migrations_are_noops(self, monkeypatch):
        monkeypatch.setattr(
            r.task_control_db,
            'get_task_workflow_control',
            lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=7),
        )
        monkeypatch.setattr(
            r.staged_tasks_db,
            'migrate_ai_tasks',
            lambda uid: pytest.fail('read mode cannot invoke staged migration writer'),
        )
        monkeypatch.setattr(
            r.staged_tasks_db,
            'migrate_conversation_items_to_staged',
            lambda uid: pytest.fail('read mode cannot invoke staged migration writer'),
        )

        assert r.migrate_ai_tasks(uid='u1')['status'].startswith('canonical read mode')
        assert r.migrate_conversation_items(uid='u1') == {'status': 'ok', 'migrated': 0, 'deleted': 0}

    def test_read_mode_by_id_routes_ignore_non_staged_candidates(self, monkeypatch):
        monkeypatch.setattr(
            r.task_control_db,
            'get_task_workflow_control',
            lambda uid: TaskWorkflowControl(workflow_mode='read', account_generation=7),
        )
        proposal = CandidateCreate.model_validate(
            {
                'subject_kind': 'task',
                'proposed_action': 'update',
                'task_id': 'task-1',
                'task_change': {'description': 'Revise the budget'},
                'capture_confidence': 0.8,
                'ownership_confidence': 1,
                'evidence_refs': [{'kind': 'conversation', 'id': 'c1', 'scope': 'canonical'}],
                'source_surface': 'conversation',
            }
        )
        candidate = CandidateRecord(
            **proposal.model_dump(mode='python'),
            candidate_id='candidate-update',
            account_generation=7,
            idempotency_key='idem',
            created_at=datetime(2026, 7, 9, tzinfo=timezone.utc),
        )
        monkeypatch.setattr(r.candidates_db, 'get_candidate', lambda uid, candidate_id: candidate)
        monkeypatch.setattr(
            r.candidate_service,
            'reject_candidate',
            lambda *args, **kwargs: pytest.fail('legacy delete cannot reject a universal mutation Candidate'),
        )
        monkeypatch.setattr(
            r.candidate_service,
            'accept_candidate',
            lambda *args, **kwargs: pytest.fail('legacy promote cannot accept a universal mutation Candidate'),
        )

        assert r.delete_staged_task(candidate.candidate_id, uid='u1') == {'status': 'ok'}
        with pytest.raises(HTTPException) as error:
            r.promote_staged_task_by_id(candidate.candidate_id, uid='u1')
        assert error.value.status_code == 404

        candidate.source_surface = 'legacy_staged'
        candidate.proposed_action = 'create'
        candidate.task_id = None
        candidate.account_generation = 6
        assert r.delete_staged_task(candidate.candidate_id, uid='u1') == {'status': 'ok'}
        with pytest.raises(HTTPException) as stale_error:
            r.promote_staged_task_by_id(candidate.candidate_id, uid='u1')
        assert stale_error.value.status_code == 404
