"""
Import endpoints for importing data from external sources.
"""

import os
import threading
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import database.import_jobs as import_jobs_db
import database.conversations as conversations_db
from models.import_job import ImportJob, ImportJobResponse, ImportJobStatus, ImportSourceType
from utils.other import endpoints as auth
from utils.imports.limitless import create_import_job, process_limitless_import

router = APIRouter()

# Temp directory for uploaded files
TEMP_DIR = '_temp'


@router.post(
    '/v1/import/limitless',
    response_model=ImportJobResponse,
    tags=['import'],
)
async def import_limitless_data(
    file: UploadFile = File(...),
    language: str = 'en',
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Start a Limitless data import from a ZIP file export.

    The import runs in the background. Use GET /v1/import/jobs/{job_id} to check status.

    Args:
        file: ZIP file containing Limitless data export
        language: Language code for conversation processing (default: 'en')

    Returns:
        ImportJobResponse with job_id and initial status
    """
    # Validate file type
    if not file.filename or not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="File must be a ZIP archive")

    # Create import job
    job = create_import_job(uid, ImportSourceType.limitless)

    # Save uploaded file to temp directory
    os.makedirs(TEMP_DIR, exist_ok=True)
    zip_path = os.path.join(TEMP_DIR, f"{job.id}_{file.filename}")

    try:
        # Read and save the file
        contents = await file.read()
        with open(zip_path, 'wb') as f:
            f.write(contents)
    except Exception as e:
        # Clean up on error
        import_jobs_db.update_import_job(
            job.id, {'status': ImportJobStatus.failed.value, 'error': f"Failed to save uploaded file: {str(e)}"}
        )
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    # Start background processing
    thread = threading.Thread(target=process_limitless_import, args=(job.id, uid, zip_path, language), daemon=True)
    thread.start()

    return ImportJobResponse(
        job_id=job.id,
        status=ImportJobStatus.pending,
    )


@router.get(
    '/v1/import/jobs',
    response_model=List[ImportJobResponse],
    tags=['import'],
)
async def get_import_jobs(
    uid: str = Depends(auth.get_current_user_uid),
    limit: int = 50,
):
    """
    Get all import jobs for the current user.

    Returns:
        List of import jobs ordered by creation date (newest first)
    """
    jobs = import_jobs_db.get_import_jobs(uid, limit=limit)

    return [
        ImportJobResponse(
            job_id=job['id'],
            status=ImportJobStatus(job['status']),
            total_files=job.get('total_files'),
            processed_files=job.get('processed_files'),
            conversations_created=job.get('conversations_created'),
            created_at=job.get('created_at'),
            error=job.get('error'),
        )
        for job in jobs
    ]


@router.get(
    '/v1/import/jobs/{job_id}',
    response_model=ImportJobResponse,
    tags=['import'],
)
async def get_import_job_status(
    job_id: str,
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Get the status of a specific import job.

    Args:
        job_id: The import job ID

    Returns:
        ImportJobResponse with current job status and progress
    """
    job = import_jobs_db.get_import_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")

    # Verify ownership
    if job['uid'] != uid:
        raise HTTPException(status_code=403, detail="Not authorized to view this import job")

    return ImportJobResponse(
        job_id=job['id'],
        status=ImportJobStatus(job['status']),
        total_files=job.get('total_files'),
        processed_files=job.get('processed_files'),
        conversations_created=job.get('conversations_created'),
        created_at=job.get('created_at'),
        error=job.get('error'),
    )


@router.delete(
    '/v1/import/limitless/conversations',
    tags=['import'],
)
async def delete_limitless_conversations(
    uid: str = Depends(auth.get_current_user_uid),
):
    """
    Delete all conversations imported from Limitless.

    Returns:
        Number of deleted conversations
    """
    deleted_count = conversations_db.delete_conversations_by_source(uid, 'limitless')

    return {'deleted_count': deleted_count, 'message': f'Successfully deleted {deleted_count} Limitless conversations'}
