"""Quiet-check identity and retirement, independent of finalization admission."""

import logging
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client
from utils.observability.fallback import record_fallback

logger = logging.getLogger(__name__)


def quiet_check_id(uid: str, conversation_id: str) -> str:
    return 'quiet-' + sha256(f'{uid}\0{conversation_id}'.encode()).hexdigest()


def _retire(transaction: Any, ref: Any, *, failure_code: str | None = None) -> None:
    updates: dict[str, Any] = {
        'status': 'quiet_done',
        'reconcile_after_at': firestore.DELETE_FIELD,
        'updated_at': datetime.now(timezone.utc),
    }
    if failure_code is not None:
        updates['last_failure_code'] = failure_code
    transaction.update(ref, updates)


def _record_deferred_retirement(operation: str) -> None:
    try:
        record_fallback(
            component='conversation_finalization',
            from_mode='inline',
            to_mode='durable_queued',
            reason='unavailable',
            outcome='degraded',
            log=logger,
        )
    except Exception:
        # Telemetry is never allowed to change the committed owner result.
        logger.warning('event=quiet_check_retirement outcome=telemetry_failed')
    logger.exception('event=quiet_check_retirement outcome=deferred operation=%s', operation)


def restore_quiet_check_in_transaction(
    transaction: Any, client: Any, uid: str, conversation_id: str, conversation: dict[str, Any]
) -> None:
    """Restore existing custody atomically with a processing-to-live rollback.

    The caller has read the owner and supplies its proposed live state.
    Only a previously owed quiet job is restored; indexed replay picks it up
    immediately and a new generation fences deliveries from before admission.
    """
    if (
        conversation.get('status') != 'in_progress'
        or conversation.get('source') not in {'omi', 'phone'}
        or any(
            conversation.get(key)
            for key in ('deleted', 'discarded', 'is_locked', 'sync_merged_into', 'finalization_job_id')
        )
    ):
        return
    ref = client.collection('conversation_finalization_jobs').document(quiet_check_id(uid, conversation_id))
    job = ref.get(transaction=transaction).to_dict() or {}
    if job.get('kind') != 'listen_quiet_check':
        return
    now = datetime.now(timezone.utc)
    transaction.update(
        ref,
        {
            'status': 'waiting_quiet',
            'dispatch_generation': int(job.get('dispatch_generation') or 0) + 1,
            'due_at': now,
            'reconcile_after_at': now,
            'updated_at': now,
        },
    )


def stop_quiet_check(
    job_id: str, generation: int, *, failure_code: str | None = None, firestore_client: Any = None
) -> None:
    """A delivered worker may retire only its own generation."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    ref = client.collection('conversation_finalization_jobs').document(job_id)

    @firestore.transactional
    def stop(transaction: Any) -> None:
        job = ref.get(transaction=transaction).to_dict() or {}
        if job.get('kind') == 'listen_quiet_check' and job.get('dispatch_generation') == generation:
            _retire(transaction, ref, failure_code=failure_code)

    stop(client.transaction())


def stop_quiet_check_for_conversation(uid: str, conversation_id: str, *, firestore_client: Any = None) -> bool:
    """Retire immediately after a lifecycle commit, fenced against a live reopen.

    Read the latest job and conversation together: an old post-commit cleanup
    must not cancel a successor armed after a concurrent reopen. Missing jobs
    are never created. A missing/merged/hidden/non-live owner owes no quiet wake.
    """
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        ref = client.collection('conversation_finalization_jobs').document(quiet_check_id(uid, conversation_id))
        # Most completed sync rows never owned a quiet check. Avoid a transaction
        # for them; the authoritative reads below still fence every actual retirement.
        if (ref.get().to_dict() or {}).get('kind') != 'listen_quiet_check':
            return False

        @firestore.transactional
        def stop(transaction: Any) -> bool:
            job = ref.get(transaction=transaction).to_dict() or {}
            if job.get('kind') != 'listen_quiet_check':
                return False
            if job.get('status') == 'quiet_done' and 'reconcile_after_at' not in job:
                return False
            row_ref = client.collection('users').document(uid).collection('conversations').document(conversation_id)
            row = row_ref.get(transaction=transaction).to_dict() or {}
            if row.get('status') == 'in_progress' and not any(
                row.get(key) for key in ('deleted', 'discarded', 'sync_merged_into', 'finalization_job_id')
            ):
                return False
            _retire(transaction, ref)
            return True

        return stop(client.transaction())
    except Exception:
        # Cleanup must not invalidate an already-committed owner transition.
        # Keep the durable index for the independent quiet replay backstop.
        _record_deferred_retirement('stop_quiet_check_for_conversation')
        return False


def stop_quiet_checks_for_job(job_id: str, *, firestore_client: Any = None) -> None:
    """Converge quiet debt when a terminal worker knows only its outbox ID."""
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        job = client.collection('conversation_finalization_jobs').document(job_id).get().to_dict() or {}
        uid = job.get('uid')
        if not isinstance(uid, str) or not uid:
            return
        conversation_id = job.get('conversation_id')
        conversation_ids = [conversation_id] if isinstance(conversation_id, str) else []
        if job.get('kind') == 'conversation_merge' and isinstance(job.get('conversation_ids'), list):
            conversation_ids = job['conversation_ids']
        for cid in conversation_ids:
            if isinstance(cid, str) and cid:
                stop_quiet_check_for_conversation(uid, cid, firestore_client=client)
    except Exception:
        # Cleanup must not invalidate an already-committed owner transition.
        # Keep the durable index for the independent quiet replay backstop.
        _record_deferred_retirement('stop_quiet_checks_for_job')


def stop_quiet_checks_for_account(uid: str, *, firestore_client: Any = None, page_size: int = 450) -> None:
    """Retire global quiet jobs after recursive account erasure, in bounded pages.

    The existing UID single-field index suffices. Filter kind locally so normal
    finalization jobs keep their own retention/ownership policy. Latest-owner
    transactions still protect a concurrently reopened conversation.
    """
    try:
        client = firestore_client if firestore_client is not None else get_firestore_client()
        query = (
            client.collection('conversation_finalization_jobs')
            .where('uid', '==', uid)
            .select(['kind', 'conversation_id'])
            .limit(max(1, min(450, page_size)))
        )
        cursor = None
        while True:
            page = list((query.start_after(cursor) if cursor is not None else query).stream())
            if not page:
                return
            for snapshot in page:
                row = snapshot.to_dict() or {}
                cid = row.get('conversation_id')
                if row.get('kind') == 'listen_quiet_check' and isinstance(cid, str) and cid:
                    stop_quiet_check_for_conversation(uid, cid, firestore_client=client)
            cursor = page[-1]
    except Exception:
        # Cleanup must not invalidate an already-committed owner transition.
        # Keep the durable index for the independent quiet replay backstop.
        _record_deferred_retirement('stop_quiet_checks_for_account')
