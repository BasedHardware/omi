import os
from unittest.mock import patch
import pytest
from fastapi import HTTPException

os.environ.setdefault('OPENAI_API_KEY', 'sk-test-not-real')
os.environ.setdefault('ENCRYPTION_SECRET', 'omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv')

from routers import imports as imports_mod


def test_get_import_jobs_firestore_exception_handled():
    with patch.object(
        imports_mod.import_jobs_db,
        'get_import_jobs',
        side_effect=RuntimeError('Firestore transport failure'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            imports_mod.get_import_jobs(uid='u1', limit=50)
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to retrieve import jobs'


def test_get_import_job_status_firestore_exception_handled():
    with patch.object(
        imports_mod.import_jobs_db,
        'get_import_job',
        side_effect=RuntimeError('Database read error'),
    ):
        with pytest.raises(HTTPException) as exc_info:
            imports_mod.get_import_job_status(job_id='job-123', uid='u1')
        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == 'Failed to retrieve import job status'


def test_cancel_import_job_update_exception_handled():
    mock_job = {'id': 'job-123', 'uid': 'u1', 'status': 'pending'}
    with patch.object(imports_mod.import_jobs_db, 'get_import_job', return_value=mock_job):
        with patch.object(
            imports_mod.import_jobs_db,
            'update_import_job',
            side_effect=RuntimeError('Database write error'),
        ):
            with pytest.raises(HTTPException) as exc_info:
                imports_mod.cancel_import_job(job_id='job-123', uid='u1')
            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == 'Failed to cancel import job'


def test_delete_import_job_exception_handled():
    mock_job = {'id': 'job-123', 'uid': 'u1', 'status': 'completed'}
    with patch.object(imports_mod.import_jobs_db, 'get_import_job', return_value=mock_job):
        with patch.object(
            imports_mod.import_jobs_db,
            'delete_import_job',
            side_effect=RuntimeError('Database delete error'),
        ):
            with pytest.raises(HTTPException) as exc_info:
                imports_mod.delete_import_job(job_id='job-123', uid='u1')
            assert exc_info.value.status_code == 500
            assert exc_info.value.detail == 'Failed to delete import job'
