from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, UploadFile

from database import import_jobs as import_jobs_db
from routers.imports import _sanitize_upload_filename, _validate_job_id


def test_sanitize_upload_filename_clean_basename():
    assert _sanitize_upload_filename('my_export.zip') == 'my_export.zip'
    assert _sanitize_upload_filename('archive-2026.06.19.zip') == 'archive-2026.06.19.zip'


def test_sanitize_upload_filename_neutralizes_path_traversal():
    assert _sanitize_upload_filename('../../../../etc/passwd.zip') == 'passwd.zip'
    assert _sanitize_upload_filename('..\\..\\..\\windows\\system32\\calc.zip') == 'calc.zip'
    assert _sanitize_upload_filename('/var/log/syslog.zip') == 'syslog.zip'


def test_sanitize_upload_filename_neutralizes_special_characters():
    assert _sanitize_upload_filename('test;rm -rf;.zip') == 'test_rm_-rf_.zip'
    assert _sanitize_upload_filename('test`id`.zip') == 'test_id_.zip'
    assert _sanitize_upload_filename('test$(whoami).zip') == 'test__whoami_.zip'


def test_sanitize_upload_filename_fallback_on_dangerous_names():
    assert _sanitize_upload_filename('.zip') == 'upload.zip'
    assert _sanitize_upload_filename('..zip') == 'upload.zip'
    assert _sanitize_upload_filename('.hidden.zip') == 'upload.zip'
    assert _sanitize_upload_filename('') == 'upload.zip'


def test_validate_job_id_accepts_valid_ids():
    _validate_job_id('job_12345')
    _validate_job_id('cfi_reconciled_abc-123')
    _validate_job_id('01J2K3L4M5N6P7Q8R9S0T1U2V3')


@pytest.mark.parametrize('bad_id', ['', '   ', 'job/123', 'job\\123', '../job', 'job..', None, 'a' * 129])
def test_validate_job_id_rejects_invalid_ids(bad_id):
    with pytest.raises(HTTPException) as exc_info:
        _validate_job_id(bad_id)  # type: ignore[arg-type]
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'Invalid job ID format'


def test_database_import_jobs_id_validation():
    # get_import_job returns None on invalid ID
    assert import_jobs_db.get_import_job('bad/id') is None
    assert import_jobs_db.get_import_job('') is None

    # update_import_job raises ValueError on invalid ID
    with pytest.raises(ValueError, match='Invalid job ID format'):
        import_jobs_db.update_import_job('bad/id', {'status': 'failed'})

    # delete_import_job raises ValueError on invalid ID
    with pytest.raises(ValueError, match='Invalid job ID format'):
        import_jobs_db.delete_import_job('bad/id')

    # get_import_jobs returns [] on empty uid
    assert import_jobs_db.get_import_jobs('') == []


def test_database_import_jobs_limit_clamping():
    fake_stream = MagicMock(return_value=[])
    fake_query = MagicMock()
    fake_query.where.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.stream = fake_stream

    fake_db = MagicMock()
    fake_db.collection.return_value = fake_query

    with patch('database.import_jobs.db', fake_db):
        import_jobs_db.get_import_jobs('test_uid', limit=5000)
        fake_query.limit.assert_called_with(1000)

        import_jobs_db.get_import_jobs('test_uid', limit=-10)
        fake_query.limit.assert_called_with(1)


@pytest.mark.asyncio
async def test_import_limitless_data_rejects_non_zip():
    from routers.imports import import_limitless_data

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = 'export.tar.gz'

    with pytest.raises(HTTPException) as exc_info:
        await import_limitless_data(file=mock_file, uid='test_uid')
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == 'File must be a ZIP archive'


@pytest.mark.asyncio
async def test_import_limitless_data_shields_storage_exceptions():
    from routers.imports import import_limitless_data

    mock_file = MagicMock(spec=UploadFile)
    mock_file.filename = 'export.zip'
    mock_file.read = AsyncMock(return_value=b'PK\x03\x04')

    with patch('routers.imports.run_blocking') as mock_run_blocking, patch('os.makedirs'):
        mock_job = MagicMock()
        mock_job.id = 'job_999'

        # First call is create_import_job, second is open (fails)
        mock_run_blocking.side_effect = [
            mock_job,
            PermissionError('/var/protected/secret_path: access denied'),
            None,  # update_import_job
        ]

        with pytest.raises(HTTPException) as exc_info:
            await import_limitless_data(file=mock_file, uid='test_uid')

        assert exc_info.value.status_code == 500
        # Assert raw path/traceback is NOT leaked to response detail
        assert 'secret_path' not in exc_info.value.detail
        assert exc_info.value.detail == 'Failed to save uploaded file. Please try again.'
