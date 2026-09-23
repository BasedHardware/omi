"""Unit tests for imports router exception sanitization.

Verifies that file streaming and I/O errors during archive upload in import_limitless
are logged server-side and masked in HTTP 500 response bodies without exposing
internal filesystem paths or OS errno details.
"""

from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException, UploadFile
import pytest

from routers import imports as imports_routes


@pytest.mark.asyncio
async def test_import_limitless_masks_io_error_detail(monkeypatch):
    """Ensure import_limitless raises sanitized 500 without internal paths or errno strings."""
    mock_job = MagicMock(id="job-uuid-1234")
    monkeypatch.setattr(imports_routes, "create_import_job", MagicMock(return_value=mock_job))

    mock_db = MagicMock()
    monkeypatch.setattr(imports_routes, "import_jobs_db", mock_db)

    async def mock_run_blocking(executor, func, *args, **kwargs):
        if func == imports_routes.create_import_job:
            return mock_job
        if func == open:
            raise OSError(28, "No space left on device: '/tmp/imports/job-uuid-1234_data.zip'")
        if func == mock_db.update_import_job:
            return None
        return func(*args, **kwargs)

    monkeypatch.setattr(imports_routes, "run_blocking", mock_run_blocking)

    mock_upload = MagicMock(spec=UploadFile)
    mock_upload.filename = "export.zip"
    mock_upload.read = AsyncMock(return_value=b"data")

    with pytest.raises(HTTPException) as exc_info:
        await imports_routes.import_limitless(
            file=mock_upload,
            language="en",
            uid="test-user-999",
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Failed to save uploaded file"
    assert "/tmp/imports" not in exc_info.value.detail
    assert "No space left" not in exc_info.value.detail
    assert "job-uuid-1234" not in exc_info.value.detail
