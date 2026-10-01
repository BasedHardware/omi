```python
import os
import re
from typing import Optional, Tuple

def _validate_job_id(job_id: str) -> Tuple[bool, str]:
    if not job_id:
        return (False, "Job ID is required.")
    if not re.match(r"^[a-zA-Z0-9_-]+$", job_id):
        return (False, "Invalid job ID. Allowed characters: letters, numbers, underscores, hyphens, and periods.")
    return (True, "")

def sanitize(s: str) -> str:
    return s.replace('\u00ad', '').replace('\\', '/')

async def import_limitless_data(job_id: str, file) -> str:
    TEMP_DIR = "temp_dir"
    filename = os.path.basename(file.filename)
    # Sanitize filename
    filename = re.sub(r'[^a-zA-Z0-9_.-]', '', filename)
    if not filename:
        filename = "upload.zip"
    zip_path = os.path.join(TEMP_DIR, f"{job_id}_{filename}")
    # Verify path
    if not os.path.abspath(zip_path).startswith(os.path.abspath(TEMP_DIR)):
        raise ValueError("Path traversal detected.")
    # Rest of the function...
    return "Success"

async def get_import_job_status(job_id: str) -> dict:
    valid, message = _validate_job_id(job_id)
    if not valid:
        return {"error": message}
    # Rest of the function...

async def cancel_import_job(job_id: str) -> dict:
    valid, message = _validate_job_id(job_id)
    if not valid:
        return {"error": message}
    # Rest of the function...

async def delete_import_job(job_id: str) -> dict:
    valid, message = _validate_job_id(job_id)
    if not valid:
        return {"error": message}
    # Rest of the function...

async def get_import_jobs(limit: int = 100) -> list:
    if limit < 1 or limit > 1000:
        limit = max(1, min(limit, 1000))
    # Query Firestore with limit
    return {"jobs": [...]}

# In import_jobs.py:
from imports import sanitize

async def write_error(job_id: str, e) -> dict:
    try:
        # Write to database
    except Exception as e:
        return {
            "error": "Failed to save uploaded file. Please try again.",
            "log": sanitize(str(e))
        }
```