"""Re-mark stale queued/leased finalization jobs that lost their due marker.

A job without ``reconcile_after_at`` is never selected by replay, so it can sit
forever. This bounded sweep gives such jobs a due marker; the normal replay
ladder then dispatches, claims or fences them. Lives beside the jobs ledger so the
ledger module stays within its line budget.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter
from prometheus_client import Counter

from database._client import get_firestore_client
from database.conversation_finalization_jobs import (
    FINALIZATION_JOBS_COLLECTION,
    FINALIZATION_OLDEST_NONTERMINAL_QUERY,
    STALE_PROCESSING_SWEEP_STATE_COLLECTION,
)
from utils.observability.reasons import DueMarkerSweepOutcome, ReasonFamily, reason_label

LISTEN_FINALIZATION_DUE_MARKER_SWEEP_TOTAL = Counter(
    'listen_finalization_due_marker_sweep_total',
    'Queued or leased finalization jobs older than 24h without a due marker, by sweep outcome',
    ['outcome'],
)


def count_sweep_outcome(outcome: object, count: int = 1) -> None:
    """Add ``count`` to the sweep counter under a closed outcome label."""
    LISTEN_FINALIZATION_DUE_MARKER_SWEEP_TOTAL.labels(
        outcome=reason_label(ReasonFamily.DUE_MARKER_SWEEP, outcome, DueMarkerSweepOutcome)
    ).inc(count)


for _outcome in DueMarkerSweepOutcome:
    count_sweep_outcome(_outcome, 0)


def _advance_cursor_txn(
    transaction: Any, doc_ref: Any, expected_generation: int, path: str | None, now: datetime
) -> bool:
    """CAS on the persisted generation, like the stale-processing sweep cursor."""
    snapshot = doc_ref.get(transaction=transaction)
    generation = int((snapshot.to_dict() or {}).get('generation', 0)) if getattr(snapshot, 'exists', False) else 0
    if generation != expected_generation:
        return False
    transaction.set(doc_ref, {'resume_after_path': path, 'generation': generation + 1, 'updated_at': now})
    return True


FINALIZATION_DUE_MARKER_STALE_AFTER = timedelta(hours=24)
FINALIZATION_DUE_MARKER_PAGE_SIZE = 50
# Quiet checks and merge jobs keep their own admission and scheduling owners.
_DUE_MARKER_SWEEP_EXCLUDED_KINDS = frozenset({'listen_quiet_check', 'conversation_merge'})


def _restore_missing_due_marker_txn(transaction: Any, job_ref: Any, cutoff: datetime, now: datetime) -> str:
    snapshot = job_ref.get(transaction=transaction)
    if not getattr(snapshot, 'exists', False):
        return 'skipped'
    job = snapshot.to_dict() or {}
    if job.get('status') not in ('queued', 'leased') or job.get('kind') in _DUE_MARKER_SWEEP_EXCLUDED_KINDS:
        return 'skipped'
    if job.get('requires_byok'):
        # BYOK jobs have their own recovery scan; touching updated_at would keep them looking active.
        return 'skipped'
    if isinstance(job.get('reconcile_after_at'), datetime):
        return 'skipped'
    created_at = job.get('created_at')
    if not isinstance(created_at, datetime) or created_at > cutoff:
        return 'skipped'
    # Due now: the normal replay ladder decides whether to dispatch, claim, or fence.
    transaction.update(job_ref, {'reconcile_after_at': now, 'updated_at': now})
    return 'remarked'


def remark_missing_due_markers(
    *,
    now: datetime | None = None,
    stale_after: timedelta = FINALIZATION_DUE_MARKER_STALE_AFTER,
    limit: int = FINALIZATION_DUE_MARKER_PAGE_SIZE,
    firestore_client: Any = None,
) -> dict[str, int]:
    """Re-mark queued/leased jobs older than ``stale_after`` that have no due marker.

    A bounded page per status, rotated through a persisted cursor over the
    existing status + created_at index, so no new composite index is needed.
    Each row is re-read and re-checked inside its own transaction.
    """
    client = firestore_client if firestore_client is not None else get_firestore_client()
    current = now or datetime.now(timezone.utc)
    cutoff = current - stale_after
    page_size = max(1, min(int(limit), 200))
    collection = client.collection(FINALIZATION_JOBS_COLLECTION)
    result = {'remarked': 0, 'skipped': 0, 'error': 0}
    for status in ('queued', 'leased'):
        state_ref = client.collection(STALE_PROCESSING_SWEEP_STATE_COLLECTION).document(f'due_marker_{status}')
        state = state_ref.get().to_dict() or {}
        query = (
            FINALIZATION_OLDEST_NONTERMINAL_QUERY.build(
                collection, dict.fromkeys(('status',), status), field_filter_factory=FieldFilter
            )
            .where('created_at', '<=', cutoff)
            .order_by('created_at')
        )
        path = state.get('resume_after_path')
        if isinstance(path, str) and path.startswith(FINALIZATION_JOBS_COLLECTION + '/'):
            cursor = client.document(path).get()
            if cursor.exists and isinstance((cursor.to_dict() or {}).get('created_at'), datetime):
                query = query.start_after(cursor)
        snapshots = list(query.limit(page_size).stream())
        for snapshot in snapshots:
            if isinstance((snapshot.to_dict() or {}).get('reconcile_after_at'), datetime):
                # Advisory pre-read: healthy rows never open a transaction. The
                # transaction below rereads the marker before any write.
                result['skipped'] += 1
                continue
            try:
                outcome = firestore.transactional(_restore_missing_due_marker_txn)(
                    client.transaction(), snapshot.reference, cutoff, current
                )
            except Exception:
                outcome = 'error'
            result[outcome] += 1
        next_path = snapshots[-1].reference.path if len(snapshots) == page_size else None
        firestore.transactional(_advance_cursor_txn)(
            client.transaction(), state_ref, int(state.get('generation', 0)), next_path, datetime.now(timezone.utc)
        )
    return result
