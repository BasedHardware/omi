"""Batch cohort alignment, durable coverage and actual vendor-write denominators."""

import asyncio

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from config import batch_pipeline, batch_live_preview, summary_guarantee
from routers.listen import batch_preview, demand_routing
from utils.observability import demand_cohort as telemetry
from utils.stt import streaming
from utils.stt.soniox import SafeSonioxSocket


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


def test_all_three_cohorts_share_batch_bucket_and_nesting(monkeypatch):
    enable(monkeypatch, '5')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_PERCENT', '5')
    results = []
    for index in range(1000):
        owner = f'synthetic-{index}'
        expected = batch_pipeline.enabled_for(owner)
        assert batch_live_preview.selected(owner) == expected
        assert summary_guarantee.enabled(owner) == expected
        results.append(expected)
    assert 20 < sum(results) < 80
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '1')
    assert all(not summary_guarantee.enabled(f'synthetic-{i}') or results[i] for i in range(1000))


def test_summary_kill_allowlist_legacy_global_and_invalid(monkeypatch):
    assert not summary_guarantee.enabled('synthetic')
    monkeypatch.setenv('FIRST_SUMMARY_DEADLINE_ENABLED', 'true')
    assert summary_guarantee.enabled('synthetic')  # legacy empty list at zero
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
        ('multi_lang_enabled', True),
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
    monkeypatch.setattr(streaming, 'stt_service_models', ['soniox', 'parakeet'])
    h = host()
    telemetry.attach_demand_telemetry(h, 'ineligible')
    assert batch_preview.capture_batch_preview(h)
    assert h.stt_service == streaming.STTService.parakeet
    assert h.demand_telemetry.batch_cohort == 'admitted'
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    assert demand_routing.attach_live_demand(SimpleNamespace(host=h)) is None
    # No configured Parakeet: keep the configured vendor, never add a provider.
    monkeypatch.setattr(streaming, 'stt_service_models', ['soniox'])
    assert batch_preview.capture_batch_preview(h)
    assert h.stt_service == streaming.STTService.soniox
    monkeypatch.setenv('BATCH_LIVE_STT_RETIRE_PERCENT', '0')
    assert not batch_preview.capture_batch_preview(h)
    assert h.demand_telemetry.batch_cohort == 'eligible_control'


@pytest.mark.asyncio
async def test_actual_soniox_writes_and_capture_pin_retirement_denominator():
    h = host()
    attached = telemetry.attach_demand_telemetry(h, 'ineligible')
    attached.batch_cohort = 'admitted'
    wire = SimpleNamespace(send=AsyncMock(), close=AsyncMock())
    before = telemetry.BATCH_WIRE_AUDIO.labels(provider='soniox', batch_cohort='admitted')._value.get()
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
    assert telemetry.BATCH_WIRE_AUDIO.labels(provider='soniox', batch_cohort='admitted')._value.get() - before == 2
    assert telemetry.BATCH_CAPTURE_AUDIO.labels(batch_cohort='admitted')._value.get() - capture_before == 1
