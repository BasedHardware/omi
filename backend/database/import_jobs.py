from typing import Any, Dict, List, Optional, cast

from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def _is_valid_job_id(job_id: Any) -> bool:
    return bool(
        job_id
        and isinstance(job_id, str)
        and job_id.strip()
        and '/' not in job_id
        and '\\' not in job_id
        and '..' not in job_id
    )


def create_import_job(job_data: Dict[str, Any]) -> str:
    """Create a new import job in Firestore."""
    job_id = job_data['id']
    if not _is_valid_job_id(job_id):
        raise ValueError("Invalid job ID format")
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.set(job_data)
    return job_id


def update_import_job(job_id: str, updates: Dict[str, Any]) -> None:
    """Update an existing import job."""
    if not _is_valid_job_id(job_id):
        raise ValueError("Invalid job ID format")
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.update(updates)


def get_import_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a single import job by ID."""
    if not _is_valid_job_id(job_id):
        return None
    job_ref = db.collection('import_jobs').document(job_id)
    job_doc = job_ref.get()
    if getattr(job_doc, "exists", False):
        raw: object = job_doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_import_jobs(uid: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all import jobs for a user, ordered by created_at descending."""
    if not uid or not isinstance(uid, str) or not uid.strip():
        return []
    clamped_limit = max(1, min(int(limit), 1000))
    query = (
        db.collection('import_jobs')
        .where(filter=FieldFilter('uid', '==', uid))
        .order_by('created_at', direction='DESCENDING')
        .limit(clamped_limit)
    )
    jobs: List[Dict[str, Any]] = []
    for doc in query.stream():
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            jobs.append(cast(Dict[str, Any], raw))
    return jobs


def delete_import_job(job_id: str) -> None:
    """Delete an import job."""
    if not _is_valid_job_id(job_id):
        raise ValueError("Invalid job ID format")
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.delete()
