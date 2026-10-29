"""Batch cohort alignment, durable coverage and actual vendor-write denominators."""

import asyncio
import json

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import batch_pipeline, batch_live_preview, summary_guarantee
from routers.listen import batch_preview, demand_routing
from utils.observability import demand_cohort as telemetry
from utils.stt import streaming
from utils.stt.soniox import SafeSonioxSocket
from database import helpers
from models.conversation import Conversation
from utils.conversations import lifecycle
from routers.listen.receiver import ListenReceiver
from routers.listen.lane_meter import LiveLaneMeter
from routers.listen.parity_capture import ListenParityCapture
from testing.parity_pack_v0.schema import RequestFingerprint


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    for key in (
        'FIRST_SUMMARY_DEADLINE_ENABLED',
        'FIRST_SUMMARY_UID_ALLOWLIST',
        'FIRST_SUMMARY_DEADLINE_PERCENT',
        'BATCH_PIPELINE_ENABLED',
        'BATCH_PIPELINE_PERCENT',
        'BATCH_PIPELINE_UID_ALLOWLIST',
        'BATCH_PIPELINE_LIVE_ADMISSION_ENABLED',
        'BATCH_LIVE_STT_RETIRE_PERCENT',
    ):
        monkeypatch.delenv(key, raising=False)
    token = telemetry.current_demand.set(None)
    yield
    telemetry.current_demand.reset(token)


def enable(monkeypatch, percent='100'):
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', percent)
    monkeypatch.setenv('BATCH_PIPELINE_LIVE_ADMISSION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', percent)


def host():
    return SimpleNamespace(
        request=SimpleNamespace(uid='synthetic-owner', source='omi', onboarding_mode=False, language='en'),
        state=SimpleNamespace(current_conversation_id='synthetic-conversation'),
        batch_record_capture=dict(
            id='synthetic-conversation',
            record_lane_owner='batch_live_v1',
            private_cloud_sync_enabled=True,
            language='en',
            data_protection_level='enhanced',
        ),
        private_cloud_sync_enabled=True,
        is_multi_channel=False,
        use_custom_stt=False,
        pusher_enabled=True,
        language='en',
        multi_lang_enabled=False,
        language_profile=SimpleNamespace(primary='en', expected=('en',), multi=False, in_scope=False),
    )


def test_all_three_cohorts_share_batch_bucket_and_summary_survives_admission_rollback(monkeypatch):
    enable(monkeypatch, '5')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', '')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '5')
    results = []
    for index in range(1000):
        owner = f'synthetic-{index}'
        expected = batch_pipeline.enabled_for(owner)
        assert batch_live_preview.selected(owner) == expected
        assert summary_guarantee.enabled(owner) == expected
        results.append(expected)
    assert 20 < sum(results) < 80
    # The kill switch is all-or-nothing and the summary guarantee is independent of it, so a
    # 100-owner prefix proves both. The full 1000-owner sweep above keeps the bucket bound
    # statistically meaningful; each policy resolution copies the whole process environment.
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    assert not any(batch_pipeline.enabled_for(f'synthetic-{i}') for i in range(100))
    assert [summary_guarantee.enabled(f'synthetic-{i}') for i in range(100)] == results[:100]


def test_summary_kill_allowlist_legacy_global_and_invalid(monkeypatch):
    assert not summary_guarantee.enabled('synthetic')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    assert not summary_guarantee.enabled('synthetic')  # fail-safe at zero percent with no allowlist
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '100')
    assert summary_guarantee.enabled('synthetic')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '0')
    monkeypatch.setenv('FIRST_SUMMARY_UID_ALLOWLIST', ' synthetic-allowed ')
    assert summary_guarantee.enabled('synthetic-allowed')
    assert not summary_guarantee.enabled('synthetic')
    for invalid in ('nan', 'inf', '-1', '101', 'bad'):
        monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', invalid)
        assert not summary_guarantee.enabled('synthetic')
        assert summary_guarantee.enabled('synthetic-allowed')
        monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', invalid)
        assert not batch_live_preview.selected('synthetic')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'false')
    assert not summary_guarantee.enabled('synthetic-allowed')


@pytest.mark.parametrize(
    'field,value',
    [
        ('record_lane_owner', None),
        ('id', 'another-conversation'),
        ('private_cloud_sync_enabled', False),
        ('uses_custom_stt', True),
        ('deleted', True),
        ('discarded', True),
        ('data_protection_level', 'e2ee'),
        ('language', 'multi'),
    ],
)
def test_durable_record_fences(monkeypatch, field, value):
    enable(monkeypatch)
    h = host()
    assert batch_live_preview.covered(h)
    h.batch_record_capture[field] = value
    assert not batch_live_preview.covered(h)


@pytest.mark.parametrize(
    'field,value',
    [
        ('private_cloud_sync_enabled', False),
        ('is_multi_channel', True),
        ('use_custom_stt', True),
        ('pusher_enabled', False),
        ('language', 'pt'),
    ],
)
def test_live_session_exclusions(monkeypatch, field, value):
    enable(monkeypatch)
    h = host()
    setattr(h, field, value)
    assert not batch_live_preview.covered(h)


def test_preview_dark_or_uncovered_does_not_reselect(monkeypatch):
    monkeypatch.setattr(batch_preview, 'get_stt_service_for_language', lambda *a, **k: pytest.fail('unexpected dial'))
    assert not batch_preview.capture_batch_preview(host())
    enable(monkeypatch)
    h = host()
    h.batch_record_capture = None
    assert not batch_preview.capture_batch_preview(h)


def test_actual_selector_prefers_configured_parakeet_and_retains_policy(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-key')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setattr(streaming, 'stt_service_models', ['soniox', 'parakeet-window'])
    h = host()
    telemetry.attach_demand_telemetry(h, 'ineligible')
    assert batch_preview.capture_batch_preview(h)
    assert h.stt_service == streaming.STTService.parakeet
    assert h.stt_model == 'parakeet-window'
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0')
    unavailable = host()
    assert batch_preview.capture_batch_preview(unavailable)
    assert unavailable.stt_service == streaming.STTService.soniox
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    assert h.demand_telemetry.batch_cohort == 'admitted'
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    assert demand_routing.attach_live_demand(SimpleNamespace(host=h)) is None
    # No configured Parakeet: keep the configured vendor, never add a provider.
    monkeypatch.setattr(streaming, 'stt_service_models', ['soniox'])
    missing = host()
    assert batch_preview.capture_batch_preview(missing)
    assert missing.stt_service == streaming.STTService.soniox
    monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', '0')
    assert batch_preview.capture_batch_preview(h)  # Existing connection remains pinned.
    assert h.demand_telemetry.batch_cohort == 'admitted'
    control = host()
    telemetry.attach_demand_telemetry(control, 'ineligible')
    assert not batch_preview.capture_batch_preview(control)
    assert control.demand_telemetry.batch_cohort == 'eligible_control'


@pytest.mark.asyncio
async def test_actual_soniox_writes_and_capture_pin_retirement_denominator():
    h = host()
    attached = telemetry.attach_demand_telemetry(h, 'ineligible')
    attached.batch_cohort = 'admitted'
    wire = SimpleNamespace(send=AsyncMock(), close=AsyncMock())
    before = telemetry.BATCH_WIRE_AUDIO.labels(
        provider='soniox', batch_cohort='admitted', origin='initial'
    )._value.get()
    capture_before = telemetry.BATCH_CAPTURE_AUDIO.labels(batch_cohort='admitted')._value.get()
    sock = SafeSonioxSocket(wire, lambda _: None, asyncio.get_running_loop(), sample_rate=8000)
    sock._recv_task.cancel()
    sock._send_task.cancel()
    await asyncio.gather(sock._recv_task, sock._send_task, return_exceptions=True)
    try:
        pcm = b'\0\0' * 8000
        attached.capture(1)
        await sock._write(pcm)
        telemetry.attach_demand_telemetry(host(), 'eligible_control')
        await sock._write(pcm)  # replay stays attributed to the original admission
        await sock._write('keepalive')
        wire.send.side_effect = RuntimeError('synthetic failure')
        with pytest.raises(RuntimeError):
            await sock._write(pcm)
    finally:
        await sock.drain_and_close()
    assert (
        telemetry.BATCH_WIRE_AUDIO.labels(provider='soniox', batch_cohort='admitted', origin='initial')._value.get()
        - before
        == 2
    )
    assert telemetry.BATCH_CAPTURE_AUDIO.labels(batch_cohort='admitted')._value.get() - capture_before == 1


@pytest.mark.parametrize('level', ['standard', 'enhanced', 'e2ee', 'unknown'])
@pytest.mark.parametrize('idempotent', [False, True])
def test_fresh_model_resolves_privacy_before_ownership_without_an_extra_lookup(monkeypatch, level, idempotent):
    enable(monkeypatch)
    reads = []
    monkeypatch.setattr(helpers.redis_db, 'get_user_data_protection_level', lambda uid: reads.append(uid) or level)
    saved = []

    @helpers.set_data_protection_level(data_arg_name='conversation_data')
    def persist(uid, conversation_data):
        saved.append(dict(conversation_data))
        return True

    monkeypatch.setattr(lifecycle.conversations_db, 'upsert_conversation_with_lifecycle', persist)
    monkeypatch.setattr(lifecycle.conversations_db, 'create_conversation_if_absent_with_lifecycle', persist)
    now = datetime.now(timezone.utc)
    row = Conversation(
        id='synthetic-conversation',
        created_at=now,
        started_at=now,
        finished_at=now,
        status='in_progress',
        structured={},
        language='en',
        private_cloud_sync_enabled=True,
    ).model_dump()
    assert row['data_protection_level'] is None
    assert lifecycle.create_in_progress_conversation('synthetic-owner', row, idempotent=idempotent)
    assert len(reads) == 1
    assert saved[0]['data_protection_level'] == level
    assert (saved[0].get('record_lane_owner') == 'batch_live_v1') == (level in {'standard', 'enhanced'})


def test_capture_snapshot_never_retains_transcript_or_photo_payloads():
    row = {
        **host().batch_record_capture,
        'transcript_segments': [{'text': 'synthetic'}],
        'photos': [{'base64': 'synthetic'}],
        'structured': {'overview': 'synthetic'},
    }
    snapshot = batch_live_preview.capture_snapshot(row)
    assert set(snapshot) == {
        'id',
        'record_lane_owner',
        'private_cloud_sync_enabled',
        'uses_custom_stt',
        'deleted',
        'discarded',
        'data_protection_level',
        'language',
    }
    assert all(not isinstance(value, (dict, list)) for value in snapshot.values())


@pytest.mark.asyncio
@pytest.mark.parametrize('percent,cohort', [('0', 'eligible_control'), ('100', 'admitted')])
async def test_cap_pause_pins_capture_before_return_and_resume_does_not_reclassify(monkeypatch, percent, cohort):
    enable(monkeypatch)
    monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', percent)
    monkeypatch.setattr(batch_preview, 'get_stt_service_for_language', lambda *a, **k: pytest.fail('paused dial'))
    h = host()
    h.stt_service = streaming.STTService.soniox
    attached = telemetry.attach_demand_telemetry(h, 'admitted')
    h._demand_cohort = 'admitted'
    receiver = SimpleNamespace(host=h, cap_admission=SimpleNamespace(refresh=AsyncMock(), allowed=lambda _: False))
    h.receiver = receiver
    before = telemetry.BATCH_CAPTURE_AUDIO.labels(batch_cohort=cohort)._value.get()
    assert await ListenReceiver.initialize_stt(receiver)
    assert receiver.cap_paused
    attached.capture(1)
    assert attached.batch_cohort == cohort
    assert telemetry.BATCH_CAPTURE_AUDIO.labels(batch_cohort=cohort)._value.get() - before == 1
    monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', '0' if percent == '100' else '100')
    assert batch_preview.capture_batch_preview(h, select_provider=False) == (cohort == 'admitted')
    assert attached.batch_cohort == cohort


def test_batch_treatment_is_excluded_from_all_existing_live_demand_arms(monkeypatch):
    enable(monkeypatch)
    h = host()
    attached = telemetry.attach_demand_telemetry(h, 'admitted')
    h._demand_cohort = 'admitted'
    h.receiver = SimpleNamespace(lane_meter=LiveLaneMeter())
    h.receiver.lane_meter.demand_cohort = 'admitted'
    old_before = telemetry.CAPTURE_AUDIO.labels(demand_cohort='admitted')._value.get()
    assert batch_preview.capture_batch_preview(h, select_provider=False)
    assert h._demand_cohort == attached.cohort == h.receiver.lane_meter.demand_cohort == 'ineligible'
    assert demand_routing.attach_live_demand(SimpleNamespace(host=h)) is None
    attached.capture(1)
    assert telemetry.CAPTURE_AUDIO.labels(demand_cohort='admitted')._value.get() == old_before


@pytest.mark.parametrize('language,expected', [('en', ('en',)), ('pt', ('pt', 'en'))])
def test_window_preview_uses_supported_declared_multilingual_profiles(monkeypatch, language, expected):
    enable(monkeypatch)
    h = host()
    h.request.language = h.language = h.batch_record_capture['language'] = language
    h.multi_lang_enabled = True
    h.language_profile = SimpleNamespace(primary=language, expected=expected, multi=True)
    assert batch_live_preview.covered(h)
    h.language_profile.expected = (*expected, 'zh')
    assert not batch_live_preview.covered(h)


def test_window_preference_supersedes_hintable_vendor_only_when_policy_permits(monkeypatch):
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-key')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setattr(streaming, 'stt_service_models', ['soniox', 'parakeet-window'])
    profile = SimpleNamespace(primary='pt', expected=('pt', 'en'), multi=True, in_scope=True, arm='hintable')
    # A raw client hint cannot activate the new internal preference.
    assert (
        streaming.get_stt_service_for_language(
            'pt', preferred_service='parakeet-window', window_uid='synthetic', language_profile=profile
        )[0]
        == streaming.STTService.soniox
    )
    assert (
        streaming.get_stt_service_for_language('pt', prefer_window=True, language_profile=profile)[0]
        == streaming.STTService.soniox
    )
    assert (
        streaming.get_stt_service_for_language(
            'pt', prefer_window=True, window_uid='synthetic', language_profile=profile
        )[2]
        == 'parakeet-window'
    )
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '0')
    assert (
        streaming.get_stt_service_for_language(
            'pt', prefer_window=True, window_uid='synthetic', language_profile=profile
        )[0]
        == streaming.STTService.soniox
    )


def test_active_preview_controls_are_isolated_and_use_normal_policy(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', '1')
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-key')
    monkeypatch.setattr(streaming, 'stt_service_models', ['soniox', 'parakeet-window'])
    h = host()
    h.request.uid = next(
        f'synthetic-control-{i}' for i in range(100) if not batch_live_preview.selected(f'synthetic-control-{i}')
    )
    h.stt_service = streaming.STTService.parakeet
    h.stt_model = 'parakeet-window'
    attached = telemetry.attach_demand_telemetry(h, 'admitted')
    h._demand_cohort = 'admitted'
    assert not batch_preview.capture_batch_preview(h)
    assert h.batch_preview_isolated
    assert attached.batch_cohort == 'eligible_control'
    assert h._demand_cohort == attached.cohort == 'ineligible'
    assert h.stt_service == streaming.STTService.soniox
    assert demand_routing.attach_live_demand(SimpleNamespace(host=h)) is None


def test_zero_preview_percent_preserves_existing_live_demand_treatment(monkeypatch):
    enable(monkeypatch)
    monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', '0')
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setattr(batch_preview, 'get_stt_service_for_language', lambda *a, **k: pytest.fail('dark reselection'))
    h = host()
    attached = telemetry.attach_demand_telemetry(h, 'admitted')
    h._demand_cohort = 'admitted'
    assert not batch_preview.capture_batch_preview(h)
    assert not h.batch_preview_isolated
    assert attached.batch_cohort == 'eligible_control'
    assert attached.cohort == 'admitted'
    assert demand_routing.attach_live_demand(SimpleNamespace(host=h)).eligible


def test_preview_reselection_refreshes_parity_and_keeps_cap_paused_audio(monkeypatch, tmp_path):
    enable(monkeypatch)
    monkeypatch.setenv('HOSTED_PARAKEET_API_URL', 'http://synthetic.invalid')
    monkeypatch.setenv('SONIOX_API_KEY', 'synthetic-key')
    monkeypatch.setenv('PARAKEET_WINDOW_ALLOCATION_PERCENT', '100')
    monkeypatch.setattr(streaming, 'stt_service_models', ['soniox', 'parakeet-window'])
    h = host()
    h.request.codec, h.request.sample_rate, h.request.channels = 'pcm16', 8000, 1
    initial = dict(codec='pcm16', sample_rate=8000, channels=1, language='en', provider='soniox', model='soniox')
    h.parity_capture = ListenParityCapture.from_environ(
        principal_id=h.request.uid,
        session_id='synthetic-session',
        provider='soniox',
        model='soniox',
        request=initial,
        environ=dict(
            OMI_ENV_STAGE='dev',
            OMI_PARITY_PACK_CAPTURE='1',
            OMI_PARITY_PACK_ALLOWED_PRINCIPALS=h.request.uid,
            OMI_PARITY_PACK_ROOT=str(tmp_path),
        ),
    )
    assert h.parity_capture.enabled
    assert batch_preview.capture_batch_preview(h, select_provider=False)
    h.parity_capture.observe_client_audio(b'synthetic-paused-capture')
    assert batch_preview.capture_batch_preview(h)
    h.parity_capture.observe_outbound_stt(b'synthetic-window-request')
    h.parity_capture.persist()
    cassette = json.loads(next((tmp_path / 'cassettes').glob('*.json')).read_text())
    assert cassette['identity']['route_or_model'] == 'parakeet-window'
    expected = {**initial, 'provider': 'parakeet', 'model': 'parakeet-window'}
    assert cassette['request_fingerprint'] == RequestFingerprint.from_request(expected).as_dict()
    assert [event['direction'] for event in cassette['events']] == ['client', 'outbound']
    assert not h.parity_capture.reselect(provider='soniox', model='soniox', request=initial)
    monkeypatch.setattr(
        batch_preview, 'get_stt_service_for_language', lambda *a, **k: pytest.fail('resume reselection')
    )
    assert batch_preview.capture_batch_preview(h)
