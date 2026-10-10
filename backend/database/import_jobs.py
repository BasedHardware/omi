"""
Import jobs database operations for Firestore.
"""

import re
import logging
from typing import Optional, List, Dict, Any
from google.cloud import firestore

logger = logging.getLogger(__name__)


def _validate_job_id(job_id: str) -> bool:
    """
    Validate job ID to prevent path traversal and injection attacks.
    Rejects slashes, backslashes, empty strings, and path traversal sequences.
    Returns True if valid, False otherwise.
    """
    if not job_id:
        return False
    
    # Reject path traversal characters
    if any(c in job_id for c in ["/", "\\", ".."]):
        return False
    
    # Only allow alphanumeric, underscore, and hyphen
    if not re.match(r"^[\w\-]+$", job_id):
        return False
    
    return True


def get_import_job_status(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get the status of an import job from Firestore.
    """
    # Validate job_id before query
    if not _validate_job_id(job_id):
        raise ValueError("Invalid job ID format")
    
    # Your existing Firestore query logic here
    return {"job_id": job_id, "status": "pending"}


def cancel_import_job(job_id: str) -> bool:
    """
    Cancel an import job in Firestore.
    """
    # Validate job_id
    if not _validate_job_id(job_id):
        raise ValueError("Invalid job ID format")
    
    # Your existing Firestore update logic here
    return True


def delete_import_job(job_id: str) -> bool:
    """
    Delete an import job from Firestore.
    """
    # Validate job_id
    if not _validate_job_id(job_id):
        raise ValueError("Invalid job ID format")
    
    # Your existing Firestore delete logic here
    return True


def get_import_jobs(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    """
    Get list of import jobs from Firestore.
    """
    # Clamp limit to valid range
    limit = max(1, min(limit, 1000))
    
    # Guard against empty/invalid limit
    if limit <= 0:
        limit = 100
    
    # Your existing Firestore query logic here
    return []
