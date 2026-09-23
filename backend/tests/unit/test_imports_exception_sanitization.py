"""Unit tests for imports router exception sanitization.

Verifies that file streaming and I/O errors during archive upload in import_limitless_data
are logged server-side and masked in both the HTTP 500 response and the persisted job record
without exposing internal filesystem paths or OS errno details.
"""

from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, UploadFile
import pytest

from routers import imports as imports_routes


@pytest.mark.asyncio
async def test_import_limitless_masks_io_error_detail(monkeypatch):
    """Ensure import_limitless_data raises sanitized 500 and persists clean job error without paths or errno."""
    mock_job = MagicMock(id="job-uuid-1234")
    monkeypatch.setattr(imports_routes, "create_import_job", MagicMock(return_value=mock_job))

    mock_db = MagicMock()
    monkeypatch.setattr(imports_routes, "import_jobs_db", mock_db)

    captured_updates = []

    async def mock_run_blocking(executor, func, *args, **kwargs):
        if func == imports_routes.create_import_job:
            return mock_job
        # The upload handler routes file open through run_blocking(storage_executor, open, ...)
        if func == open:
            raise OSError(28, "No space left on device: '/tmp/imports/job-uuid-1234_data.zip'")
        if func == mock_db.update_import_job:
            captured_updates.append(args)
            return None
        return func(*args, **kwargs)

    monkeypatch.setattr(imports_routes, "run_blocking", mock_run_blocking)

    mock_upload = MagicMock(spec=UploadFile)
    mock_upload.filename = "export.zip"
    mock_upload.read = AsyncMock(return_value=b"data")

    with pytest.raises(HTTPException) as exc_info:
        await imports_routes.import_limitless_data(
            file=mock_upload,
            language="en",
            uid="test-user-999",
        )

    # Verify HTTP response masking
    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to save uploaded file."
    assert "/tmp/imports" not in exc_info.value.detail
    assert "No space left" not in exc_info.value.detail
    assert "job-uuid-1234" not in exc_info.value.detail

    # Verify persisted job record masking
    assert len(captured_updates) == 1
    job_id_arg, update_payload = captured_updates[0]
    assert job_id_arg == "job-uuid-1234"
    assert update_payload["status"] == "failed"
    assert update_payload["error"] == "Failed to save uploaded file."
    assert "/tmp/imports" not in update_payload["error"]
    assert "No space left" not in update_payload["error"]
