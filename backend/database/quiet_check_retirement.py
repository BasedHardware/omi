"""Quiet-check identity and retirement, independent of finalization admission."""

from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from google.cloud import firestore

from database._client import get_firestore_client


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
