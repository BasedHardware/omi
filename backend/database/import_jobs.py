from typing import Any, Dict, List, Optional, cast

from google.cloud import firestore
from google.cloud.firestore_v1 import FieldFilter

from ._client import db, run_transactional

# ImportJobStatus.cancelled; the database layer does not import the API models.
_CANCELLED = 'cancelled'


def create_import_job(job_data: Dict[str, Any]) -> str:
    """Create a new import job in Firestore."""
    job_id = job_data['id']
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.set(job_data)
    return job_id


def update_import_job(job_id: str, updates: Dict[str, Any]) -> None:
    """Update an existing import job."""
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.update(updates)


def update_import_job_unless_cancelled(job_id: str, updates: Dict[str, Any]) -> bool:
    """Apply ``updates`` unless the job was cancelled or deleted; whether they were applied.

    The status is read and the update written in one transaction, so a cancel the
    user makes while a worker writes cannot be overwritten by it.
    """
    job_ref = db.collection('import_jobs').document(job_id)

    @firestore.transactional
    def apply(transaction: Any) -> bool:
        snapshot = job_ref.get(transaction=transaction)
        current: object = snapshot.to_dict() if getattr(snapshot, 'exists', False) else None
        if not isinstance(current, dict) or current.get('status') == _CANCELLED:
            return False
        transaction.update(job_ref, updates)
        return True

    return bool(run_transactional(db, apply))


def get_import_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a single import job by ID."""
    job_ref = db.collection('import_jobs').document(job_id)
    job_doc = job_ref.get()
    if getattr(job_doc, "exists", False):
        raw: object = job_doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_import_jobs(uid: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all import jobs for a user, ordered by created_at descending."""
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
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.delete()
