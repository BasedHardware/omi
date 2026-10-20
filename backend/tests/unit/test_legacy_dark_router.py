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
    sys.modules.pop('utils.sync.pipeline', None)
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
async def test_dark_sweep_stops_claims_but_keeps_enrichment_repair(monkeypatch):
    from unittest.mock import MagicMock

    module, saved, jobs, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: DARK)
        module.uid_sequencer.sweep = MagicMock(return_value={'claimed': 1})
        from utils.sync import reprocess

        monkeypatch.setattr(reprocess, 'owns_runtime', lambda: True)
        repair = MagicMock(return_value={'repaired': 2, 'error': 0})
        monkeypatch.setattr(reprocess, 'sweep', repair)
        module.summary_repair_enabled = lambda: False
        response = await module.sweep_sync_backfill_sequencer(0)
        assert response.status_code == 200
        outcomes = json.loads(response.body)['outcomes']
        assert outcomes['legacy_dark'] == 1 and outcomes['reprocess_repaired'] == 2
        module.uid_sequencer.sweep.assert_not_called()
        repair.assert_called_once()
    finally:
        _restore(saved)


@pytest.mark.asyncio
async def test_dark_wake_does_not_kick(monkeypatch):
    from unittest.mock import AsyncMock, MagicMock

    module, saved, jobs, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: DARK)
        module.uid_sequencer.kick = MagicMock()
        request = MagicMock()
        request.json = AsyncMock(return_value={'uid': 'test-uid'})
        response = await module.wake_sync_backfill_uid(request, 0)
        assert response.status_code == 200
        assert json.loads(response.body)['status'] == 'legacy_dark'
        module.uid_sequencer.kick.assert_not_called()
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


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [DRAINING, DARK])
async def test_dark_direct_backfill_never_runs_beside_a_live_sequencer_owner(monkeypatch, mode):
    """M1 review L10-1: no second transcriber for a uid whose sequencer owner is live."""
    from unittest.mock import AsyncMock, MagicMock

    module, saved, jobs, BytesIO = _router()
    try:
        monkeypatch.setattr(legacy_dark, 'current_mode', lambda: mode)
        request = MagicMock()
        request.json = AsyncMock(return_value={'uid': 'test-uid', 'job_id': 'job-1', 'lane': 'backfill'})
        module.uid_sequencer.enabled = MagicMock(return_value=True)
        module.uid_sequencer.production_stage = MagicMock(return_value=True)
        module.uid_sequencer.foreign_delivery = MagicMock(return_value=False)
        module.sync_backfill_sequencer.is_registered = MagicMock(return_value=False)
        module.sync_backfill_sequencer.get_owner = MagicMock(return_value={'active_job_id': 'sequenced-job'})
        module.sync_backfill_sequencer.register_job = MagicMock()
        module._run_sync_job_body = AsyncMock(
            return_value=module.JSONResponse(status_code=200, content={'status': 'done'})
        )

        locked = await module.run_sync_job(request, task_retry_count=0)
        assert locked.status_code == 409
        assert json.loads(locked.body) == {'status': 'locked', 'reason': 'sequencer_owner_active'}
        module._run_sync_job_body.assert_not_awaited()

        # The owner is idle: the direct delivery is the only transcriber.
        module.sync_backfill_sequencer.get_owner.return_value = {}
        assert (await module.run_sync_job(request, task_retry_count=0)).status_code == 200
        assert module._run_sync_job_body.await_count == 1

        # Already registered: draining's sweep dispatches it (ack); dark's sweep
        # no longer dispatches, so the delivery runs it.
        module.sync_backfill_sequencer.is_registered.return_value = True
        registered = await module.run_sync_job(request, task_retry_count=0)
        if mode is DRAINING:
            assert json.loads(registered.body) == {'status': 'sequenced_legacy_job'}
            assert module._run_sync_job_body.await_count == 1
        else:
            assert registered.status_code == 200
            assert module._run_sync_job_body.await_count == 2
        module.sync_backfill_sequencer.register_job.assert_not_called()
    finally:
        _restore(saved)
