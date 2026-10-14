from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db, get_firestore_client, run_transactional

# ImportJobStatus.cancelled; the database layer does not import the API models.
_CANCELLED = 'cancelled'
# Job ids are generated server-side; a slash or traversal sequence in a
# caller-supplied id would otherwise be interpreted as a subcollection path by
# document(job_id). Reject anything that is not a plain doc id.
_JOB_ID_SAFE_CHARS = frozenset('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-')
_MAX_IMPORT_JOBS_LIMIT = 200


def _validate_job_id(job_id: str) -> str:
    """Return *job_id* if it is a safe Firestore document id, else raise ValueError.

    Caller-supplied ids flow into ``document(job_id)``; a slash or traversal
    sequence there is interpreted as a subcollection path, letting a malformed id
    read or delete an unrelated document. Job ids are server-generated, so any id
    outside the safe charset is rejected outright.
    """
    if (
        not isinstance(job_id, str)
        or not job_id
        or len(job_id) > 128
        or not set(job_id) <= _JOB_ID_SAFE_CHARS
    ):
        raise ValueError(f'invalid import job id {job_id!r}')
    return job_id
# The counters a worker reports: all that a progress-only write may change.
IMPORT_JOB_PROGRESS_FIELDS = frozenset({'processed_files', 'conversations_created', 'conversations_skipped'})


def create_import_job(job_data: Dict[str, Any]) -> str:
    """Create a new import job in Firestore."""
    job_id = job_data['id']
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.set(job_data)
    return job_id


def update_import_job(job_id: str, updates: Dict[str, Any]) -> None:
    """Update an existing import job."""
    job_ref = db.collection('import_jobs').document(_validate_job_id(job_id))
    job_ref.update(updates)


def update_import_job_unless_cancelled(job_id: str, updates: Dict[str, Any]) -> bool:
    """Apply ``updates`` unless the job was cancelled or deleted; whether they were applied.

    The status is read and the update written in one transaction, so a cancel the
    user makes while a worker writes cannot be overwritten by it.
    """
    job_ref = db.collection('import_jobs').document(_validate_job_id(job_id))

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=transaction)
        current: object = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if not isinstance(current, dict) or current.get('status') == _CANCELLED:
            return False
        transaction.update(job_ref, updates)
        return True

    return bool(run_transactional(db, apply))


def cancel_import_job_if_active(job_id: str, *, firestore_client: Any = None) -> bool:
    """Cancel only a pending or processing job, in the transaction that reads its status."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    job_ref = client.collection('import_jobs').document(_validate_job_id(job_id))

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=transaction)
        current = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if not current or current.get('status') not in ('pending', 'processing'):
            return False
        transaction.update(job_ref, {'status': _CANCELLED, 'error': 'Cancelled by user'})
        return True

    return bool(run_transactional(client, apply))


def update_import_job_progress(job_id: str, progress: Dict[str, Any]) -> bool:
    """Write progress counters to a job that still exists, whatever its status; whether they were written.

    For a worker that stops on a cancel: it records the counts it reached, while
    ``status`` and every other field stay as the cancel left them. Only
    ``IMPORT_JOB_PROGRESS_FIELDS`` may be written, and a deleted job is not recreated.
    """
    unexpected = set(progress) - IMPORT_JOB_PROGRESS_FIELDS
    if unexpected:
        raise ValueError(f'not import job progress fields: {sorted(unexpected)}')
    job_ref = db.collection('import_jobs').document(_validate_job_id(job_id))

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        if not getattr(job_ref.get(transaction=transaction), 'exists', False):
            return False
        transaction.update(job_ref, progress)
        return True

    return bool(run_transactional(db, apply))


def get_import_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a single import job by ID."""
    job_ref = db.collection('import_jobs').document(_validate_job_id(job_id))
    job_doc = job_ref.get()
    if getattr(job_doc, "exists", False):
        raw: object = job_doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_import_jobs(uid: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all import jobs for a user, ordered by created_at descending."""
    if not uid or not isinstance(uid, str):
        return []
    # Clamp the page size: an unbounded or negative limit is meaningless and a
    # huge one would stream the whole collection.
    limit = max(1, min(int(limit) if isinstance(limit, (int, float)) else 50, _MAX_IMPORT_JOBS_LIMIT))
    query = (
        db.collection('import_jobs')
        .where(filter=FieldFilter('uid', '==', uid))
        .order_by('created_at', direction='DESCENDING')
        .limit(limit)
    )
    jobs: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            jobs.append(cast(Dict[str, Any], raw))
    return jobs


def delete_import_job(job_id: str) -> None:
    """Delete an import job."""
    job_ref = db.collection('import_jobs').document(_validate_job_id(job_id))
    job_ref.delete()
