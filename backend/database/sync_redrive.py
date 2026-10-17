"""Durable custody for accepted work whose Redis execution record expired."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.cloud import firestore
from prometheus_client import Gauge

from database._client import get_firestore_client
from database.sync_ledger import is_valid_completed_sync_content_result, sync_content_reference
from utils.sync.redrive_policy import enabled as enabled, legacy_convergence_enabled as legacy_convergence_enabled

COLLECTION = 'sync_redrive_required'
STATS_COLLECTION = 'sync_redrive_stats'
BACKLOG = Gauge('sync_redrive_required', 'Accepted obligations retained for operator redrive')
DEADLINE = Gauge('sync_redrive_nearest_deadline_timestamp_seconds', 'Earliest source deadline; 0 if empty')
UNKNOWN_DEADLINE = Gauge('sync_redrive_unknown_deadline', 'Obligations without an exact source deadline')


def prepare(transaction: Any, client: Any, uid: str, job_id: str, payload: dict, accepted_at: datetime) -> dict:
    """Read all custody/stat documents before caller starts any writes.

    The stats document counts unresolved handoffs, not process-local events.
    Source deadline is exact only when supplied by custody metadata. Otherwise
    accepted_at is a conservative attention deadline: source creation predates
    acceptance and the one-day lifecycle is not a guaranteed recovery window.
    """
    ref = client.collection(COLLECTION).document(job_id)
    stats_ref = client.collection(STATS_COLLECTION).document('backlog')
    existing = ref.get(transaction=transaction).to_dict() or {}
    stats = stats_ref.get(transaction=transaction).to_dict() or {}
    if existing and (existing.get('uid') != uid or existing.get('payload') != payload):
        raise ValueError('redrive custody identity conflict')
    deadline = payload.get('source_deadline_at')
    exact = isinstance(deadline, datetime) and deadline.tzinfo is not None
    deadline = deadline if isinstance(deadline, datetime) and deadline.tzinfo is not None else accepted_at
    nearest = stats.get('nearest_deadline_at')
    return {
        'ref': ref,
        'stats_ref': stats_ref,
        'existing': existing,
        'row': {
            'uid': uid,
            'job_id': job_id,
            'payload': payload,
            'status': 'redrive_required',
            'accepted_at': accepted_at,
            'marked_at': datetime.now(timezone.utc),
            'source_deadline_at': deadline,
            'deadline_kind': 'exact' if exact else 'attention_unknown_source',
        },
        'stats': {
            'count': int(stats.get('count', 0)) + 1,
            'unknown_deadline_count': int(stats.get('unknown_deadline_count', 0)) + int(not exact),
            'nearest_deadline_at': min(nearest, deadline) if isinstance(nearest, datetime) else deadline,
        },
    }


def retain(transaction: Any, prepared: dict) -> None:
    """Write the handoff atomically with caller's scheduling changes."""
    if not prepared['existing']:
        transaction.set(prepared['ref'], prepared['row'])
        transaction.set(prepared['stats_ref'], prepared['stats'])


def preserve_missing_job(uid: str, job_id: str, payload: dict, *, firestore_client: Any = None) -> str:
    """Under the worker run-lock, retain its exact request before ACK; never delete bytes."""
    client = firestore_client or get_firestore_client()

    @firestore.transactional
    def commit(transaction: Any) -> str:
        content_id = payload.get('content_id')
        if isinstance(content_id, str) and content_id and '/' not in content_id:
            claim = sync_content_reference(client, uid, content_id).get(transaction=transaction).to_dict() or {}
            if claim.get('status') == 'completed' and is_valid_completed_sync_content_result(claim.get('result')):
                return 'completed'
        prepared = prepare(transaction, client, uid, job_id, payload, datetime.now(timezone.utc))
        retain(transaction, prepared)
        return 'redrive_required'

    return commit(client.transaction())


def refresh_metrics(*, firestore_client: Any = None) -> None:
    """Read the durable aggregate on every Scheduler tick; no UID metric labels."""
    client = firestore_client or get_firestore_client()
    stats = client.collection(STATS_COLLECTION).document('backlog').get().to_dict() or {}
    BACKLOG.set(int(stats.get('count', 0)))
    UNKNOWN_DEADLINE.set(int(stats.get('unknown_deadline_count', 0)))
    nearest = stats.get('nearest_deadline_at')
    DEADLINE.set(nearest.timestamp() if isinstance(nearest, datetime) else 0)


def converge_legacy_completion(
    *,
    job_id: str,
    uid: str,
    content_id: str | None,
    run_lock_token: str | None,
    firestore_client: Any = None,
) -> dict | None:
    """Read durable success under a legacy lock before provider execution.

    No ledger epoch is bound. The existing Redis CAS verifies the same legacy
    token when publishing the result. Read errors and lost locks fail closed.
    """
    if not content_id or run_lock_token is None:
        return None
    from database.sync_jobs import fenced_finalize_sync_job_from_durable_ledger

    client = firestore_client or get_firestore_client()
    claim = sync_content_reference(client, uid, content_id).get().to_dict() or {}
    result = claim.get('result')
    if (
        not isinstance(result, dict)
        or claim.get('status') != 'completed'
        or not is_valid_completed_sync_content_result(result)
    ):
        return None
    mutation = fenced_finalize_sync_job_from_durable_ledger(job_id, run_lock_token, result)
    if not mutation.applied:
        raise RuntimeError('legacy completion convergence lost its run lock')
    return mutation.job
