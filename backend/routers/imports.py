"""
Imports router for handling data import operations.
"""

import os
import re
import logging
import tempfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from typing import Optional

logger = logging.getLogger(__name__)

TEMP_DIR = os.getenv("IMPORT_TEMP_DIR", "/tmp/omi_imports")
router = APIRouter(prefix="/imports", tags=["imports"])


def _sanitize_filename(filename: str) -> str:
    """
    Sanitize uploaded filename to prevent path traversal.
    Returns safe basename with only alphanumeric, underscore, dot, and hyphen characters.
    Falls back to 'upload.zip' if malformed or empty.
    """
    if not filename:
        return "upload.zip"
    
    # Extract basename to remove any directory components
    safe_name = Path(filename).name
    
    # Strip non-alphanumeric characters except underscore, dot, and hyphen
    sanitized = re.sub(r"[^a-zA-Z0-9_.\-]", "", safe_name)
    
    # Fall back to default if empty after sanitization
    if not sanitized:
        return "upload.zip"
    
    return sanitized


def _validate_temp_path(requested_path: str, temp_dir: str) -> bool:
    """
    Verify that the canonical path is strictly within the temp directory.
    Returns True if safe, False otherwise.
    """
    try:
        abs_temp = os.path.abspath(temp_dir)
        abs_path = os.path.abspath(requested_path)
        return abs_path.startswith(abs_temp + os.sep) or abs_path == abs_temp
    except (ValueError, TypeError):
        return False


def _sanitize_for_logging(error_message: str) -> str:
    """
    Sanitize error messages for internal logging to prevent path disclosure.
    Removes absolute paths and sensitive system information.
    """
    # Remove common path patterns
    sanitized = re.sub(r"/[\w\-\.]+/[\w\-\.]+", "[PATH_REDACTED]", error_message)
    sanitized = re.sub(r"[A-Za-z]:\\[\w\-\.\\]+", "[PATH_REDACTED]", sanitized)
    return sanitized


@router.post("/limitless-data")
async def import_limitless_data(
    job_id: str,
    file: UploadFile = File(...),
):
    """
    Import limitless data from uploaded zip file.
    """
    # Validate job_id format
    if not job_id or not re.match(r"^[\w\-]+$", job_id):
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    
    # Sanitize filename to prevent path traversal
    safe_filename = _sanitize_filename(file.filename)
    
    # Construct path and verify it's within temp directory
    zip_path = os.path.join(TEMP_DIR, f"{job_id}_{safe_filename}")
    
    if not _validate_temp_path(zip_path, TEMP_DIR):
        logger.error("Path traversal attempt blocked: %s", _sanitize_for_logging(zip_path))
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    try:
        # Ensure temp directory exists
        os.makedirs(TEMP_DIR, exist_ok=True)
        
        # Write file in chunks
        with open(zip_path, "wb") as f:
            while chunk := await file.read(8192):
                f.write(chunk)
                
    except Exception as e:
        # Log sanitized error internally
        logger.error("Failed to save uploaded file: %s", _sanitize_for_logging(str(e)))
        # Return generic error to client - do not leak internal details
        raise HTTPException(
            status_code=500,
            detail="Failed to save uploaded file. Please try again."
        )
    
    return {"job_id": job_id, "filename": safe_filename, "status": "uploaded"}


@router.get("/jobs/{job_id}/status")
async def get_import_job_status(job_id: str):
    """
    Get the status of an import job.
    """
    # Validate job_id - reject path traversal attempts
    if not job_id or any(c in job_id for c in ["/", "\\", ".."]):
        raise HTTPException(status_code=400, detail="Invalid job ID")
    
    # Your existing job status logic here
    return {"job_id": job_id, "status": "pending"}


@router.post("/jobs/{job_id}/cancel")
async def cancel_import_job(job_id: str):
    """
    Cancel an import job.
    """
    # Validate job_id
    if not job_id or any(c in job_id for c in ["/", "\\", ".."]):
        raise HTTPException(status_code=400, detail="Invalid job ID")
    
    # Your existing cancel logic here
    return {"job_id": job_id, "status": "cancelled"}


@router.delete("/jobs/{job_id}")
async def delete_import_job(job_id: str):
    """
    Delete an import job.
    """
    # Validate job_id
    if not job_id or any(c in job_id for c in ["/", "\\", ".."]):
        raise HTTPException(status_code=400, detail="Invalid job ID")
    
    # Your existing delete logic here
    return {"job_id": job_id, "status": "deleted"}


@router.get("/jobs")
async def get_import_jobs(limit: int = 100, offset: int = 0):
    """
    Get list of import jobs.
    """
    # Clamp limit to reasonable range
    limit = max(1, min(limit, 1000))
    
    # Validate offset
    if offset < 0:
        offset = 0
    
    # Your existing list logic here
    return {"jobs": [], "limit": limit, "offset": offset}
