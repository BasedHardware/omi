import logging
from typing import Any, Dict, List, Optional, cast

from google.api_core.exceptions import NotFound
from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db, firestore_failure_reason, get_firestore_client, run_transactional

logger = logging.getLogger(__name__)

# ImportJobStatus.cancelled; the database layer does not import the API models.
_CANCELLED = 'cancelled'
# The counters a worker reports: all that a progress-only write may change.
IMPORT_JOB_PROGRESS_FIELDS = frozenset({'processed_files', 'conversations_created', 'conversations_skipped'})


def _sanitize_id(id_val: Any, name: str = 'id') -> str:
    """Validates and trims document identifiers, rejecting empty strings and path traversal."""
    if not isinstance(id_val, str):
        raise ValueError(f"Invalid {name}: must be a non-empty string")
    cleaned = id_val.strip()
    if not cleaned or len(cleaned) > 256:
        raise ValueError(f"Invalid {name}: must be between 1 and 256 characters")
    if '/' in cleaned or '\\' in cleaned or '..' in cleaned:
        raise ValueError(f"Invalid {name}: contains path traversal characters")
    if any(ord(c) < 32 or ord(c) == 127 for c in cleaned):
        raise ValueError(f"Invalid {name}: contains control characters")
    return cleaned


def _clean_optional_id(id_val: Any) -> Optional[str]:
    """Cleans optional identifiers, returning None for invalid or empty inputs without raising."""
    if not isinstance(id_val, str):
        return None
    cleaned = id_val.strip()
    if not cleaned or len(cleaned) > 256:
        return None
    if '/' in cleaned or '\\' in cleaned or '..' in cleaned:
        return None
    if any(ord(c) < 32 or ord(c) == 127 for c in cleaned):
        return None
    return cleaned


def _get_client(client: Optional[Any] = None) -> Any:
    return client if client is not None else db


def create_import_job(job_data: Dict[str, Any], *, firestore_client: Optional[Any] = None) -> str:
    """Create a new import job in Firestore."""
    if not isinstance(job_data, dict):
        raise ValueError("job_data must be a dictionary")
    raw_id = job_data.get('id')
    job_id = _sanitize_id(raw_id, 'job_id')
    if 'uid' in job_data:
        _sanitize_id(job_data['uid'], 'uid')
    client = _get_client(firestore_client)
    job_ref = client.collection('import_jobs').document(job_id)
    job_ref.set(job_data)
    return job_id


def update_import_job(job_id: str, updates: Dict[str, Any], *, firestore_client: Optional[Any] = None) -> bool:
    """Update an existing import job. Returns True if updated, False if empty or not found."""
    cleaned_id = _sanitize_id(job_id, 'job_id')
    if not updates or not isinstance(updates, dict):
        return False
    client = _get_client(firestore_client)
    job_ref = client.collection('import_jobs').document(cleaned_id)
    try:
        job_ref.update(updates)
        return True
    except NotFound:
        return False
    except Exception as e:
        if getattr(e, "code", None) in (404,):
            return False
        raise


def update_import_job_unless_cancelled(
    job_id: str, updates: Dict[str, Any], *, firestore_client: Optional[Any] = None
) -> bool:
    """Apply ``updates`` unless the job was cancelled or deleted; whether they were applied.

    The status is read and the update written in one transaction, so a cancel the
    user makes while a worker writes cannot be overwritten by it.
    """
    cleaned_id = _sanitize_id(job_id, 'job_id')
    if not updates or not isinstance(updates, dict):
        return False
    client = _get_client(firestore_client)
    job_ref = client.collection('import_jobs').document(cleaned_id)

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=transaction)
        current: object = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if not isinstance(current, dict) or current.get('status') == _CANCELLED:
            return False
        transaction.update(job_ref, updates)
        return True

    return bool(run_transactional(client, apply))


def cancel_import_job_if_active(job_id: str, *, firestore_client: Optional[Any] = None) -> bool:
    """Cancel only a pending or processing job, in the transaction that reads its status."""
    cleaned_id = _clean_optional_id(job_id)
    if not cleaned_id:
        return False
    client = _get_client(firestore_client)
    job_ref = client.collection('import_jobs').document(cleaned_id)

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=transaction)
        current = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if not isinstance(current, dict) or current.get('status') not in ('pending', 'processing'):
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
    cleaned_id = _sanitize_id(job_id, 'job_id')
    if not isinstance(progress, dict):
        raise ValueError("progress must be a dictionary")
    unexpected = set(progress) - IMPORT_JOB_PROGRESS_FIELDS
    if unexpected:
        raise ValueError(f'not import job progress fields: {sorted(unexpected)}')
    client = _get_client(firestore_client)
    job_ref = client.collection('import_jobs').document(cleaned_id)

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        if not getattr(job_ref.get(transaction=transaction), 'exists', False):
            return False
        transaction.update(job_ref, progress)
        return True

    return bool(run_transactional(client, apply))


def get_import_job(job_id: str, *, firestore_client: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Get a single import job by ID with error boundary and id backfill."""
    cleaned_id = _clean_optional_id(job_id)
    if not cleaned_id:
        return None
    client = _get_client(firestore_client)
    try:
        job_ref = client.collection('import_jobs').document(cleaned_id)
        job_doc = job_ref.get()
        if getattr(job_doc, "exists", False):
            raw: object = job_doc.to_dict()
            if isinstance(raw, dict):
                if 'id' not in raw or not raw['id']:
                    raw['id'] = str(getattr(job_doc, 'id', cleaned_id))
                return cast(Dict[str, Any], raw)
        return None
    except Exception as exc:
        logger.warning("Failed to get import job id=%s reason=%s", cleaned_id, firestore_failure_reason(exc))
        return None


def get_import_jobs(uid: str, limit: int = 50, *, firestore_client: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Get all import jobs for a user, ordered by created_at descending."""
    cleaned_uid = _clean_optional_id(uid)
    if not cleaned_uid:
        return []
    try:
        clamped_limit = max(1, min(1000, int(limit)))
    except (TypeError, ValueError):
        clamped_limit = 50

    client = _get_client(firestore_client)
    jobs: List[Dict[str, Any]] = []
    try:
        query = (
            client.collection('import_jobs')
            .where(filter=FieldFilter('uid', '==', cleaned_uid))
            .order_by('created_at', direction='DESCENDING')
            .limit(clamped_limit)
        )
        for doc in query.stream():
            try:
                raw: object = doc.to_dict()
                if isinstance(raw, dict):
                    if 'id' not in raw or not raw['id']:
                        raw['id'] = str(getattr(doc, 'id', ''))
                    jobs.append(cast(Dict[str, Any], raw))
            except Exception as doc_exc:
                logger.warning("Failed to deserialize import job doc: %s", doc_exc)
                continue
    except Exception as exc:
        logger.warning("Failed to get import jobs uid=%s reason=%s", cleaned_uid, firestore_failure_reason(exc))
        return []
    return jobs


def delete_import_job(job_id: str, *, firestore_client: Optional[Any] = None) -> bool:
    """Delete an import job. Returns True if deleted, False if already deleted or invalid."""
    cleaned_id = _clean_optional_id(job_id)
    if not cleaned_id:
        return False
    client = _get_client(firestore_client)
    job_ref = client.collection('import_jobs').document(cleaned_id)
    try:
        job_ref.delete()
        return True
    except NotFound:
        return False
    except Exception as e:
        if getattr(e, "code", None) in (404,):
            return False
        raise
