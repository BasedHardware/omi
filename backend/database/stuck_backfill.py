"""Snapshot-fenced, metadata-only historical noise close and restore.

No decoder, content rewrite, deletion, provider or delivery call lives here.
The caller must have an approved private plan for the exact row revision.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client
from database import conversation_finalization_jobs as jobs
from utils.conversations.recovery import TERMINAL_NO_DERIVED_EFFECTS_FIELD

MARKER = 'stuck_noise_close'
POLICY = 'silent_backfill_v1'
_FIELDS = ('status', 'discarded', TERMINAL_NO_DERIVED_EFFECTS_FIELD)


class BackfillConflict(RuntimeError):
    """Closed reason codes only; never include identities or content."""


def revision(snapshot: Any) -> str | None:
    value = getattr(snapshot, 'update_time', None)
    if value is None:
        return None
    return value.rfc3339() if hasattr(value, 'rfc3339') else value.isoformat()


def session_revision(transaction: Any, user: Any, row: dict[str, Any]) -> str | None:
    external = row.get('external_data') or {}
    sid = external.get('recording_session_id') if isinstance(external, dict) else None
    if not sid:
        return None
    if not isinstance(sid, str) or '/' in sid:
        raise BackfillConflict('invalid_session')
    return revision(user.collection('recording_sessions').document(sid).get(transaction=transaction))


def _fences(
    transaction: Any,
    client: Any,
    user: Any,
    uid: str,
    cid: str,
    row: dict[str, Any],
    cutoff: datetime,
    expected_session_revision: str | None,
    now: datetime,
) -> None:
    if row.get('record_lane_owner'):
        raise BackfillConflict('refused_record_owner')
    reason = jobs.recovery_admission_refusal(uid, row, cutoff)
    if reason and reason != 'no_content':
        raise BackfillConflict('refused_' + reason)
    if session_revision(transaction, user, row) != expected_session_revision:
        raise BackfillConflict('session_changed')
    lease_expiry = jobs.recording_session_lease_expiry(
        transaction, user.collection('recording_sessions'), uid, cid, row, now
    )
    if lease_expiry is not None and lease_expiry > now:
        raise BackfillConflict('active_session')
    # An orphan deterministic generation must not be hidden by noise close.
    if jobs.has_finalization_job_for_revision(
        transaction,
        client.collection(jobs.FINALIZATION_JOBS_COLLECTION),
        uid,
        cid,
        int(row.get('finalization_revision') or 0) + 1,
    ):
        raise BackfillConflict('job_exists')
    if not jobs.backfill_owner_available(transaction, user, client.collection(jobs.FINALIZATION_JOBS_COLLECTION)):
        raise BackfillConflict('owner_inflight')
    privacy = user.get(transaction=transaction).to_dict() or {}
    if privacy.get('data_protection_level', 'enhanced') not in {'standard', 'enhanced'}:
        raise BackfillConflict('privacy')


def _close_txn(
    transaction: Any,
    client: Any,
    uid: str,
    cid: str,
    expected_revision: str,
    cutoff: datetime,
    expected_session_revision: str | None,
    run_id: str,
    now: datetime,
) -> None:
    user = client.collection('users').document(uid)
    ref = user.collection('conversations').document(cid)
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists or revision(snapshot) != expected_revision:
        raise BackfillConflict('revision_changed')
    row = snapshot.to_dict() or {}
    if row.get(MARKER):
        raise BackfillConflict('already_closed')
    _fences(transaction, client, user, uid, cid, row, cutoff, expected_session_revision, now)
    prior = {key: {'present': key in row, 'value': row.get(key)} for key in _FIELDS}
    transaction.update(
        ref,
        {
            'status': 'completed',
            'discarded': True,
            TERMINAL_NO_DERIVED_EFFECTS_FIELD: True,
            MARKER: {
                'version': 1,
                'policy': POLICY,
                'run_id': run_id,
                'closed_at': now,
                'prior': prior,
                'session_revision': expected_session_revision,
            },
        },
    )


def close_noise(
    uid: str,
    cid: str,
    *,
    expected_revision: str,
    cutoff: datetime,
    expected_session_revision: str | None,
    run_id: str,
    firestore_client: Any = None,
) -> str:
    if not run_id or cutoff.tzinfo is None or cutoff > datetime.now(timezone.utc):
        raise BackfillConflict('unbound_plan')
    client = firestore_client or get_firestore_client()
    transaction = client.transaction()
    firestore.transactional(_close_txn)(
        transaction,
        client,
        uid,
        cid,
        expected_revision,
        cutoff,
        expected_session_revision,
        run_id,
        datetime.now(timezone.utc),
    )
    # Bind restore to our commit, never a later read that might observe someone else's write.
    committed_revision = revision(transaction.write_results[0])
    if committed_revision is None:
        raise BackfillConflict('commit_revision_unavailable')
    return committed_revision


def _restore_txn(
    transaction: Any, client: Any, uid: str, cid: str, expected_closed_revision: str, run_id: str, now: datetime
) -> None:
    user = client.collection('users').document(uid)
    ref = user.collection('conversations').document(cid)
    snapshot = ref.get(transaction=transaction)
    if not snapshot.exists or revision(snapshot) != expected_closed_revision:
        raise BackfillConflict('revision_changed')
    row = snapshot.to_dict() or {}
    marker = row.get(MARKER) or {}
    if (
        marker.get('version') != 1
        or marker.get('run_id') != run_id
        or marker.get('policy') != POLICY
        or row.get('status') != 'completed'
        or row.get('discarded') is not True
        or row.get(TERMINAL_NO_DERIVED_EFFECTS_FIELD) is not True
    ):
        raise BackfillConflict('not_matching_close')
    prior = marker.get('prior') or {}
    if set(prior) != set(_FIELDS):
        raise BackfillConflict('invalid_snapshot')
    restored = dict(row)
    for key, saved in prior.items():
        if saved['present']:
            restored[key] = saved['value']
        else:
            restored.pop(key, None)
    # Re-check jobs, privacy and leases even when the closed row itself is unchanged.
    _fences(transaction, client, user, uid, cid, restored, now, marker.get('session_revision'), now)
    transaction.update(
        ref,
        {
            **{key: saved['value'] if saved['present'] else firestore.DELETE_FIELD for key, saved in prior.items()},
            MARKER: firestore.DELETE_FIELD,
        },
    )


def restore_noise(
    uid: str, cid: str, *, expected_closed_revision: str, run_id: str, firestore_client: Any = None
) -> None:
    client = firestore_client or get_firestore_client()
    firestore.transactional(_restore_txn)(
        client.transaction(), client, uid, cid, expected_closed_revision, run_id, datetime.now(timezone.utc)
    )


def _reserve_txn(transaction: Any, ref: Any, digest: str, modeled_usd: float, now: datetime) -> float:
    if not math.isfinite(modeled_usd) or modeled_usd < 0:
        raise BackfillConflict('unsafe_modeled_cost')
    snapshot = ref.get(transaction=transaction)
    row = snapshot.to_dict() or {}
    if row.get('enabled') is not True or row.get('approved_plan_sha256') != digest:
        raise BackfillConflict('run_disabled_or_plan_changed')
    if row.get('verified_delivery_policy') != POLICY or not row.get('verified_release_sha'):
        raise BackfillConflict('serving_policy_not_verified')
    if not row.get('silent_canary_evidence_ref') or not row.get('queue_consumers_evidence_ref'):
        raise BackfillConflict('serving_silence_evidence_required')
    cap = row.get('admissions_per_minute')
    if not isinstance(cap, (int, float)) or not 0 < cap <= 1000:
        raise BackfillConflict('unsafe_rate')
    admitted = int(row.get('admitted', 0))
    if admitted >= int(row.get('max_admissions', 0)):
        raise BackfillConflict('admission_budget')
    spent = float(row.get('modeled_reserved_usd', 0))
    budget = float(row.get('max_modeled_usd', 0))
    if not math.isfinite(spent) or not math.isfinite(budget) or min(spent, budget) < 0:
        raise BackfillConflict('unsafe_budget')
    if spent + modeled_usd > budget:
        raise BackfillConflict('modeled_budget')
    next_at = row.get('next_admission_at')
    if isinstance(next_at, datetime) and next_at > now:
        return (next_at - now).total_seconds()
    transaction.update(
        ref,
        {
            'admitted': admitted + 1,
            'modeled_reserved_usd': spent + modeled_usd,
            'next_admission_at': now + timedelta(seconds=60 / cap),
        },
    )
    return 0.0


def reserve_admission(run_id: str, digest: str, modeled_usd: float, *, firestore_client: Any = None) -> float:
    """Read the durable kill switch and reserve one globally paced admission.

    Returns a delay without writing when another admission owns the interval.
    Crashes consume the reserved slot/budget; they cannot exceed it.
    """
    client = firestore_client or get_firestore_client()
    ref = client.collection('stuck_backfill_runs').document(run_id)
    return firestore.transactional(_reserve_txn)(
        client.transaction(), ref, digest, modeled_usd, datetime.now(timezone.utc)
    )
