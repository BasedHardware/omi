"""Real custody metadata transactions around accepted/refused storage requests."""

from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from starlette.responses import JSONResponse

from database import record_custody_append as database
from database import record_token_lease_metrics as metrics
from utils.sync import record_token_lease as request
from tests.unit.test_record_token_lease import PATH, ROW, NOW
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore


@pytest.mark.parametrize('status,durable', [(202, True), (409, True), (503, True), (202, False)])
@pytest.mark.parametrize('mode', ['off', 'shadow', 'serve'])
async def test_response_storage_and_mode_matrix(monkeypatch, status, durable, mode):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', mode)
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setattr(database.time, 'time', lambda: NOW)
    client = StrictFirestore({PATH: ROW, ('users', 'synthetic'): {'private_cloud_sync_enabled': True}})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    counter = metrics.LATE_APPEND._value.get()
    before = deepcopy(client.rows)

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'request')
        row = client.rows[PATH]
        assert row['record_upload_revision'] == 7
        assert ('custody:request' in row['record_upload_sessions']) is (mode == 'serve')
        if durable:
            request.stored(['local'], ['durable-archive'])
        return JSONResponse(status_code=status, content={'status': 'synthetic'})

    if status == 202 and not durable and mode == 'serve':
        with pytest.raises(HTTPException) as failure:
            await upload()
        assert failure.value.status_code == 503
    else:
        assert (await upload()).status_code == status
    accepted = status == 202 and durable
    assert 'custody:request' not in client.rows[PATH]['record_upload_sessions']
    assert client.rows[PATH]['record_upload_revision'] == 7 + (mode == 'serve' and accepted)
    assert metrics.LATE_APPEND._value.get() == counter + (mode != 'off' and accepted)
    if mode != 'serve':
        assert client.rows == before
    assert request._upload.get() is None


async def test_memoized_wait_before_begin_has_zero_metadata_io(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    forbidden = Mock(side_effect=AssertionError('memoized retry performed metadata IO'))
    monkeypatch.setattr(database, 'get_firestore_client', forbidden)

    @request.custody_upload
    async def upload():
        # The endpoint returns its memoized response before begin_upload.
        return JSONResponse(status_code=503, content={'code': 'record_jobs_missing'})

    assert (await upload()).status_code == 503
    forbidden.assert_not_called()


async def test_storage_exception_clears_only_own_fence_without_revision_or_counter(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = StrictFirestore({PATH: ROW})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    before = deepcopy(client.rows)
    counter = metrics.LATE_APPEND._value.get()

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'failed')
        raise OSError('synthetic archive failure')

    with pytest.raises(OSError):
        await upload()
    assert client.rows == before
    assert metrics.LATE_APPEND._value.get() == counter


async def test_failed_job_202_is_a_refusal_without_bump_or_late_count(monkeypatch):
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE', 'serve')
    monkeypatch.setenv('RECORD_TOKEN_LEASE_MODE_SERVE_PERCENT', '100')
    client = StrictFirestore({PATH: ROW})
    monkeypatch.setattr(database, 'get_firestore_client', lambda: client)
    before = deepcopy(client.rows)
    counter = metrics.LATE_APPEND._value.get()

    @request.custody_upload
    async def upload():
        await request.begin_upload('synthetic', 'record', 'capped')
        request.stored(['local'], ['archive'])
        return JSONResponse(status_code=202, content={'status': 'failed'})

    assert (await upload()).status_code == 202
    assert client.rows == before
    assert metrics.LATE_APPEND._value.get() == counter
