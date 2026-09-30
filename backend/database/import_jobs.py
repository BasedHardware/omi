"""CRUD operations and resilience guards for user import jobs."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, cast

from google.cloud.firestore_v1 import FieldFilter

from ._client import db, get_firestore_client

logger = logging.getLogger(__name__)

MAX_ID_LENGTH = 128
MAX_IMPORT_JOBS_LIMIT = 1000
DEFAULT_IMPORT_JOBS_LIMIT = 50


def _clean_id(id_val: Optional[str]) -> str:
    """Validate and sanitize user or job ID."""
    if not isinstance(id_val, str):
        return ""
    cleaned = id_val.strip()
    if (
        not cleaned
        or len(cleaned) > MAX_ID_LENGTH
        or "/" in cleaned
        or "\\" in cleaned
        or ".." in cleaned
        or "\x00" in cleaned
    ):
        return ""
    return cleaned


def _resolve_client(client: Optional[Any] = None) -> Any:
    if client is not None:
        return client
    try:
        c = get_firestore_client()
        if c is not None:
            return c
    except Exception:
        pass
    return db


def create_import_job(job_data: Dict[str, Any], client: Optional[Any] = None) -> str:
    """Create a new import job in Firestore."""
    if not isinstance(job_data, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("job_data must be a dictionary")

    raw_id = job_data.get("id")
    job_id = _clean_id(raw_id)
    if not job_id:
        raise ValueError("Invalid or missing 'id' in job_data")

    payload = dict(job_data)
    if "uid" in payload:
        clean_uid = _clean_id(payload.get("uid"))
        if not clean_uid:
            raise ValueError("Invalid or missing 'uid' in job_data")
        payload["uid"] = clean_uid

    fs = _resolve_client(client)
    try:
        job_ref = fs.collection("import_jobs").document(job_id)
        job_ref.set(payload)
        return job_id
    except Exception as e:
        logger.error("Failed to create import job %s: %s", job_id, e)
        raise


def update_import_job(job_id: str, updates: Dict[str, Any], client: Optional[Any] = None) -> bool:
    """Update an existing import job in Firestore."""
    cleaned_id = _clean_id(job_id)
    if not cleaned_id:
        raise ValueError(f"Invalid or missing 'job_id': {job_id!r}")

    if not isinstance(updates, dict):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError(f"Invalid updates payload for job {cleaned_id}: expected dict, got {type(updates).__name__}")

    if not updates:
        return True

    fs = _resolve_client(client)
    try:
        job_ref = fs.collection("import_jobs").document(cleaned_id)
        job_ref.update(updates)
        return True
    except Exception as e:
        logger.error("Failed to update import job %s: %s", cleaned_id, e)
        raise


def get_import_job(job_id: str, client: Optional[Any] = None) -> Optional[Dict[str, Any]]:
    """Get a single import job by ID."""
    cleaned_id = _clean_id(job_id)
    if not cleaned_id:
        return None

    fs = _resolve_client(client)
    try:
        job_ref = fs.collection("import_jobs").document(cleaned_id)
        job_doc = job_ref.get()
        if getattr(job_doc, "exists", False):
            raw: object = job_doc.to_dict()
            return cast(Dict[str, Any], raw) if isinstance(raw, dict) else None
    except Exception as e:
        logger.warning("Failed to fetch import job %s: %s", cleaned_id, e)
    return None


def get_import_jobs(
    uid: str,
    limit: int = DEFAULT_IMPORT_JOBS_LIMIT,
    client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Get all import jobs for a user, ordered by created_at descending."""
    cleaned_uid = _clean_id(uid)
    if not cleaned_uid:
        return []

    try:
        clamped_limit = max(1, min(MAX_IMPORT_JOBS_LIMIT, int(limit)))
    except (TypeError, ValueError):
        clamped_limit = DEFAULT_IMPORT_JOBS_LIMIT

    fs = _resolve_client(client)
    try:
        query = (
            fs.collection("import_jobs")
            .where(filter=FieldFilter("uid", "==", cleaned_uid))
            .order_by("created_at", direction="DESCENDING")
            .limit(clamped_limit)
        )
        jobs: List[Dict[str, Any]] = []
        for doc in query.stream():
            raw: object = doc.to_dict()
            if isinstance(raw, dict):
                jobs.append(cast(Dict[str, Any], raw))
        return jobs
    except Exception as e:
        logger.warning("Failed to query import jobs for user %s: %s", cleaned_uid, e)
        return []


def delete_import_job(job_id: str, client: Optional[Any] = None) -> bool:
    """Delete an import job in Firestore."""
    cleaned_id = _clean_id(job_id)
    if not cleaned_id:
        raise ValueError(f"Invalid or missing 'job_id': {job_id!r}")

    fs = _resolve_client(client)
    try:
        job_ref = fs.collection("import_jobs").document(cleaned_id)
        job_ref.delete()
        return True
    except Exception as e:
        logger.error("Failed to delete import job %s: %s", cleaned_id, e)
        raise
