"""POST /v1/import/transcripts: queue a transcript-file import job.

The route only validates and stages the upload; parsing and conversation creation
run in the background worker (tests/unit/test_transcript_file_import.py).
"""

import asyncio
import io
import os
import threading

os.environ.setdefault("ENCRYPTION_SECRET", "omi_ZwB2ZNqB2HHpMK6wStk7sTpavJiPTFg7gXUHnc4tFABPU6pZ2c2DKgehtfgi4RZv")
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import UploadFile

from models.import_job import ImportJob, ImportJobStatus, ImportSourceType
from routers import imports as imports_mod

UID = "u1"


def _upload(name: str, data: bytes = b"1\n00:00:01,000 --> 00:00:02,000\nhello\n") -> UploadFile:
    return UploadFile(file=io.BytesIO(data), filename=name)


def _call(upload: UploadFile, **kwargs):
    params = {'language': 'en', 'tz': 'UTC', 'origin': 'other', **kwargs}
    return asyncio.run(imports_mod.import_transcript_files(file=upload, uid=UID, **params))


class _Worker:
    """Stands in for the background worker; records the queued call."""

    def __init__(self):
        self.called = threading.Event()
        self.args: tuple = ()
        self.kwargs: dict = {}

    def __call__(self, *args, **kwargs):
        self.args, self.kwargs = args, kwargs
        self.called.set()

    def wait(self):
        assert self.called.wait(timeout=5), 'the import was never queued'
        return self


@pytest.fixture
def staged(tmp_path, monkeypatch):
    monkeypatch.setattr(imports_mod, 'TEMP_DIR', str(tmp_path))
    job = ImportJob(id='job-9', uid=UID, status=ImportJobStatus.pending, source_type=ImportSourceType.transcript_files)
    create = MagicMock(return_value=job)
    worker = _Worker()
    with patch.object(imports_mod, 'create_transcript_import_job', create), patch.object(
        imports_mod, 'process_transcript_import', worker
    ):
        yield create, worker, tmp_path


@pytest.mark.parametrize('name', ['meeting.mp3', 'notes.docx', 'noextension', ''])
def test_unsupported_upload_is_rejected_before_a_job_exists(staged, name):
    create, worker, _ = staged

    with pytest.raises(HTTPException) as error:
        _call(_upload(name))

    assert error.value.status_code == 400
    assert '.zip, .srt, .vtt or .txt' in error.value.detail
    create.assert_not_called()
    assert not worker.called.is_set()


def test_unknown_origin_is_rejected(staged):
    create, worker, _ = staged

    with pytest.raises(HTTPException) as error:
        _call(_upload('call.srt'), origin='otterly')

    assert error.value.status_code == 400
    create.assert_not_called()


@pytest.mark.parametrize('name', ['call.SRT', 'export.zip', 'notes.txt', 'meeting.vtt'])
def test_supported_upload_is_staged_and_queued(staged, name):
    create, worker, tmp_path = staged
    data = b'transcript bytes'

    response = _call(_upload(name, data), language='es', tz='Europe/Madrid', origin='plaud')

    assert (response.job_id, response.status) == ('job-9', ImportJobStatus.pending)
    create.assert_called_once_with(UID)
    queued = worker.wait()
    job_id, uid, staged_path = queued.args
    assert (job_id, uid) == ('job-9', UID)
    assert open(staged_path, 'rb').read() == data
    assert os.path.dirname(staged_path) == str(tmp_path)
    assert queued.kwargs == {
        'original_filename': name,
        'language_code': 'es',
        'tz': 'Europe/Madrid',
        'origin': 'plaud',
    }


def test_path_components_in_the_filename_never_leave_the_temp_dir(staged):
    _, worker, tmp_path = staged

    _call(_upload('../../etc/evil.srt'))

    queued = worker.wait()
    assert os.path.dirname(os.path.abspath(queued.args[2])) == str(tmp_path)
    assert queued.kwargs['original_filename'] == 'evil.srt'


@pytest.mark.parametrize(
    ('name', 'staged_name'),
    [
        pytest.param('call.SRT', 'job-9.srt', id='upper-case-extension'),
        pytest.param('export.zip', 'job-9.zip', id='zip'),
        pytest.param('x' * 300 + '.vtt', 'job-9.vtt', id='name-over-filesystem-limit'),
    ],
)
def test_upload_is_staged_under_the_job_id_not_the_user_filename(staged, name, staged_name):
    """A user file name can exceed the file-system name limit; the job ID cannot."""
    _, worker, tmp_path = staged

    _call(_upload(name))

    queued = worker.wait()
    assert queued.args[2] == os.path.join(str(tmp_path), staged_name)
    assert queued.kwargs['original_filename'] == name


class _BrokenUpload(UploadFile):
    """Delivers one chunk, then the stream fails; a failed disk write takes the same path."""

    def __init__(self):
        super().__init__(file=io.BytesIO(), filename='call.srt')
        self.reads = 0

    async def read(self, size: int = -1) -> bytes:
        self.reads += 1
        if self.reads > 1:
            raise OSError('stream broke')
        return b'1\n00:00:01,000 --> 00:00:02,000\n'


def test_failed_staging_removes_the_partial_file_and_fails_the_job(staged):
    _, worker, tmp_path = staged

    with patch.object(imports_mod.import_jobs_db, 'update_import_job') as update, pytest.raises(HTTPException) as error:
        _call(_BrokenUpload())

    assert error.value.status_code == 500
    assert update.call_args.args[0] == 'job-9'
    assert update.call_args.args[1]['status'] == ImportJobStatus.failed.value
    assert os.listdir(tmp_path) == [], 'the partial upload is removed'
    assert not worker.called.is_set()


def test_job_is_failed_when_the_worker_cannot_be_queued(staged, monkeypatch):
    """A job that never reaches the worker must not sit in pending forever."""
    _, worker, tmp_path = staged
    queue = imports_mod.storage_executor.submit

    def submit(fn, *args, **kwargs):
        if fn is worker:
            raise RuntimeError('cannot schedule new futures after shutdown')
        return queue(fn, *args, **kwargs)

    monkeypatch.setattr(imports_mod.storage_executor, 'submit', submit)

    with patch.object(imports_mod.import_jobs_db, 'update_import_job') as update, pytest.raises(HTTPException) as error:
        _call(_upload('call.srt'))

    assert error.value.status_code == 503
    assert update.call_args.args[0] == 'job-9'
    assert update.call_args.args[1]['status'] == ImportJobStatus.failed.value
    assert os.listdir(tmp_path) == [], 'the staged upload is removed'


def _client(monkeypatch, enforce) -> TestClient:
    monkeypatch.setattr(imports_mod.auth, '_enforce_rate_limit', enforce)
    app = FastAPI()
    app.include_router(imports_mod.router)
    app.dependency_overrides[imports_mod.auth.get_current_user_uid] = lambda: UID
    return TestClient(app)


def _post(client: TestClient):
    return client.post(
        '/v1/import/transcripts', files={'file': ('call.srt', b'1\n00:00:01,000 --> 00:00:02,000\nhi\n')}
    )


def test_upload_is_rate_limited_per_user_like_other_uploads(staged, monkeypatch):
    create, worker, _ = staged
    checked = []

    def deny(key, policy_name, **_kwargs):
        checked.append((key, policy_name))
        raise HTTPException(status_code=429, detail='Rate limit exceeded. Try again in 60s.')

    response = _post(_client(monkeypatch, deny))

    assert response.status_code == 429
    assert checked == [(UID, 'file:upload')]
    create.assert_not_called()
    assert not worker.called.is_set()


def test_upload_within_the_rate_limit_is_queued(staged, monkeypatch):
    _, worker, _ = staged
    checked = []

    response = _post(_client(monkeypatch, lambda key, policy_name, **_kwargs: checked.append((key, policy_name))))

    assert response.status_code == 200
    assert response.json()['job_id'] == 'job-9'
    assert checked == [(UID, 'file:upload')]
    worker.wait()


def _stored_job(job_id: str, **fields):
    return {'id': job_id, 'uid': UID, 'status': 'completed', 'created_at': '2026-10-04T00:00:00', **fields}


def test_job_list_reports_each_jobs_source_so_clients_label_it():
    jobs = [
        _stored_job('a', source_type='transcript_files'),
        _stored_job('b', source_type='limitless'),
        _stored_job('c'),
        _stored_job('d', source_type='unknown-importer'),
    ]
    with patch.object(imports_mod.import_jobs_db, 'get_import_jobs', return_value=jobs):
        result = imports_mod.get_import_jobs(uid=UID, limit=10)

    assert [job.source_type for job in result] == [
        ImportSourceType.transcript_files,
        ImportSourceType.limitless,
        None,
        None,
    ]


def test_job_status_reports_its_source():
    with patch.object(
        imports_mod.import_jobs_db, 'get_import_job', return_value=_stored_job('a', source_type='transcript_files')
    ):
        result = imports_mod.get_import_job_status('a', uid=UID)

    assert result.source_type == ImportSourceType.transcript_files
