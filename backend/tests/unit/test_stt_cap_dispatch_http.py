"""Actual sync HTTP routing with local fake persistence/provider boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from routers import sync as router
from utils.sync.lanes import SyncLane


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'true')
    monkeypatch.setattr(router, 'get_sync_ledger_fence_mode', lambda: router.SyncLedgerFenceMode.ACTIVE)
    monkeypatch.setattr(
        router,
        'classify_sync_lane',
        lambda *a, **kw: SimpleNamespace(
            lane=SyncLane.FRESH,
            trust=SimpleNamespace(value='untrusted'),
            maximum_age_seconds=0,
            reason='synthetic',
            automatic_recovery_allowed=True,
        ),
    )
    monkeypatch.setattr(router, 'get_hard_restriction_status', lambda _: (False, None))
    monkeypatch.setattr(router, 'is_daily_audio_ceiling_exceeded', lambda _: False)
    monkeypatch.setattr(router, 'has_transcription_credits', lambda _: False)
    monkeypatch.setattr(
        router, 'resolve_transcription_allowance', lambda _: SimpleNamespace(reason='plan_allowance_exhausted')
    )
    monkeypatch.setattr(router, 'retrieve_file_paths', lambda *_: ['synthetic.bin'])
    monkeypatch.setattr(router, 'archive_mobile_batch_raw_files', lambda *_: [])
    monkeypatch.setattr(router, 'decode_files_to_wav', lambda _: ['1792152000.wav'])
    monkeypatch.setattr(router, '_cleanup_files', Mock())

    async def held(*args, **kwargs):
        kwargs['admission']['reason'] = router.resolve_transcription_allowance('synthetic').reason
        return True

    monkeypatch.setattr(router, 'hold_capture_if_exhausted', AsyncMock(side_effect=held))
    monkeypatch.setattr(router, 'retrieve_vad_segments', Mock(side_effect=AssertionError('denied audio reached VAD')))
    app = FastAPI()
    app.include_router(router.router)
    app.dependency_overrides[router.auth.get_current_user_uid] = lambda: 'synthetic'
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def test_v2_typed_result_preserves_flag_off_wire_and_exposes_only_present_hold():
    from models.sync_job_status import SyncJobStatusResponse

    body = {'job_id': 'job', 'status': 'completed', 'result': {'new_memories': [], 'updated_memories': []}}
    result = SyncJobStatusResponse(**body).model_dump(exclude_none=True)['result']
    assert result == {
        'new_memories': [],
        'updated_memories': [],
        'failed_segments': 0,
        'total_segments': 0,
        'errors': [],
    }
    body['result']['held_audio'] = True
    assert SyncJobStatusResponse(**body).model_dump(exclude_none=True)['result']['held_audio'] is True
