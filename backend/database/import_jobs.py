from datetime import datetime
from typing import List, Optional

from google.cloud.firestore_v1 import FieldFilter

from ._client import db


def create_import_job(job_data: dict) -> str:
    """Create a new import job in Firestore."""
    job_id = job_data['id']
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.set(job_data)
    return job_id


def update_import_job(job_id: str, updates: dict) -> None:
    """Update an existing import job."""
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.update(updates)


def get_import_job(job_id: str) -> Optional[dict]:
    """Get a single import job by ID."""
    job_ref = db.collection('import_jobs').document(job_id)
    job_doc = job_ref.get()
    if job_doc.exists:
        return job_doc.to_dict()
    return None


def get_import_jobs(uid: str, limit: int = 50) -> List[dict]:
    """Get all import jobs for a user, ordered by created_at descending."""
    query = (
        db.collection('import_jobs')
        .where(filter=FieldFilter('uid', '==', uid))
        .order_by('created_at', direction='DESCENDING')
        .limit(limit)
    )
    return [doc.to_dict() for doc in query.stream()]


def delete_import_job(job_id: str) -> None:
    """Delete an import job."""
    job_ref = db.collection('import_jobs').document(job_id)
    job_ref.delete()
