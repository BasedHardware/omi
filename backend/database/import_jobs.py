from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db, get_firestore_client, run_transactional

# ImportJobStatus.cancelled; the database layer does not import the API models.
_CANCELLED = 'cancelled'
# The counters a worker reports: all that a progress-only write may change.
IMPORT_JOB_PROGRESS_FIELDS = frozenset({'processed_files', 'conversations_created', 'conversations_skipped'})

# A Firestore document id is a path segment: a '/' (or a NUL) silently retargets the
# write, so identifiers are length-bounded and rejected instead of passed through.
IDENTIFIER_MAX_LENGTH = 256
DEFAULT_IMPORT_JOBS_LIMIT = 50
MAX_IMPORT_JOBS_LIMIT = 1000


def _clean_identifier(value: Any, field: str) -> str:
    """Return a validated Firestore document id, or raise ``ValueError``.

    ``create_import_job`` used to read ``job_data['id']`` directly, so a missing id
    raised ``KeyError`` and a caller-supplied id reached Firestore unchecked.
    """
    if not isinstance(value, str):
        raise ValueError(f'{field} is required')
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f'{field} is required')
    if len(cleaned) > IDENTIFIER_MAX_LENGTH or any(bad in cleaned for bad in ('/', '\\', '\x00')):
        raise ValueError(f'invalid {field}')
    return cleaned


def _clean_limit(limit: Any, default: int = DEFAULT_IMPORT_JOBS_LIMIT) -> int:
    """Clamp a caller-supplied page size to Firestore-safe bounds (1..1000)."""
    if isinstance(limit, bool) or not isinstance(limit, (int, float, str)):
        return default
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, MAX_IMPORT_JOBS_LIMIT))


def _client(firestore_client: Any = None) -> Any:
    return firestore_client if firestore_client is not None else db


def create_import_job(job_data: Any, *, firestore_client: Any = None) -> str:
    """Create a new import job in Firestore."""
    if not isinstance(job_data, dict):
        raise ValueError('job_data must be a mapping')
    job_id = _clean_identifier(job_data.get('id'), 'job id')
    job_ref = _client(firestore_client).collection('import_jobs').document(job_id)
    job_ref.set({**job_data, 'id': job_id})
    return job_id


def update_import_job(job_id: str, updates: Dict[str, Any], *, firestore_client: Any = None) -> None:
    """Update an existing import job."""
    job_ref = _client(firestore_client).collection('import_jobs').document(_clean_identifier(job_id, 'job id'))
    job_ref.update(updates)


def update_import_job_unless_cancelled(job_id: str, updates: Dict[str, Any], *, firestore_client: Any = None) -> bool:
    """Apply ``updates`` unless the job was cancelled or deleted; whether they were applied.

    The status is read and the update written in one transaction, so a cancel the
    user makes while a worker writes cannot be overwritten by it.
    """
    client = _client(firestore_client)
    job_ref = client.collection('import_jobs').document(_clean_identifier(job_id, 'job id'))

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=transaction)
        current: object = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if not isinstance(current, dict) or current.get('status') == _CANCELLED:
            return False
        transaction.update(job_ref, updates)
        return True

    return bool(run_transactional(client, apply))


def cancel_import_job_if_active(job_id: str, *, firestore_client: Any = None) -> bool:
    """Cancel only a pending or processing job, in the transaction that reads its status."""
    client = firestore_client if firestore_client is not None else get_firestore_client()
    job_ref = client.collection('import_jobs').document(_clean_identifier(job_id, 'job id'))

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=transaction)
        current = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if not current or current.get('status') not in ('pending', 'processing'):
            return False
        transaction.update(job_ref, {'status': _CANCELLED, 'error': 'Cancelled by user'})
        return True

    return bool(run_transactional(client, apply))


def update_import_job_progress(job_id: str, progress: Dict[str, Any], *, firestore_client: Any = None) -> bool:
    """Write progress counters to a job that still exists, whatever its status; whether they were written.

    For a worker that stops on a cancel: it records the counts it reached, while
    ``status`` and every other field stay as the cancel left them. Only
    ``IMPORT_JOB_PROGRESS_FIELDS`` may be written, and a deleted job is not recreated.
    """
    unexpected = set(progress) - IMPORT_JOB_PROGRESS_FIELDS
    if unexpected:
        raise ValueError(f'not import job progress fields: {sorted(unexpected)}')
    client = _client(firestore_client)
    job_ref = client.collection('import_jobs').document(_clean_identifier(job_id, 'job id'))

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        if not getattr(job_ref.get(transaction=transaction), 'exists', False):
            return False
        transaction.update(job_ref, progress)
        return True

    return bool(run_transactional(client, apply))


def get_import_job(job_id: str, *, firestore_client: Any = None) -> Optional[Dict[str, Any]]:
    """Get a single import job by ID."""
    job_ref = _client(firestore_client).collection('import_jobs').document(_clean_identifier(job_id, 'job id'))
    job_doc = job_ref.get()
    if getattr(job_doc, "exists", False):
        raw: object = job_doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_import_jobs(
    uid: str, limit: int = DEFAULT_IMPORT_JOBS_LIMIT, *, firestore_client: Any = None
) -> List[Dict[str, Any]]:
    """Get all import jobs for a user, ordered by created_at descending."""
    clean_uid = _clean_identifier(uid, 'uid')
    bounded_limit = _clean_limit(limit)
    query = (
        _client(firestore_client)
        .collection('import_jobs')
        .where(filter=FieldFilter('uid', '==', clean_uid))
        .order_by('created_at', direction='DESCENDING')
        .limit(bounded_limit)
    )
    jobs: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            jobs.append(cast(Dict[str, Any], raw))
    return jobs


def delete_import_job(job_id: str, *, firestore_client: Any = None) -> None:
    """Delete an import job."""
    job_ref = _client(firestore_client).collection('import_jobs').document(_clean_identifier(job_id, 'job id'))
    job_ref.delete()
