"""Durable quiet checks, separate from processing ownership in the finalization outbox.

A check never changes conversation status or finalization revision. The normal
SERVER_RECOVERY transaction is the only processing admission boundary.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from google.cloud import firestore
from prometheus_client import Counter

from database.quiet_check_retirement import (
    quiet_check_id,
    stop_quiet_check as stop_quiet_check,
    stop_quiet_check_for_conversation,
)
from database._client import get_firestore_client
from database import conversation_finalization_jobs as jobs_db
from models.conversation_continuity import continuation_timeout
from config.refactor_modes import serving_for
from utils.conversations.lifecycle_clocks import speech_clock

QUIET_CHECK_KIND = 'listen_quiet_check'
QUIET_CHECK_STATUS = 'waiting_quiet'
QUIET_SOURCES = frozenset({'omi', 'phone'})

ARM_OUTCOMES = Counter('listen_quiet_check_arm_total', 'Quiet-check arm attempts by durable outcome', ['outcome'])
ARM_METRICS = {
    'created': ARM_OUTCOMES.labels(outcome='created'),
    'rearmed': ARM_OUTCOMES.labels(outcome='rearmed'),
    'reused': ARM_OUTCOMES.labels(outcome='reused'),
    'refused': ARM_OUTCOMES.labels(outcome='refused'),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _client(firestore_client: Any) -> Any:
    return firestore_client if firestore_client is not None else get_firestore_client()


def quiet_timeout(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return max(1.0, min(float(value), 14400.0))
    return 120.0


def quiet_deadline(conversation: dict[str, Any], timeout: Any = 120, *, uid: str = '') -> datetime | None:
    finish = speech_clock(uid, conversation)
    if not isinstance(finish, datetime):
        return None
    finish = finish if finish.tzinfo else finish.replace(tzinfo=timezone.utc)
    return finish + timedelta(seconds=continuation_timeout(conversation, quiet_timeout(timeout)))


def arm_quiet_check(
    uid: str, conversation_id: str, timeout: float, *, requires_byok: bool = False, firestore_client: Any = None
) -> dict[str, Any] | None:
    """Create one check per conversation, or move its wake earlier on disconnect.

    Arming at session setup also covers a process killed before teardown. An
    empty row can own a check while its recording lease is live; only content
    can subsequently pass SERVER_RECOVERY admission.
    """
    client = _client(firestore_client)
    row_ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
    job_id = quiet_check_id(uid, conversation_id)
    job_ref = client.collection(jobs_db.FINALIZATION_JOBS_COLLECTION).document(job_id)

    @firestore.transactional
    def arm(transaction: Any) -> dict[str, Any] | None:
        row = row_ref.get(transaction=transaction).to_dict() or {}
        job = job_ref.get(transaction=transaction).to_dict() or {}
        if row.get('source') not in QUIET_SOURCES or row.get('status') != 'in_progress':
            return None
        if any(
            row.get(key) for key in ('deleted', 'discarded', 'sync_merged_into', 'is_locked', 'finalization_job_id')
        ):
            return None
        deadline = quiet_deadline(row, timeout, uid=uid)
        if deadline is None:
            return None
        requires_keys = bool(requires_byok or row.get('listen_finalization_requires_byok'))
        now = _now()
        due = max(now, deadline)
        existing_due = job.get('due_at')
        if job.get('status') == QUIET_CHECK_STATUS and isinstance(existing_due, datetime) and existing_due <= due:
            if (
                job.get('quiet_timeout_seconds') != quiet_timeout(timeout)
                or row.get('listen_finalization_requires_byok') != requires_keys
            ):
                transaction.update(
                    row_ref,
                    {
                        'listen_quiet_timeout_seconds': quiet_timeout(timeout),
                        'listen_finalization_requires_byok': requires_keys,
                    },
                )
                transaction.update(job_ref, {'quiet_timeout_seconds': quiet_timeout(timeout)})
            return job | {'job_id': job_id, 'quiet_timeout_seconds': quiet_timeout(timeout), '_arm_outcome': 'reused'}
        generation = int(job.get('dispatch_generation') or 0) + 1
        updated = {
            'kind': QUIET_CHECK_KIND,
            'status': QUIET_CHECK_STATUS,
            'uid': uid,
            'conversation_id': conversation_id,
            'quiet_timeout_seconds': quiet_timeout(timeout),
            'dispatch_generation': generation,
            'due_at': due,
            'reconcile_after_at': due,
            'created_at': job.get('created_at') or now,
            'updated_at': now,
        }
        transaction.update(
            row_ref,
            {
                'listen_quiet_timeout_seconds': quiet_timeout(timeout),
                'listen_finalization_requires_byok': requires_keys,
            },
        )
        transaction.set(job_ref, updated)
        return updated | {'job_id': job_id, '_arm_outcome': 'rearmed' if job else 'created'}

    result = arm(client.transaction())
    outcome = result.pop('_arm_outcome') if result is not None else 'refused'
    ARM_METRICS[outcome].inc()
    if result is None:
        stop_quiet_check_for_conversation(uid, conversation_id, firestore_client=client)
    return result


def evaluate_quiet_check(job_id: str, generation: int, *, firestore_client: Any = None) -> dict[str, Any]:
    try:
        result = _evaluate_quiet_check(job_id, generation, firestore_client=firestore_client)
    except Exception:
        ensure_quiet_check_progress(job_id, firestore_client=firestore_client)
        raise
    if result['status'] == 'stale':
        ensure_quiet_check_progress(job_id, firestore_client=firestore_client)
    return result


def _evaluate_quiet_check(job_id: str, generation: int, *, firestore_client: Any = None) -> dict[str, Any]:
    """Re-read row + lease transactionally; reserve the next wake before returning.

    A reconnect/content update only defers this obligation. The fresh lease is
    read again in SERVER_RECOVERY admission, closing the evaluate/admit race.
    Duplicate workers may observe ready; they cannot admit a second generation.
    """
    client = _client(firestore_client)
    job_ref = client.collection(jobs_db.FINALIZATION_JOBS_COLLECTION).document(job_id)

    @firestore.transactional
    def evaluate(transaction: Any) -> dict[str, Any]:
        job = job_ref.get(transaction=transaction).to_dict() or {}
        if job.get('kind') != QUIET_CHECK_KIND or job.get('status') != QUIET_CHECK_STATUS:
            return {'status': 'stale'}
        if isinstance(job.get('dispatch_generation'), bool) or job.get('dispatch_generation') != generation:
            return {'status': 'stale'}
        now = _now()
        row_ref = (
            client.collection('users').document(job['uid']).collection('conversations').document(job['conversation_id'])
        )
        row = row_ref.get(transaction=transaction).to_dict() or {}
        if not row:
            transaction.update(
                job_ref, {'status': 'quiet_done', 'reconcile_after_at': firestore.DELETE_FIELD, 'updated_at': now}
            )
            return {'status': 'done', 'reason': 'missing_conversation'}
        deadline = quiet_deadline(row, job.get('quiet_timeout_seconds'), uid=job['uid'])
        lease_expiry = jobs_db.recording_session_lease_expiry(
            transaction,
            row_ref.parent.parent.collection('recording_sessions'),
            job['uid'],
            job['conversation_id'],
            row,
            now,
        )
        active = lease_expiry is not None and lease_expiry > now
        refusal = jobs_db.recovery_admission_refusal(job['uid'], row, now)
        # Empty live generations must keep their obligation until their owner
        # leaves, since content may arrive after the first scheduled wake.
        empty = refusal == 'no_content' and serving_for('LIFECYCLE_V2_MODE', job['uid'])
        if refusal is not None and not (refusal == 'no_content' and (active or empty)):
            transaction.update(
                job_ref, {'status': 'quiet_done', 'reconcile_after_at': firestore.DELETE_FIELD, 'updated_at': _now()}
            )
            return {'status': 'done', 'reason': refusal}
        if deadline is None:
            transaction.update(
                job_ref, {'status': 'quiet_done', 'reconcile_after_at': firestore.DELETE_FIELD, 'updated_at': _now()}
            )
            return {'status': 'done'}
        ready = lease_expiry is not None and not active and deadline <= now
        # Short, bounded retry for a lost admission; live sessions get a minute
        # probe so an expired lease becomes due without waiting for a reconnect.
        due = max(now + timedelta(seconds=60), deadline, lease_expiry if lease_expiry is not None and active else now)
        updated = job | {
            'dispatch_generation': generation + 1,
            'due_at': due,
            'reconcile_after_at': due,
            'updated_at': now,
        }
        transaction.set(job_ref, updated)
        return updated | {
            'job_id': job_id,
            'status': ('empty_ready' if empty else 'ready') if ready else 'deferred',
            'recording_session_id': (row.get('external_data') or {}).get('recording_session_id'),
            'recovery_cutoff': now
            - timedelta(seconds=continuation_timeout(row, quiet_timeout(job.get('quiet_timeout_seconds')))),
        }

    return evaluate(client.transaction())


def ensure_quiet_check_progress(job_id: str, *, firestore_client: Any = None) -> bool:
    """Repair an overdue obligation after any return or exception, without losing work.

    Fresh successor wakes are untouched. A stale delivery must never retire a
    newer waiting generation; instead reserve a bounded successor for replay.
    Missing or malformed references cannot be evaluated and are retired explicitly.
    """
    client = _client(firestore_client)
    ref = client.collection(jobs_db.FINALIZATION_JOBS_COLLECTION).document(job_id)

    @firestore.transactional
    def repair(transaction: Any) -> bool:
        job = ref.get(transaction=transaction).to_dict() or {}
        if job.get('kind') != QUIET_CHECK_KIND:
            return False
        now = _now()
        reconcile_at = job.get('reconcile_after_at')
        if job.get('status') != QUIET_CHECK_STATUS and 'reconcile_after_at' not in job:
            return False  # Already retired.
        if job.get('status') == QUIET_CHECK_STATUS and isinstance(reconcile_at, datetime) and reconcile_at > now:
            return False  # A fresh successor is already reserved.
        updates: dict[str, Any] = {'updated_at': now}
        generation = job.get('dispatch_generation')
        parsed_generation = 0
        valid_generation = False
        if isinstance(generation, (int, float, str)) and not isinstance(generation, bool):
            try:
                parsed_generation = int(generation)
                valid_generation = parsed_generation >= 1 and str(generation) in {
                    str(parsed_generation),
                    str(float(parsed_generation)),
                }
            except (TypeError, ValueError, OverflowError):
                pass
        if (
            job.get('status') != QUIET_CHECK_STATUS
            or not valid_generation
            or not all(isinstance(job.get(key), str) and job[key] for key in ('uid', 'conversation_id'))
        ):
            updates.update(status='quiet_done', reconcile_after_at=firestore.DELETE_FIELD)
            updates['last_failure_code'] = 'invalid_or_terminal_quiet_check'
        else:
            due = now + timedelta(seconds=60)
            updates.update(dispatch_generation=parsed_generation + 1, due_at=due, reconcile_after_at=due)
        transaction.update(ref, updates)
        return True

    return repair(client.transaction())
