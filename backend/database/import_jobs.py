import logging
from typing import Any, Dict, List, Optional, cast

from google.api_core.exceptions import NotFound
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db, get_firestore_client, run_transactional

logger = logging.getLogger(__name__)

# ImportJobStatus.cancelled; the database layer does not import the API models.
_CANCELLED = 'cancelled'
# The counters a worker reports: all that a progress-only write may change.
IMPORT_JOB_PROGRESS_FIELDS = frozenset({'processed_files', 'conversations_created', 'conversations_skipped'})


def _sanitize_id(value: object, field_name: str = 'job_id') -> str:
    if not isinstance(value, str):
        raise ValueError(f'{field_name} must be a non-empty string')
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        raise ValueError(f'{field_name} must be a safe document id')
    return cleaned


def _clean_optional_id(value: object) -> str:
    if not isinstance(value, str):
        return ''
    cleaned = value.strip()
    if (
        not cleaned
        or len(cleaned) > 128
        or any(ch in cleaned for ch in ('/', '\\', '\x00', '\r', '\n'))
        or '..' in cleaned
    ):
        return ''
    return cleaned


def create_import_job(job_data: Dict[str, Any], *, firestore_client: Optional[Any] = None) -> str:
    """Create a new import job in Firestore."""
    if not isinstance(job_data, dict):
        raise ValueError('job_data must be a dictionary')
    job_id = _sanitize_id(job_data.get('id'), 'job_id')
    client = firestore_client if firestore_client is not None else db
    payload: Dict[str, Any] = dict(job_data)
    payload['id'] = job_id
    raw_uid: object = payload.get('uid')
    if isinstance(raw_uid, str):
        payload['uid'] = raw_uid.strip()
    job_ref = client.collection('import_jobs').document(job_id)
    job_ref.set(payload)
    return job_id


def update_import_job(job_id: str, updates: Dict[str, Any], *, firestore_client: Optional[Any] = None) -> bool:
    """Update an existing import job."""
    clean_id = _sanitize_id(job_id, 'job_id')
    if not isinstance(updates, dict) or not updates:
        return False
    client = firestore_client if firestore_client is not None else db
    job_ref = client.collection('import_jobs').document(clean_id)
    try:
        job_ref.update(updates)
        return True
    except NotFound:
        return False


def update_import_job_unless_cancelled(
    job_id: str, updates: Dict[str, Any], *, firestore_client: Optional[Any] = None
) -> bool:
    """Apply ``updates`` unless the job was cancelled or deleted; whether they were applied.

    The status is read and the update written in one transaction, so a cancel the
    user makes while a worker writes cannot be overwritten by it.
    """
    clean_id = _sanitize_id(job_id, 'job_id')
    if not isinstance(updates, dict) or not updates:
        return False
    client = firestore_client if firestore_client is not None else db
    job_ref = client.collection('import_jobs').document(clean_id)

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
    clean_id = _sanitize_id(job_id, 'job_id')
    client = firestore_client if firestore_client is not None else get_firestore_client()
    job_ref = client.collection('import_jobs').document(clean_id)

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=transaction)
        raw: object = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        current: Optional[Dict[str, Any]] = cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
        if not current or current.get('status') not in ('pending', 'processing'):
            return False
        transaction.update(job_ref, {'status': _CANCELLED, 'error': 'Cancelled by user'})
        return True

    return bool(run_transactional(client, apply))


def update_import_job_progress(
    job_id: str, progress: Dict[str, Any], *, firestore_client: Optional[Any] = None
) -> bool:
    """Write progress counters to a job that still exists, whatever its status; whether they were written.

    For a worker that stops on a cancel: it records the counts it reached, while
    ``status`` and every other field stay as the cancel left them. Only
    ``IMPORT_JOB_PROGRESS_FIELDS`` may be written, and a deleted job is not recreated.
    """
    clean_id = _sanitize_id(job_id, 'job_id')
    if not isinstance(progress, dict) or not progress:
        return False
    unexpected = set(progress) - IMPORT_JOB_PROGRESS_FIELDS
    if unexpected:
        raise ValueError(f'not import job progress fields: {sorted(unexpected)}')
    client = firestore_client if firestore_client is not None else db
    job_ref = client.collection('import_jobs').document(clean_id)

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        if not getattr(job_ref.get(transaction=transaction), 'exists', False):
            return False
        transaction.update(job_ref, progress)
        return True

    return bool(run_transactional(client, apply))


def get_import_job(job_id: str, *, firestore_client: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Get a single import job by ID."""
    clean_id = _clean_optional_id(job_id)
    if not clean_id:
        return None
    client = firestore_client if firestore_client is not None else db
    try:
        job_ref = client.collection('import_jobs').document(clean_id)
        job_doc = job_ref.get()
    except Exception as exc:
        logger.warning('Failed to fetch import job id=%s: %s', clean_id, exc)
        return None
    if getattr(job_doc, "exists", False):
        raw: object = job_doc.to_dict()
        if isinstance(raw, dict):
            data = dict(cast(Dict[str, Any], raw))
            if not data.get('id') and getattr(job_doc, 'id', None):
                data['id'] = str(job_doc.id)
            return data
    return None


def get_import_jobs(uid: str, limit: int = 50, *, firestore_client: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Get all import jobs for a user, ordered by created_at descending."""
    clean_uid = _clean_optional_id(uid)
    if not clean_uid:
        return []
    bounded_limit = max(1, min(limit, 1000)) if isinstance(limit, int) and not isinstance(limit, bool) else 50
    client = firestore_client if firestore_client is not None else db
    query = (
        client.collection('import_jobs')
        .where(filter=FieldFilter('uid', '==', clean_uid))
        .order_by('created_at', direction='DESCENDING')
        .limit(bounded_limit)
    )
    try:
        docs = query.stream()
    except Exception as exc:
        logger.warning('Failed to stream import jobs for uid=%s: %s', clean_uid, exc)
        return []
    jobs: List[Dict[str, Any]] = []
    for doc in docs:
        try:
            raw: object = doc.to_dict()
        except Exception as exc:
            logger.warning('Skipping unreadable import job doc %s: %s', getattr(doc, 'id', 'unknown'), exc)
            continue
        if isinstance(raw, dict):
            data = dict(cast(Dict[str, Any], raw))
            if not data.get('id') and getattr(doc, 'id', None):
                data['id'] = str(doc.id)
            jobs.append(data)
    return jobs


def delete_import_job(job_id: str, *, firestore_client: Optional[Any] = None) -> bool:
    """Delete an import job."""
    clean_id = _sanitize_id(job_id, 'job_id')
    client = firestore_client if firestore_client is not None else db
    job_ref = client.collection('import_jobs').document(clean_id)
    try:
        job_ref.delete()
        return True
    except NotFound:
        return False
