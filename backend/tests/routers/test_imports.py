"""Import-job lifecycle: POST /v1/import/jobs/{job_id}/cancel and DELETE /v1/import/jobs/{job_id}.

A user can start, list, and get the status of import jobs, but there was no way to cancel a stuck
or running import or remove a finished one. cancel handles the in-progress states (pending/
processing -> cancelled); delete handles the terminal states (completed/failed/cancelled). Both
mirror the existing ownership pattern (404 unknown, 403 wrong owner). The worker skips its final
status write when the job was cancelled mid-run, so a cancel sticks.

Test isolation: routers.imports imports cleanly (tests/conftest.py sets the env, stubs tiktoken,
and blocks network), so the module is imported normally and the db helpers are patched.
"""

import os

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from routers import imports as imports_mod
from models.import_job import ImportJobStatus

UID = "u1"


def _job(status, uid=UID, job_id="j1"):
    return {
        "id": job_id,
        "uid": uid,
        "status": status,
        "total_files": 3,
        "processed_files": 3,
        "conversations_created": 2,
        "created_at": "2026-01-01T00:00:00",
        "error": None,
    }


class TestCancelImportJob:
    @pytest.mark.parametrize("status", ["pending", "processing"])
    def test_cancel_in_progress(self, status):
        with patch.object(imports_mod.import_jobs_db, "get_import_job", return_value=_job(status)), patch.object(
            imports_mod.import_jobs_db, "update_import_job"
        ) as upd:
            resp = imports_mod.cancel_import_job("j1", uid=UID)
        assert resp.status == ImportJobStatus.cancelled
        upd.assert_called_once()
        assert upd.call_args.args[1]["status"] == ImportJobStatus.cancelled.value

    @pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
    def test_cancel_terminal_is_409(self, status):
        with patch.object(imports_mod.import_jobs_db, "get_import_job", return_value=_job(status)), patch.object(
            imports_mod.import_jobs_db, "update_import_job"
        ) as upd:
            with pytest.raises(HTTPException) as ei:
                imports_mod.cancel_import_job("j1", uid=UID)
        assert ei.value.status_code == 409
        upd.assert_not_called()

    def test_cancel_missing_is_404(self):
        with patch.object(imports_mod.import_jobs_db, "get_import_job", return_value=None):
            with pytest.raises(HTTPException) as ei:
                imports_mod.cancel_import_job("j1", uid=UID)
        assert ei.value.status_code == 404

    def test_cancel_wrong_owner_is_403(self):
        with patch.object(imports_mod.import_jobs_db, "get_import_job", return_value=_job("pending", uid="other")):
            with pytest.raises(HTTPException) as ei:
                imports_mod.cancel_import_job("j1", uid=UID)
        assert ei.value.status_code == 403


class TestDeleteImportJob:
    @pytest.mark.parametrize("status", ["completed", "failed", "cancelled"])
    def test_delete_terminal_ok(self, status):
        with patch.object(imports_mod.import_jobs_db, "get_import_job", return_value=_job(status)), patch.object(
            imports_mod.import_jobs_db, "delete_import_job"
        ) as dele:
            result = imports_mod.delete_import_job("j1", uid=UID)
        assert result == {"status": "ok", "job_id": "j1"}
        dele.assert_called_once_with("j1")

    @pytest.mark.parametrize("status", ["pending", "processing"])
    def test_delete_in_progress_is_409(self, status):
        with patch.object(imports_mod.import_jobs_db, "get_import_job", return_value=_job(status)), patch.object(
            imports_mod.import_jobs_db, "delete_import_job"
        ) as dele:
            with pytest.raises(HTTPException) as ei:
                imports_mod.delete_import_job("j1", uid=UID)
        assert ei.value.status_code == 409
        dele.assert_not_called()

    def test_delete_missing_is_404(self):
        with patch.object(imports_mod.import_jobs_db, "get_import_job", return_value=None):
            with pytest.raises(HTTPException) as ei:
                imports_mod.delete_import_job("j1", uid=UID)
        assert ei.value.status_code == 404

    def test_delete_wrong_owner_is_403(self):
        with patch.object(imports_mod.import_jobs_db, "get_import_job", return_value=_job("completed", uid="other")):
            with pytest.raises(HTTPException) as ei:
                imports_mod.delete_import_job("j1", uid=UID)
        assert ei.value.status_code == 403
