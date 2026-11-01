"""Actual sync HTTP routing with local fake persistence/provider boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from tests.unit.fixtures.cap_rollout import full_cap_dispatch_rollout  # noqa: F401

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


@pytest.mark.parametrize('unavailable', [False, True])
def test_ladder_denied_upload_reaches_custody_without_402(client, monkeypatch, unavailable):
    from utils import ladder_v1

    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setenv('LADDER_V1_BUDGET_ENFORCEMENT_ENABLED', 'true')

    def snapshot(*args, **kwargs):
        if unavailable:
            raise RuntimeError('synthetic ledger read failure')
        return {'budget_percent': 100, 'used_units': 100, 'budget_units': 100}

    monkeypatch.setattr(ladder_v1, 'usage_snapshot', snapshot)
    reject = Mock(side_effect=AssertionError('upload must hold instead of raising 402'))
    monkeypatch.setattr(ladder_v1, 'enforce_budget', reject)
    monkeypatch.setattr(
        router,
        'resolve_transcription_allowance',
        lambda _: SimpleNamespace(reason='allowance_unavailable' if unavailable else 'usage_budget_exhausted'),
    )
    # V2 acknowledges archived bytes/job custody; the real coordinator's
    # full-WAV hold before VAD is tested in test_sync_cap_coordinator.
    monkeypatch.setattr(router, 'is_cloud_tasks_dispatch_enabled', lambda: False)
    monkeypatch.setattr(router, 'has_byok_keys', lambda: False)
    from config.policy import BatchUnitPolicy

    monkeypatch.setattr(router, 'resolve_batch_policy', lambda _: BatchUnitPolicy())
    monkeypatch.setattr(router, '_retrieve_file_paths_v2', lambda *a: ['synthetic.bin'])
    monkeypatch.setattr(router, 'compute_sync_content_id', lambda *a: 'held-content')
    monkeypatch.setattr(router, 'create_sync_job', Mock())
    monkeypatch.setattr(router, 'claim_sync_content', lambda *a: {'outcome': 'held', 'result': {'held_audio': True}})
    monkeypatch.setattr(router, 'mark_job_completed', Mock())
    response = client.post('/v2/sync-local-files', files={'files': ('omi_1792152000.bin', b'synthetic')})
    assert response.status_code == 202, response.text
    assert response.json()['status'] == 'completed'
    assert router.mark_job_completed.call_args.args[1]['held_audio'] is True
    reject.assert_not_called()
