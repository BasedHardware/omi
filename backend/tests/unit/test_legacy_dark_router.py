"""Legacy dark (contract (h)) wired into routers/sync.py, through the shared fast-path harness.

Each test reloads routers.sync in the harness, so this file sits in the
fast-unit duration allowlist next to test_sync_cloud_tasks.py.
"""

import json
import sys

import pytest

from utils.sync import legacy_dark
from utils.sync.legacy_dark import LegacySyncMode

DRAINING, DARK, ON = LegacySyncMode.DRAINING, LegacySyncMode.DARK, LegacySyncMode.ON
COMPLETED = {'failed_segments': 0, 'total_segments': 3, 'errors': [], 'outcome': 'success'}


def _router():
    from tests.unit.test_sync_cloud_tasks import _load_sync_router_for_fast_path

    module, saved, jobs, BytesIO, fallback_calls, _ = _load_sync_router_for_fast_path()
    return module, saved, jobs, BytesIO


def _restore(saved):
    sys.modules.pop('routers.sync', None)
    sys.modules.pop('utils.sync.legacy_segment_core', None)
    for name, original in saved.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


async def _upload(module, BytesIO):
    from starlette.datastructures import UploadFile

    upload = UploadFile(filename='omi_1792152000.bin', file=BytesIO(b'\x00' * 10))
    return await module.sync_local_files_v2(files=[upload], uid='test-uid')


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [DRAINING, DARK])
async def test_router_never_creates_a_legacy_job_outside_on(monkeypatch, mode):
    from unittest.mock import MagicMock

    module, saved, jobs, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: mode)
        monkeypatch.setattr(legacy_dark, 'read_ledger_row', lambda uid, content_id: None)
        module.create_sync_job = MagicMock()
        response = await _upload(module, BytesIO)
        assert response.status_code == 409
        assert json.loads(response.body)['code'] == 'sync_content_retry_later'
        module.create_sync_job.assert_not_called()
    finally:
        _restore(saved)


@pytest.mark.asyncio
async def test_router_acknowledges_completed_legacy_content_in_dark(monkeypatch):
    from unittest.mock import MagicMock

    module, saved, jobs, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: DARK)
        row = {'status': 'completed', 'result': COMPLETED, 'job_id': 'legacy-job'}
        monkeypatch.setattr(legacy_dark, 'read_ledger_row', lambda uid, content_id: row)
        module.create_sync_job = MagicMock()
        response = await _upload(module, BytesIO)
        assert response.status_code == 202
        assert json.loads(response.body)['status'] == 'completed'
        module.create_sync_job.assert_not_called()
    finally:
        _restore(saved)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [DRAINING, DARK])
async def test_router_acknowledges_a_legacy_final_pass_owner_without_a_ledger_row(monkeypatch, mode):
    """M3 review: a conversation owned by legacy_final_pass_v1 whose re-home is held (the route
    stays LEGACY) gets batch intake's ACK (the shipped in-progress 409 that follows the owner),
    not the admission-refused backstop, and no legacy job."""
    from unittest.mock import AsyncMock, MagicMock

    from utils.batch_pipeline.live_upload import RecordUploadRoute

    module, saved, jobs, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: mode)
        monkeypatch.setattr(legacy_dark, 'read_ledger_row', lambda uid, content_id: None)
        module.registered_record_response = AsyncMock(return_value=RecordUploadRoute.LEGACY)
        module.create_sync_job = MagicMock()
        response = await _upload(module, BytesIO)
        assert response.status_code == 409
        assert json.loads(response.body)['code'] == 'sync_content_in_progress'
        module.create_sync_job.assert_not_called()
    finally:
        _restore(saved)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [DRAINING, DARK])
async def test_router_admits_a_rehomed_final_pass_owner_to_batch(monkeypatch, mode):
    """Lead ruling b209a5: the route re-homes a legacy_final_pass_v1 owner to batch outside ``on``
    (it receives the mode the router read); the upload then goes to batch intake with batch
    enabled, past any owner-load narrowing, and never to the fence or a legacy job."""
    from unittest.mock import AsyncMock, MagicMock

    from utils.batch_pipeline.live_upload import RecordUploadRoute

    module, saved, jobs, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: mode)
        monkeypatch.setattr(legacy_dark, 'read_ledger_row', MagicMock(side_effect=AssertionError('fence ran')))
        module.registered_record_response = AsyncMock(return_value=RecordUploadRoute.BATCH)
        module.accept_batch_upload = AsyncMock(
            return_value=module.JSONResponse(status_code=202, content={'job_id': 'bp_1', 'status': 'queued'})
        )
        module.create_sync_job = MagicMock()
        response = await _upload(module, BytesIO)
        assert response.status_code == 202
        assert module.registered_record_response.await_args.kwargs['legacy_mode'] is mode
        module.accept_batch_upload.assert_awaited_once()
        assert module.accept_batch_upload.await_args.kwargs['policy'].batch_enabled is True
        module.create_sync_job.assert_not_called()
    finally:
        _restore(saved)


@pytest.mark.asyncio
async def test_router_reads_the_legacy_mode_off_the_event_loop(monkeypatch):
    """M3 review: current_mode only waits for a cold first ramp read off the loop, so the
    router reads it through run_blocking; on the loop a fresh process serves the 'on' default."""
    module, saved, jobs, BytesIO = _router()
    offloaded = []
    passthrough = module.run_blocking

    async def recording_run_blocking(executor, fn, *args, **kwargs):
        offloaded.append(fn)
        return await passthrough(executor, fn, *args, **kwargs)

    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: DARK)
        monkeypatch.setattr(legacy_dark, 'read_ledger_row', lambda uid, content_id: None)
        module.run_blocking = recording_run_blocking
        response = await _upload(module, BytesIO)
        assert response.status_code == 409
        assert legacy_dark.current_mode in offloaded
    finally:
        _restore(saved)


@pytest.mark.asyncio
async def test_router_never_admits_legacy_even_when_mode_is_on(monkeypatch):
    module, saved, jobs, BytesIO = _router()
    try:
        reads = []
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: reads.append(ON) or ON)
        counter = legacy_dark.OMI_LEGACY_SYNC_ADMISSIONS_TOTAL.labels(reason='batch_not_enabled')
        before = counter._value.get()
        response = await _upload(module, BytesIO)
        assert response.status_code == 409
        assert counter._value.get() == before
        assert len(reads) == 1  # a young mode read is not taken again
    finally:
        _restore(saved)


@pytest.mark.asyncio
async def test_router_never_admits_legacy_after_a_stale_on_read(monkeypatch):
    """Even a stale ON read cannot create a job after C9 permanently retires legacy admission."""
    from unittest.mock import MagicMock

    module, saved, jobs, BytesIO = _router()
    try:
        reads = iter([ON, DRAINING])
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: next(reads))
        monkeypatch.setattr(legacy_dark, 'ADMISSION_REVALIDATE_SECONDS', -1)
        monkeypatch.setattr(legacy_dark, 'read_ledger_row', lambda uid, content_id: None)
        module.create_sync_job = MagicMock()
        response = await _upload(module, BytesIO)
        assert response.status_code == 409
        module.create_sync_job.assert_not_called()
    finally:
        _restore(saved)


def test_v1_sync_local_files_is_gone():
    module, saved, jobs, BytesIO = _router()
    try:
        response = module.sync_local_files(uid='test-uid')
        assert response.status_code == 410
        assert json.loads(response.body)['code'] == 'sync_v1_retired'
        assert response.headers['deprecation'] == 'true'
    finally:
        _restore(saved)
