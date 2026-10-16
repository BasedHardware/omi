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


def test_exhausted_upload_acknowledges_only_after_durable_hold(client):
    response = client.post('/v1/sync-local-files', files={'files': ('omi_1792152000.bin', b'synthetic')})
    assert response.status_code == 200, response.text
    assert response.json() == {
        'new_memories': [],
        'updated_memories': [],
        'credits_exhausted': True,
        'held_audio': True,
        'held_files': 1,
    }
    router.hold_capture_if_exhausted.assert_called_once()
    router.retrieve_vad_segments.assert_not_called()


def test_failed_hold_is_not_reported_as_an_accepted_upload(client):
    router.hold_capture_if_exhausted.side_effect = RuntimeError('synthetic storage unavailable')
    response = client.post('/v1/sync-local-files', files={'files': ('omi_1792152000.bin', b'synthetic')})
    assert response.status_code == 500
    router.retrieve_vad_segments.assert_not_called()


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


def test_flag_off_http_result_retains_main_shape_without_hold_dispatch(client, monkeypatch):
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')
    monkeypatch.setattr(router, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(router, 'retrieve_vad_segments', Mock())
    monkeypatch.setattr(router.users_db, 'get_user_transcription_preferences', Mock(return_value={}))
    monkeypatch.setattr(router.users_db, 'get_user_private_cloud_sync_enabled', Mock(return_value=False))
    monkeypatch.setattr(router, 'build_person_embeddings_cache', Mock(return_value={}))
    monkeypatch.setattr(router, '_reprocess_merged_conversations', Mock())
    monkeypatch.setattr(router, 'schedule_person_voice_learning_retries', Mock())
    response = client.post('/v1/sync-local-files', files={'files': ('omi_1792152000.bin', b'synthetic')})
    assert response.status_code == 200, response.text
    assert response.content == b'{"new_memories":[],"updated_memories":[]}'
    router.hold_capture_if_exhausted.assert_not_called()


@pytest.mark.parametrize('accepted', [False, True])
def test_late_v1_hold_is_reported_and_only_processed_speech_is_metered(client, monkeypatch, accepted):
    monkeypatch.setattr(router, 'FAIR_USE_ENABLED', False)
    router.hold_capture_if_exhausted.side_effect = None
    router.hold_capture_if_exhausted.return_value = False
    paths = ['1792152000.wav', '1792152020.wav'] if accepted else ['1792152020.wav']
    monkeypatch.setattr(router, 'retrieve_vad_segments', lambda path, segments, errors, **kw: segments.update(paths))
    monkeypatch.setattr(router, 'get_wav_duration', lambda path: 20)
    monkeypatch.setattr(router.users_db, 'get_user_transcription_preferences', Mock(return_value={}))
    monkeypatch.setattr(router.users_db, 'get_user_private_cloud_sync_enabled', Mock(return_value=False))
    monkeypatch.setattr(router, 'build_person_embeddings_cache', Mock(return_value={}))
    monkeypatch.setattr(router, '_reprocess_merged_conversations', Mock())
    monkeypatch.setattr(router, 'schedule_person_voice_learning_retries', Mock())
    usage = Mock()
    monkeypatch.setattr(router, 'record_usage', usage)

    def process(path, uid, response, *args, **kwargs):
        if path == '1792152000.wav':
            response['new_memories'].add('accepted')
            return True
        response['_cap_holds'] = {'late': {'id': 'late', 'seconds': 20, 'reason': 'plan_allowance_exhausted'}}
        return False

    monkeypatch.setattr(router, 'process_segment', process)
    response = client.post('/v1/sync-local-files', files={'files': ('omi_1792152000.bin', b'synthetic')})
    assert response.status_code == 200, response.text
    assert response.json() == {
        'new_memories': ['accepted'] if accepted else [],
        'updated_memories': [],
        'held_audio': True,
        'credits_exhausted': True,
        'held_segments': 1,
    }
    if accepted:
        assert usage.call_args.kwargs == {'transcription_seconds': 20, 'speech_seconds': 20}
    else:
        usage.assert_not_called()


@pytest.mark.parametrize('reason', ['allowance_unavailable', 'launch_config_missing', 'launch_config_invalid'])
def test_transient_policy_hold_does_not_claim_credits_exhausted(client, monkeypatch, reason):
    monkeypatch.setattr(router, 'resolve_transcription_allowance', lambda _: SimpleNamespace(reason=reason))
    response = client.post('/v1/sync-local-files', files={'files': ('omi_1792152000.bin', b'synthetic')})
    assert response.status_code == 200, response.text
    assert response.json()['held_audio'] is True
    assert response.json()['credits_exhausted'] is False
    router.retrieve_vad_segments.assert_not_called()
