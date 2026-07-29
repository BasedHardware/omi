from typing import Any, Dict, List, Optional, cast

from database.store import Filter, get_document_store


def _store():
    return get_document_store()


def create_import_job(job_data: Dict[str, Any]) -> str:
    """Create a new import job."""
    job_id = job_data['id']
    _store().set(f'import_jobs/{job_id}', job_data)
    return job_id


def update_import_job(job_id: str, updates: Dict[str, Any]) -> None:
    """Update an existing import job."""
    _store().update(f'import_jobs/{job_id}', updates)


def get_import_job(job_id: str) -> Optional[Dict[str, Any]]:
    """Get a single import job by ID."""
    job_doc = _store().get(f'import_jobs/{job_id}')
    if job_doc.exists:
        raw: object = job_doc.to_dict()
        return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    return None


def get_import_jobs(uid: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get all import jobs for a user, ordered by created_at descending."""
    filters: List[Filter] = [('uid', '==', uid)]
    docs = _store().query(
        'import_jobs',
        filters=filters,
        order_by='created_at',
        direction='desc',
        limit=limit,
    )
    jobs: List[Dict[str, Any]] = []
    for doc in docs:
        raw: object = doc.to_dict()
        if isinstance(raw, dict):
            jobs.append(cast(Dict[str, Any], raw))
    return jobs


def delete_import_job(job_id: str) -> None:
    """Delete an import job."""
    _store().delete(f'import_jobs/{job_id}')
