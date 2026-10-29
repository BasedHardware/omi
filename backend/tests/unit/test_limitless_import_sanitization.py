"""CWE-209: Limitless import upload exception details must never leak to clients or database error records.

Covers issue #18767:
  - backend/routers/imports.py (import_limitless_data — POST /v1/import/limitless)

The fix pattern:
  - Client-facing HTTPException detail is a generic message: "Failed to save uploaded file"
  - Import job database error field is sanitized to "Failed to save uploaded file"
  - Server-side logger.error records structured error_class and job_id without leaking raw exception string to the client.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException, UploadFile

from models.import_job import ImportJob, ImportJobStatus, ImportSourceType
import routers.imports as imports_mod

GENERIC_DETAIL = "Failed to save uploaded file"

LEAK_MARKERS = [
    "/etc/",
    "/var/",
    "/tmp/",
    "/home/",
    "C:\\",
    "\\temp\\",
    "No space left on device",
    "Permission denied",
    "disk_io_error_marker_12345",
]


class _FakeUploadFile:
    def __init__(self, filename="data.zip"):
        self.filename = filename

    async def read(self, size):
        raise OSError("disk_io_error_marker_12345 at /var/app/internal_storage/temp_spool.zip: No space left on device")


@pytest.fixture
def fake_job():
    return ImportJob(
        id="job_test_123",
        uid="user_test_456",
        status=ImportJobStatus.pending,
        source_type=ImportSourceType.limitless,
    )


@pytest.mark.asyncio
async def test_limitless_import_exception_sanitized(fake_job):
    fake_file = _FakeUploadFile()
    updated_fields = {}

    def fake_update(job_id, fields):
        updated_fields.update(fields)

    with (
        patch.object(imports_mod, "create_import_job", return_value=fake_job),
        patch.object(imports_mod.import_jobs_db, "update_import_job", side_effect=fake_update) as mock_update,
        patch("builtins.open", MagicMock()),
        patch.object(imports_mod.logger, "error") as mock_logger,
    ):
        with pytest.raises(HTTPException) as exc_info:
            await imports_mod.import_limitless_data(file=fake_file, language="en", uid="user_test_456")

        assert exc_info.value.status_code == 500
        # Detail must be generic without leaking raw exception or internal paths
        assert exc_info.value.detail == GENERIC_DETAIL
        for marker in LEAK_MARKERS:
            assert marker not in exc_info.value.detail

        # Database error field must also be sanitized
        assert updated_fields.get("status") == ImportJobStatus.failed.value
        assert updated_fields.get("error") == GENERIC_DETAIL

        # Logger must record the error class server-side
        mock_logger.assert_called_once()
        log_args = mock_logger.call_args[0]
        assert "limitless import upload not staged" in log_args[0]
