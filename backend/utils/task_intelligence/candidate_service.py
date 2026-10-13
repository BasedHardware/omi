"""Candidate lifecycle orchestration and post-commit integration policy."""

import asyncio
import logging
from typing import Optional, Protocol

import database.action_items as action_items_db
import database.candidate_integration_outbox as integration_outbox_db
import database.candidates as candidates_db
import database.workstreams as workstreams_db
from database.durable_queue import OutcomeKind, ProcessOutcome, drain_isolated
from models.candidate import (
    CandidateAction,
    CandidateCreate,
    CandidateRecord,
    CandidateResolutionReceipt,
    CandidateStatus,
    CandidateSubjectKind,
    SummaryTaskReference,
)
from utils.executors import postprocess_executor, submit_with_context
from utils.notifications import sync_action_item_reminder
from utils.observability.fallback import record_fallback
from utils.task_sync import auto_sync_action_item
from utils.task_intelligence import task_links
from utils.task_intelligence.workstream_index import refresh_workstream_association_index

logger = logging.getLogger(__name__)


class WorkstreamCandidateResolver(Protocol):
    def __call__(self, uid: str, candidate: CandidateRecord, account_generation: int) -> CandidateResolutionReceipt: ...


_workstream_resolver: Optional[WorkstreamCandidateResolver] = workstreams_db.resolve_workstream_candidate


def register_workstream_candidate_resolver(resolver: WorkstreamCandidateResolver) -> None:
    global _workstream_resolver
    _workstream_resolver = resolver


def clear_workstream_candidate_resolver() -> None:
    global _workstream_resolver
    _workstream_resolver = None


def create_candidate(
    uid: str,
    proposal: CandidateCreate,
    *,
    idempotency_key: str,
    account_generation: int,
) -> CandidateRecord:
    return candidates_db.create_candidate(
        uid,
        proposal,
        idempotency_key=idempotency_key,
        account_generation=account_generation,
    )


def _fail_missing_task(uid: str, candidate_id: str, *, account_generation: int, lease_token: str) -> None:
    integration_outbox_db.complete_candidate_integration_dispatch(
        uid,
        candidate_id,
        account_generation=account_generation,
        lease_token=lease_token,
        succeeded=False,
        error_text='task_not_found',
    )
    record_fallback(
        component='other',
        from_mode='candidate_integration',
        to_mode='retry_queue',
        reason='other',
        outcome='degraded',
    )


def _record_integration_result(
    uid: str,
    candidate_id: str,
    task: dict,
    *,
    account_generation: int,
    lease_token: str,
) -> bool:
    """Run the provider sync and complete or fail the lease. Blocking."""
    try:
        result = asyncio.run(auto_sync_action_item(uid, task, skip_apple_reminders=False))
    except Exception:
        integration_outbox_db.complete_candidate_integration_dispatch(
            uid,
            candidate_id,
            account_generation=account_generation,
            lease_token=lease_token,
            succeeded=False,
            error_text='integration_exception',
        )
        record_fallback(
            component='other',
            from_mode='candidate_integration',
            to_mode='retry_queue',
            reason='other',
            outcome='degraded',
        )
        raise
    terminal_noop = result.get('reason') in {
        'no_default_integration',
        'integration_not_found',
        'integration_not_connected',
        'client_handles_sync',
    }
    succeeded = bool(result.get('synced')) or terminal_noop
    integration_outbox_db.complete_candidate_integration_dispatch(
        uid,
        candidate_id,
        account_generation=account_generation,
        lease_token=lease_token,
        succeeded=succeeded,
        error_text=None if succeeded else 'integration_not_synced',
    )
    if not succeeded:
        record_fallback(
            component='other',
            from_mode='candidate_integration',
            to_mode='retry_queue',
            reason='other',
            outcome='degraded',
        )
    return succeeded


def _claim_task_integration(uid: str, candidate_id: str, task_id: str, *, account_generation: int):
    """Claim the outbox row and load the task. ``(None, None)`` when the claim is lost."""
    lease_token = integration_outbox_db.claim_candidate_integration_dispatch(
        uid,
        candidate_id,
        account_generation=account_generation,
    )
    if lease_token is None:
        return None, None
    task = action_items_db.get_action_item(uid, task_id)
    if not task:
        _fail_missing_task(uid, candidate_id, account_generation=account_generation, lease_token=lease_token)
        return lease_token, None
    return lease_token, task


def _retain_lease_for_provider_call(uid: str, candidate_id: str, lease_token: str) -> bool:
    """Fresh lease iff this token still owns the processing row. Otherwise do not export."""
    owned = integration_outbox_db.refresh_candidate_integration_lease(
        uid,
        candidate_id,
        lease_token=lease_token,
    )
    if not owned:
        logger.info(
            'candidate integration lease lost before provider call uid=%s candidate_id=%s',
            uid,
            candidate_id,
        )
    return owned


def _dispatch_task_integration(uid: str, candidate_id: str, task_id: str, *, account_generation: int) -> bool:
    """Accept path: claim, then schedule the provider sync. Returns before it finishes."""
    lease_token, task = _claim_task_integration(uid, candidate_id, task_id, account_generation=account_generation)
    if lease_token is None or task is None:
        return False

    def run_sync() -> None:
        # The pool may have queued this past the 300s claim lease. Re-stamp only
        # while this token still owns the row; a sweeper that took it must be
        # the only provider call.
        if not _retain_lease_for_provider_call(uid, candidate_id, lease_token):
            return
        _record_integration_result(
            uid,
            candidate_id,
            task,
            account_generation=account_generation,
            lease_token=lease_token,
        )

    submit_with_context(postprocess_executor, run_sync)
    return True


def dispatch_task_integration_blocking(uid: str, candidate_id: str, task_id: str, *, account_generation: int) -> bool:
    """Claim, confirm the lease, sync, and complete before returning.

    True when this call recorded the attempt (success, terminal noop, or retryable failure).
    False when the row was not claimed or the lease was lost before the provider call.
    A provider exception is recorded as a failure and re-raised.
    """
    lease_token, task = _claim_task_integration(uid, candidate_id, task_id, account_generation=account_generation)
    if lease_token is None:
        return False
    if task is None:
        return True
    if not _retain_lease_for_provider_call(uid, candidate_id, lease_token):
        return False
    _record_integration_result(
        uid,
        candidate_id,
        task,
        account_generation=account_generation,
        lease_token=lease_token,
    )
    return True


def drain_candidate_integrations(uid: str, *, account_generation: int, limit: int = 100) -> int:
    items = integration_outbox_db.list_candidate_integration_dispatches(
        uid,
        account_generation=account_generation,
        limit=limit,
    )

    def process_one(item: dict) -> ProcessOutcome:
        candidate_id = item.get('candidate_id')
        task_id = item.get('task_id')
        if not isinstance(candidate_id, str) or not isinstance(task_id, str):
            if isinstance(candidate_id, str):
                integration_outbox_db.dead_letter_malformed_candidate_integration(
                    uid,
                    candidate_id,
                    account_generation=account_generation,
                    error_text='malformed integration outbox item',
                )
            return ProcessOutcome.reject('malformed integration outbox item', reason='malformed')
        scheduled = _dispatch_task_integration(
            uid,
            candidate_id,
            task_id,
            account_generation=account_generation,
        )
        if not scheduled:
            return ProcessOutcome.retry('not_scheduled', reason='not_scheduled')
        return ProcessOutcome.ack()

    results = drain_isolated(items, process_one)
    return sum(1 for result in results if result.outcome.kind == OutcomeKind.ACK)


def _sync_task_reminder(uid: str, task_id: str) -> None:
    """Reconcile the client-scheduled reminder for a task an accepted Candidate wrote (#5085).

    Accepting a suggestion creates tasks with a due date and can reschedule or complete an
    existing one, so it owes the same reconciliation as the action-item routes.
    """
    task = action_items_db.get_action_item(uid, task_id)
    if task is None:
        return
    sync_action_item_reminder(
        user_id=uid,
        action_item_id=task_id,
        description=task.get('description', ''),
        completed=bool(task.get('completed')),
        due_at=task.get('due_at'),
        status=task.get('status'),
        deleted=bool(task.get('deleted')),
    )


def accept_candidate(
    uid: str,
    candidate_id: str,
    *,
    account_generation: int,
    summary_item: Optional[SummaryTaskReference] = None,
    review_edits: Optional[dict] = None,
) -> CandidateResolutionReceipt:
    candidate = candidates_db.get_candidate(uid, candidate_id)
    if candidate is None:
        raise candidates_db.CandidateNotFoundError(candidate_id)
    if candidate.subject_kind == CandidateSubjectKind.workstream:
        if summary_item is not None:
            raise candidates_db.CandidateConflictError('Summary promotion requires a task-create Candidate')
        if _workstream_resolver is None:
            raise candidates_db.WorkstreamCandidateResolverUnavailableError(
                'Ticket 04 workstream resolver is not registered'
            )
        try:
            receipt = _workstream_resolver(uid, candidate, account_generation)
        except workstreams_db.WorkstreamNotFoundError as exc:
            raise candidates_db.CandidateNotFoundError(candidate_id) from exc
        except workstreams_db.WorkstreamGenerationMismatchError as exc:
            raise candidates_db.CandidateGenerationMismatchError(candidate_id) from exc
        except workstreams_db.WorkstreamConflictError as exc:
            raise candidates_db.CandidateConflictError(str(exc)) from exc
        if receipt.workstream_id:
            refresh_workstream_association_index(uid, receipt.workstream_id)
        if receipt.task_id:
            _dispatch_task_integration(
                uid,
                candidate_id,
                receipt.task_id,
                account_generation=account_generation,
            )
            _sync_task_reminder(uid, receipt.task_id)
        return receipt

    if review_edits is not None:
        from utils.review_candidate_edits import edited_candidate

        candidate = edited_candidate(candidate, review_edits)
    expected_task_links = None
    final_goal_id = candidate.goal_id
    final_workstream_id = candidate.workstream_id
    if candidate.proposed_action != CandidateAction.create:
        task_id = candidate.task_id
        if task_id is None:
            raise candidates_db.CandidateConflictError('task mutation Candidate is missing task_id')
        task = action_items_db.get_action_item(uid, task_id)
        if task is None:
            raise candidates_db.CandidateNotFoundError(f'task:{task_id}')
        expected_task_links = (task.get('goal_id'), task.get('workstream_id'))
        if final_goal_id is None:
            final_goal_id = expected_task_links[0]
        if final_workstream_id is None:
            final_workstream_id = expected_task_links[1]
    task_links.validate_task_links(uid, goal_id=final_goal_id, workstream_id=final_workstream_id)
    if summary_item is None and review_edits is not None:
        receipt = candidates_db.resolve_task_candidate(
            uid,
            candidate_id,
            account_generation=account_generation,
            expected_task_links=expected_task_links,
            review_edits=review_edits,
        )
    elif summary_item is None:
        receipt = candidates_db.resolve_task_candidate(
            uid, candidate_id, account_generation=account_generation, expected_task_links=expected_task_links
        )
    else:
        receipt = candidates_db.resolve_task_candidate(
            uid,
            candidate_id,
            account_generation=account_generation,
            expected_task_links=expected_task_links,
            summary_item=summary_item,
        )
    if candidate.proposed_action == CandidateAction.create and receipt.task_id:
        _dispatch_task_integration(
            uid,
            candidate_id,
            receipt.task_id,
            account_generation=account_generation,
        )
    if receipt.task_id:
        _sync_task_reminder(uid, receipt.task_id)
    return receipt


def reject_candidate(
    uid: str,
    candidate_id: str,
    *,
    reason: Optional[str],
    account_generation: int,
) -> CandidateResolutionReceipt:
    return candidates_db.resolve_candidate_without_mutation(
        uid,
        candidate_id,
        status=CandidateStatus.rejected,
        reason=reason,
        account_generation=account_generation,
    )


def expire_candidate(
    uid: str,
    candidate_id: str,
    *,
    reason: Optional[str],
    account_generation: int,
) -> CandidateResolutionReceipt:
    return candidates_db.resolve_candidate_without_mutation(
        uid,
        candidate_id,
        status=CandidateStatus.expired,
        reason=reason,
        account_generation=account_generation,
    )


__all__ = [
    'WorkstreamCandidateResolver',
    'accept_candidate',
    'clear_workstream_candidate_resolver',
    'create_candidate',
    'dispatch_task_integration_blocking',
    'drain_candidate_integrations',
    'expire_candidate',
    'register_workstream_candidate_resolver',
    'reject_candidate',
]
