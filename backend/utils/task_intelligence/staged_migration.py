"""Mode-aware, resumable staged-task to Candidate reconciliation."""

from datetime import datetime, timezone
from typing import Any, Optional

import database.candidates as candidates_db
import database.staged_tasks as staged_tasks_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope, TaskCreatePayload, TaskOwner, TaskPriority
from models.candidate import (
    CandidateAction,
    CandidateCreate,
    CandidateMigrationReport,
    CandidateStatus,
    CandidateSubjectKind,
)
from models.task_intelligence import TaskWorkflowControl, TaskWorkflowMode
from utils.task_intelligence import candidate_service


def _aware(value: Any) -> Any:
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def proposal_from_legacy_staged(row: dict[str, Any]) -> CandidateCreate:
    priority_value = row.get('priority')
    priority = TaskPriority(priority_value) if priority_value in {item.value for item in TaskPriority} else None
    payload = TaskCreatePayload(
        description=row.get('description', ''),
        owner=TaskOwner.unknown,
        due_at=_aware(row.get('due_at')),
        priority=priority,
    )
    return CandidateCreate.model_validate(
        {
            'subject_kind': CandidateSubjectKind.task,
            'proposed_action': CandidateAction.create,
            'task_change': payload,
            'capture_confidence': 0.5,
            'ownership_confidence': 0.5,
            'evidence_refs': [
                EvidenceRef(
                    kind=EvidenceKind.external,
                    id=f'legacy-staged-{row["id"]}',
                    scope=EvidenceScope.canonical,
                )
            ],
            'source_surface': 'legacy_staged',
        }
    )


def _legacy_terminal_state(row: dict[str, Any]) -> tuple[Optional[CandidateStatus], Optional[str], Optional[str]]:
    if not row.get('completed'):
        return None, None, None
    promoted_to = row.get('promoted_to')
    if isinstance(promoted_to, str) and promoted_to:
        return CandidateStatus.accepted, promoted_to, row.get('promotion_skipped') or 'legacy_promoted'
    if row.get('promotion_skipped'):
        return CandidateStatus.rejected, None, str(row['promotion_skipped'])[:64]
    return CandidateStatus.expired, None, 'legacy_closed'


def migrate_staged_tasks(
    uid: str,
    control: TaskWorkflowControl,
    *,
    after_id: Optional[str] = None,
    limit: int = 500,
) -> CandidateMigrationReport:
    rows = sorted(staged_tasks_db.get_all_staged_tasks_for_migration(uid), key=lambda row: row.get('id', ''))
    if after_id:
        rows = [row for row in rows if row.get('id', '') > after_id]
    rows = rows[:limit]
    dry_run = control.workflow_mode in {TaskWorkflowMode.off, TaskWorkflowMode.shadow}
    created = reconciled = unchanged = failed = 0
    failure_ids: list[str] = []

    for row in rows:
        row_id = str(row.get('id', ''))
        if dry_run:
            unchanged += 1
            continue
        try:
            existing = candidates_db.get_candidate(
                uid,
                candidates_db.candidate_id_for_idempotency(uid, control.account_generation, f'legacy-staged:{row_id}'),
            )
            candidate = candidate_service.create_candidate(
                uid,
                proposal_from_legacy_staged(row),
                idempotency_key=f'legacy-staged:{row_id}',
                account_generation=control.account_generation,
            )
            if existing is None:
                created += 1
            else:
                unchanged += 1
            terminal_status, result_task_id, reason = _legacy_terminal_state(row)
            if terminal_status is not None and candidate.status == CandidateStatus.pending:
                candidates_db.reconcile_migrated_candidate(
                    uid,
                    candidate.candidate_id,
                    status=terminal_status,
                    account_generation=control.account_generation,
                    result_task_id=result_task_id,
                    reason=reason,
                    resolved_at=_aware(row.get('promoted_at') or row.get('updated_at')),
                )
                reconciled += 1
        except (ValueError, candidates_db.CandidateStoreError):
            failed += 1
            if row_id:
                failure_ids.append(row_id)

    checkpoint = str(rows[-1].get('id')) if rows else after_id
    return CandidateMigrationReport(
        workflow_mode=control.workflow_mode,
        account_generation=control.account_generation,
        dry_run=dry_run,
        scanned=len(rows),
        created=created,
        reconciled=reconciled,
        unchanged=unchanged,
        failed=failed,
        failure_ids=failure_ids,
        checkpoint=checkpoint,
    )


__all__ = ['migrate_staged_tasks', 'proposal_from_legacy_staged']
