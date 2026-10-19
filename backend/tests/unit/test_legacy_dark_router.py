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


def test_v1_sync_local_files_is_gone():
    module, saved, jobs, BytesIO = _router()
    try:
        response = module.sync_local_files(uid='test-uid')
        assert response.status_code == 410
        assert json.loads(response.body)['code'] == 'sync_v1_retired'
        assert response.headers['deprecation'] == 'true'
    finally:
        _restore(saved)
