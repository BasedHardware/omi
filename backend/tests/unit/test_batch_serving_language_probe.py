"""Real serving intake/resolver, synthetic privacy/funding/model/transport leaves."""

from types import SimpleNamespace
from unittest.mock import Mock, MagicMock

import pytest

from config.policy import BatchUnitPolicy
from database.batch_pipeline_privacy import BatchPrivacyBlocked
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils import funded_processing, stt_cap_dispatch
from utils.batch_pipeline import intake
from utils.batch_pipeline.artifacts import ProtectionContext
from utils.batch_pipeline.audio import audio_unit, read_context
from utils.stt import batch_language
from utils.sync.legacy_dark import LegacySyncMode


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setenv('BATCH_ADMISSION_LANGUAGE_EXCLUSION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_LANGUAGE_INHERITANCE_ENABLED', 'true')
    monkeypatch.setenv('STT_PRERECORDED_LANGUAGE_GUARD_ENABLED', 'true')
    monkeypatch.setenv('MODULATE_API_KEY', 'synthetic-never-sent')
    source = tmp_path / 'retained-wal.bin'
    source.write_bytes(b'synthetic caller custody')
    state = SimpleNamespace(
        revoked=False, language='multi', units=1, staged=[], staged_contexts=[], admissions=[], authorizations=[]
    )

    def authorize(store, item, *, snapshots):
        state.authorizations.append(item)
        if getattr(state, 'fail_authorize', False) and len(state.authorizations) > 1:
            raise RuntimeError('synthetic privacy read unavailable')
        if state.revoked:
            raise BatchPrivacyBlocked('privacy_generation_changed')
        snapshots['user'] = {'language': state.language, 'transcription_preferences': {}}
        snapshots['conversations'] = {
            'synthetic-conversation': {'language': state.language, 'record_lane_owner': 'batch_sync_v1'}
        }
        return ProtectionContext('standard', 0)

    def units(*args, **kwargs):
        for n in range(state.units):
            yield audio_unit(100 + n, b'\x01\x00' * 16000)

    def stage(item, body):
        state.staged.append(item)
        state.staged_contexts.append(read_context(body))
        if getattr(state, 'after_stage', None):
            state.after_stage()
        return 'synthetic://retained-stage'

    def admit(*args, **kwargs):
        state.admissions.append(args)
        return {'outcome': 'batch', 'job_id': 'bp_synthetic'}

    store = MemoryStore()
    store.namespace = 'batch_pipeline_dev'
    monkeypatch.setattr(intake, 'FirestoreStore', lambda _: store)
    monkeypatch.setattr(intake, 'current_stage', lambda: 'dev')
    monkeypatch.setattr(intake.legacy_dark, 'current_mode', lambda: LegacySyncMode.ON)
    monkeypatch.setattr(intake, 'batch_artifact_authorize', authorize)
    monkeypatch.setattr(intake, 'decode_units', units)
    monkeypatch.setattr(intake, 'artifacts_for', lambda _: SimpleNamespace(stage_audio=stage))
    monkeypatch.setattr(intake, 'admit', admit)
    monkeypatch.setattr(
        intake,
        'durable_status',
        lambda *a: {
            'job_id': 'bp_synthetic',
            'status': 'queued',
            'total_files': 1,
            'total_segments': 1,
            'poll_after_ms': 3000,
            'lane': 'fresh',
        },
    )
    state.consent = Mock(return_value=True)
    state.funding = Mock(return_value=True)
    monkeypatch.setattr(funded_processing, 'consent_allows', state.consent)
    monkeypatch.setattr(stt_cap_dispatch, 'sync_allowed', state.funding)
    monkeypatch.setattr(batch_language.language_gate, 'enforced_for', lambda *_: False)
    monkeypatch.setattr(batch_language, 'language_gate_shadow_enabled', lambda: False)
    state.model = Mock(return_value=None)
    monkeypatch.setattr(batch_language.language_gate, 'self_detect', state.model)
    monkeypatch.setattr(batch_language, 'breaker_allows', lambda *_: True)
    monkeypatch.setattr(batch_language, 'record_breaker_success', lambda *_: None)
    monkeypatch.setattr(batch_language, 'record_vendor_burn', lambda *_: None)
    response = Mock()
    response.json.return_value = {'predicted_language_code': 'en', 'confidence': 0.99}
    client = MagicMock()
    client.__enter__.return_value = client
    client.post.return_value = response
    monkeypatch.setattr(batch_language.httpx, 'Client', Mock(return_value=client))
    state.vendor, state.source = client.post, source

    async def upload():
        result = await intake.accept_upload(
            uid='synthetic-owner',
            job_id='synthetic',
            content_id='synthetic',
            paths=[str(source)],
            lane='fresh',
            recording_age_seconds=0,
            source='omi',
            should_lock=False,
            conversation_id='synthetic-conversation',
            client_device_id=None,
            client_platform='ios',
            policy=BatchUnitPolicy(batch_enabled=True, live_record_enabled=False),
        )
        assert source.read_bytes() == b'synthetic caller custody'
        return result

    state.upload = upload
    return state


@pytest.mark.parametrize('execution_enabled', [False, True])
@pytest.mark.parametrize('self_probe', [False, True])
async def test_capped_upload_is_accepted_without_probes_in_both_execution_cohorts(
    world, monkeypatch, execution_enabled, self_probe
):
    from config import stt_cap_dispatch as flags

    monkeypatch.setattr(flags, 'execution_admission_enabled', lambda *_: execution_enabled)
    monkeypatch.setattr(batch_language, 'language_gate_shadow_enabled', lambda: self_probe)
    world.funding.return_value = False
    response = await world.upload()
    assert response.status_code == 202
    assert len(world.authorizations) == 2
    assert world.consent.call_count == 2 and world.funding.call_count == 1
    assert not world.model.called and not world.vendor.called
    assert len(world.staged) == len(world.admissions) == 1
    assert world.staged_contexts[0]['stt_language'] == 'und'
    assert world.staged_contexts[0]['stt_language_evidence'] == 'unavailable'


async def test_second_probe_funding_denial_accepts_unknown_unit(world, monkeypatch):
    monkeypatch.setattr(batch_language, 'language_gate_shadow_enabled', lambda: True)
    world.funding.side_effect = [True, False]
    response = await world.upload()
    assert response.status_code == 202
    assert len(world.authorizations) == 3
    assert world.model.call_count == 1 and not world.vendor.called
    assert len(world.staged) == len(world.admissions) == 1
    assert world.staged_contexts[0]['stt_language'] == 'und'


async def test_funding_read_unavailable_skips_probe_without_stranding_upload(world):
    world.funding.side_effect = RuntimeError('synthetic billing read unavailable')
    response = await world.upload()
    assert response.status_code == 202
    assert not world.model.called and not world.vendor.called
    assert len(world.staged) == len(world.admissions) == 1
    assert world.staged_contexts[0]['stt_language'] == 'und'


async def test_consent_reset_during_funding_check_still_refuses(world):
    def reset(*args, **kwargs):
        world.consent.return_value = False
        return False

    world.funding.side_effect = reset
    response = await world.upload()
    assert response.status_code == 503
    assert world.consent.call_count == 2
    assert not world.model.called and not world.vendor.called
    assert not world.staged and not world.admissions


async def test_capped_first_unit_does_not_bypass_next_unit_privacy(world):
    world.units = 2
    world.funding.return_value = False

    def revoke():
        world.revoked = True

    world.after_stage = revoke
    response = await world.upload()
    assert response.status_code == 409
    assert len(world.staged) == 1 and not world.admissions
    assert world.staged_contexts[0]['stt_language'] == 'und'
    assert not world.model.called and not world.vendor.called


async def test_consent_revocation_between_self_and_vendor_is_rechecked(world, monkeypatch):
    monkeypatch.setattr(batch_language, 'language_gate_shadow_enabled', lambda: True)
    world.consent.side_effect = [True, False]
    response = await world.upload()
    assert response.status_code == 503
    assert len(world.authorizations) == 3
    assert world.model.call_count == 1 and not world.vendor.called
    assert world.funding.call_count == 1
    assert not world.staged and not world.admissions


async def test_privacy_revocation_between_self_and_vendor_cannot_be_swallowed(world, monkeypatch):
    monkeypatch.setattr(batch_language, 'language_gate_shadow_enabled', lambda: True)

    def revoke(*args, **kwargs):
        world.revoked = True
        return None

    world.model.side_effect = revoke
    response = await world.upload()
    assert response.status_code == 409
    assert len(world.authorizations) == 3
    assert world.model.call_count == 1 and not world.vendor.called
    assert not world.staged and not world.admissions


async def test_second_unit_reauthorizes_and_retains_first_stage_without_success_ack(world):
    world.units = 2

    def revoke():
        world.revoked = True

    world.after_stage = revoke
    response = await world.upload()
    assert response.status_code == 409
    assert len(world.authorizations) == 3
    assert world.vendor.call_count == 1 and len(world.staged) == 1
    assert not world.admissions
    assert world.authorizations[1].privacy_generation == 0
    assert world.authorizations[1].segment_id != world.authorizations[2].segment_id


async def test_guard_read_error_fails_closed_with_retry_and_retained_source(world):
    world.consent.side_effect = RuntimeError('synthetic unavailable')
    response = await world.upload()
    assert response.status_code == 503
    assert not world.model.called and not world.vendor.called
    assert not world.staged and not world.admissions


async def test_privacy_read_unavailable_fails_closed_before_model(world):
    world.fail_authorize = True
    response = await world.upload()
    assert response.status_code == 503
    assert not world.consent.called and not world.funding.called
    assert not world.model.called and not world.vendor.called
    assert not world.staged and not world.admissions


@pytest.mark.parametrize('execution_enabled', [False, True])
async def test_consent_denial_is_independent_of_execution_cohort(world, monkeypatch, execution_enabled):
    from config import stt_cap_dispatch as flags

    monkeypatch.setattr(flags, 'execution_admission_enabled', lambda *_: execution_enabled)
    world.consent.return_value = False
    response = await world.upload()
    assert response.status_code == 503
    assert world.consent.call_count == 1 and not world.funding.called
    assert not world.model.called and not world.vendor.called
    assert not world.staged and not world.admissions


async def test_funded_unknown_language_preserves_normal_admission(world):
    response = await world.upload()
    assert response.status_code == 202
    assert world.vendor.call_count == 1
    assert len(world.staged) == len(world.admissions) == 1


async def test_declared_language_needs_no_probe_or_probe_funding(world):
    world.language = 'en'
    world.consent.return_value = False
    world.funding.return_value = False
    response = await world.upload()
    assert response.status_code == 202
    assert len(world.authorizations) == 1
    assert not world.consent.called and not world.funding.called
    assert not world.model.called and not world.vendor.called
