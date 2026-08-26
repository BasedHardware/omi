"""Historical staged-task projection helpers.

The released migration report remains available for old clients, but universal
task authority never performs account-wide staged-task materialization. A row
is converted only when a user explicitly mutates that row through the released
staged-task routes.
"""

from datetime import datetime, timezone
from typing import Any, Optional

import database.staged_tasks as staged_tasks_db
from models.action_item import EvidenceKind, EvidenceRef, EvidenceScope, TaskCreatePayload, TaskOwner, TaskPriority
from models.candidate import (
    CandidateAction,
    CandidateCompatibilityMetadata,
    CandidateCreate,
    CandidateMigrationReport,
    CandidateSubjectKind,
)
from models.task_intelligence import TaskWorkflowControl


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
            'compatibility': (
                CandidateCompatibilityMetadata(
                    metadata=row.get('metadata'),
                    category=row.get('category'),
                    relevance_score=row.get('relevance_score'),
                )
                if any(row.get(field) is not None for field in ('metadata', 'category', 'relevance_score'))
                else None
            ),
        }
    )


def migrate_staged_tasks(
    uid: str,
    control: TaskWorkflowControl,
    *,
    after_id: Optional[str] = None,
    limit: int = 500,
) -> CandidateMigrationReport:
    """Return a bounded compatibility inventory without creating Candidates."""

    rows = sorted(staged_tasks_db.get_all_staged_tasks_for_migration(uid), key=lambda row: row.get('id', ''))
    if after_id:
        rows = [row for row in rows if row.get('id', '') > after_id]
    rows = rows[:limit]
    checkpoint = str(rows[-1].get('id')) if rows else after_id
    return CandidateMigrationReport(
        workflow_mode=control.workflow_mode,
        account_generation=control.account_generation,
        dry_run=True,
        scanned=len(rows),
        created=0,
        reconciled=0,
        unchanged=len(rows),
        failed=0,
        failure_ids=[],
        checkpoint=checkpoint,
    )


__all__ = ['migrate_staged_tasks', 'proposal_from_legacy_staged']
