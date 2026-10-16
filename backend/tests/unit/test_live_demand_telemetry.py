"""Exercise pinned admission, socket writes, replay and delivered-output telemetry offline."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from prometheus_client import REGISTRY

from routers.listen import demand_routing
from routers.listen import runtime as runtime_module
from routers.listen import lane_meter as lane_module
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from utils.observability import transcription
from tests.unit.test_listen_parity_runtime import (
    _AUDIO,
    _FakePersistence,
    _FakeWebSocket,
    _install_runtime_fakes,
)
from utils.observability import demand_cohort as telemetry
from utils.observability.fallback import record_fallback
from utils.stt.recovery_state import LiveRecoveryController
from utils.stt.live_metrics import RECOVERY_ATTEMPTS
from tests.unit.test_live_session_transcript_outcome import _runtime
from utils.metrics import OMI_LIVE_SESSION_TRANSCRIPT_OUTCOME_TOTAL
from utils.stt.soniox import SafeSonioxSocket
from utils.stt.streaming import SafeModulateSocket, _build_wav_header


@pytest.fixture(autouse=True)
def isolated_context():
    token = telemetry.current_demand.set(None)
    yield
    telemetry.current_demand.reset(token)


def host():
    return SimpleNamespace(
        request=SimpleNamespace(uid='synthetic', source='omi', onboarding_mode=False, language='en'),
        recovery_enabled=True,
        is_multi_channel=False,
        use_custom_stt=False,
        language='en',
        multi_lang_enabled=False,
        language_profile=SimpleNamespace(primary='en', expected=('en',), multi=False),
    )


@pytest.mark.parametrize(
    'enabled,percent,expected',
    [
        ('false', '100', 'eligible_control'),
        ('true', '0', 'eligible_control'),
        ('true', '100', 'admitted'),
    ],
)
def test_cohort_pinned_at_admission_even_after_kill(monkeypatch, enabled, percent, expected):
    monkeypatch.setattr(demand_routing, 'managed_chain_enabled', lambda _: True)
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', enabled)
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', percent)
    h = host()
    cohort = demand_routing.capture_demand_admission(h)
    assert cohort.cohort == expected
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100' if percent == '0' else '0')
    routing = demand_routing.attach_live_demand(SimpleNamespace(host=h))
    assert routing.eligible == (expected == 'admitted')
    assert h.demand_telemetry is cohort


@pytest.mark.parametrize(
    'field,value',
    [
        ('recovery_enabled', False),
        ('is_multi_channel', True),
        ('use_custom_stt', True),
        ('multi_lang_enabled', True),
        ('language', 'pt'),
        ('source', 'phone_call'),
        ('onboarding_mode', True),
    ],
)
def test_safety_exclusions_never_become_control(monkeypatch, field, value):
    monkeypatch.setattr(demand_routing, 'managed_chain_enabled', lambda _: True)
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    h = host()
    setattr(h.request if field in {'source', 'onboarding_mode'} else h, field, value)
    assert demand_routing.capture_demand_admission(h).cohort == 'ineligible'


def value(metric, **labels):
    return metric.labels(**labels)._value.get()


@pytest.mark.asyncio
@pytest.mark.parametrize('recovery', ['false', 'true'])
@pytest.mark.parametrize('provider', ['soniox', 'modulate'])
async def test_actual_writes_replay_failure_controls_and_pinned_cohort(monkeypatch, provider, recovery):
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', recovery)
    cohort = telemetry.DemandTelemetry('admitted')
    telemetry.current_demand.set(cohort)
    wire = SimpleNamespace(send=AsyncMock(), close=AsyncMock())
    labels = dict(provider=provider, demand_cohort='admitted')
    before = value(telemetry.WIRE_AUDIO, **labels)
    cls = SafeSonioxSocket if provider == 'soniox' else SafeModulateSocket
    sock = cls(wire, lambda _: None, asyncio.get_running_loop(), sample_rate=8000)
    # Drive the real writer deterministically without a live receive task.
    sock._recv_task.cancel()
    sock._send_task.cancel()
    await asyncio.gather(sock._recv_task, sock._send_task, return_exceptions=True)
    telemetry.current_demand.set(telemetry.DemandTelemetry('eligible_control'))
    pcm = b'\0\0' * 8000
    try:
        if provider == 'soniox':
            await sock._write(pcm)
            await sock._write(pcm)  # actual replay write: count again
            await sock._write('{"type":"keepalive"}')
            await sock._write('')
            wire.send.side_effect = RuntimeError('synthetic write failure')
            with pytest.raises(RuntimeError):
                await sock._write(pcm)
        else:
            sock.set_wav_header(_build_wav_header(8000))
            assert sock.send(pcm)
            assert sock.send(pcm)
            sock._send_queue.put_nowait(b'__EOS__')
            await sock._send_loop()
            assert len(wire.send.call_args_list[0].args[0]) == len(pcm) + len(sock._wav_header)
            wire.send.side_effect = RuntimeError('synthetic write failure')
            assert sock.send(pcm)
            await sock._send_loop()
        assert value(telemetry.WIRE_AUDIO, **labels) - before == pytest.approx(2)
    finally:
        sock._closed = True


def test_sync_transport_counts_below_sdk_acceptance_and_excludes_controls():
    telemetry.current_demand.set(telemetry.DemandTelemetry('eligible_control'))
    sent = []

    def send(data):
        if data == b'fail':
            raise RuntimeError('synthetic failed write')
        sent.append(data)

    raw = SimpleNamespace(send=send, connected=True)
    wrapped = telemetry.MeteredSyncTransport(raw, telemetry.WireAudioMeter('deepgram', 8000, 2))
    before = value(telemetry.WIRE_AUDIO, provider='deepgram', demand_cohort='eligible_control')
    wrapped.send(b'\0' * 32000)
    wrapped.send('{"type":"KeepAlive"}')
    wrapped.send(b'')
    with pytest.raises(RuntimeError):
        wrapped.send(b'fail')
    assert wrapped.connected
    assert value(telemetry.WIRE_AUDIO, provider='deepgram', demand_cohort='eligible_control') - before == 1


def test_exhausted_session_is_once_and_not_hop_count(monkeypatch):
    monkeypatch.setattr('utils.observability.fallback.logger.warning', lambda *a, **k: None)
    cohort = telemetry.DemandTelemetry('admitted')
    telemetry.current_demand.set(cohort)
    before = value(telemetry.EXHAUSTED_SESSIONS, demand_cohort='admitted', outcome='yes')
    for _ in range(2):
        record_fallback(
            component='stt_live_session',
            from_mode='parakeet',
            to_mode='none',
            reason='first_text_deadline',
            outcome='exhausted',
        )
    cohort.finish()
    cohort.finish()
    assert value(telemetry.EXHAUSTED_SESSIONS, demand_cohort='admitted', outcome='yes') - before == 1


def test_capture_and_first_output_and_visible_return_use_real_clocks(monkeypatch):
    now = [10.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: now[0])
    cohort = telemetry.DemandTelemetry('eligible_control')
    first = telemetry.OUTPUT_LATENCY.labels(demand_cohort=cohort.cohort, trigger='first_output')
    visible = telemetry.OUTPUT_LATENCY.labels(demand_cohort=cohort.cohort, trigger='visible_return')
    before_first, before_visible = first._sum.get(), visible._sum.get()
    cohort.capture(1)
    now[0] = 14
    cohort.delivered()
    cohort.delivered()
    assert first._sum.get() - before_first == 4
    cohort.observe_visibility({'foreground': False, 'transcript_visible': False})
    now[0] = 20
    cohort.observe_visibility({'foreground': True, 'transcript_visible': True})
    now[0] = 21
    cohort.observe_visibility({'foreground': True, 'transcript_visible': True})
    now[0] = 23
    cohort.delivered()
    cohort.delivered()
    assert visible._sum.get() - before_visible == 3


def test_metrics_only_expose_closed_labels():
    for metric in (
        telemetry.WIRE_AUDIO,
        telemetry.CAPTURE_AUDIO,
        telemetry.EXHAUSTED_SESSIONS,
        telemetry.OUTPUT_LATENCY,
    ):
        for family in metric.collect():
            for sample in family.samples:
                assert set(sample.labels) <= {'demand_cohort', 'provider', 'outcome', 'trigger', 'le'}
                assert sample.labels['demand_cohort'] in telemetry.DEMAND_COHORTS
    for cohort in telemetry.DEMAND_COHORTS:
        assert (
            REGISTRY.get_sample_value(
                'omi_stt_provider_wire_audio_seconds_total', {'provider': 'soniox', 'demand_cohort': cohort}
            )
            is not None
        )


def test_unanswered_output_waits_do_not_disappear_from_latency_gate():
    cohort = telemetry.DemandTelemetry('admitted')
    labels = dict(demand_cohort='admitted', trigger='visible_return', outcome='no_output')
    before = value(telemetry.OUTPUT_EVENTS, **labels)
    cohort.observe_visibility({'foreground': False, 'transcript_visible': False})
    cohort.observe_visibility({'foreground': True, 'transcript_visible': True})
    cohort.finish()
    cohort.finish()
    assert value(telemetry.OUTPUT_EVENTS, **labels) - before == 1


def test_recovery_dials_and_session_outcomes_keep_the_admission_cohort(monkeypatch):
    cohort = telemetry.DemandTelemetry('admitted')
    telemetry.current_demand.set(cohort)
    runtime = _runtime(terminal=True)
    runtime.demand_telemetry = cohort
    controller = LiveRecoveryController(runtime)
    controller.begin(family='parakeet')
    labels = dict(source='parakeet', successor='soniox', demand_cohort='admitted')
    before = value(RECOVERY_ATTEMPTS, **labels)
    assert controller.reserve('soniox')
    assert value(RECOVERY_ATTEMPTS, **labels) - before == 1
    before = value(OMI_LIVE_SESSION_TRANSCRIPT_OUTCOME_TOTAL, outcome='no_transcript', demand_cohort='admitted')
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'false')
    runtime._record_session_transcript_outcome()
    runtime._record_session_transcript_outcome()
    assert (
        value(OMI_LIVE_SESSION_TRANSCRIPT_OUTCOME_TOTAL, outcome='no_transcript', demand_cohort='admitted') - before
        == 1
    )


class _BrokenMetric:
    def __init__(self, failure):
        self.failure = failure

    def labels(self, **_labels):
        if self.failure == 'labels':
            raise RuntimeError('synthetic label binding failure')
        return self

    def inc(self, *_args):
        raise RuntimeError('synthetic counter failure')

    def observe(self, *_args):
        raise RuntimeError('synthetic histogram failure')


class _BrokenAttachment:
    @property
    def cohort(self):
        raise RuntimeError('synthetic cohort access failure')

    def __getattr__(self, _name):
        raise RuntimeError('synthetic telemetry access failure')


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['absent', 'constructor', 'attachment', 'labels', 'mutation'])
async def test_dark_real_runtime_bootstrap_audio_and_teardown_survive_optional_telemetry(monkeypatch, failure):
    """Real runtime/receiver lifecycle: receiver is None until late bootstrap."""
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'false')
    monkeypatch.setenv('OMI_PARITY_PACK_CAPTURE', '0')
    if failure == 'constructor':

        def unavailable(_cohort):
            raise RuntimeError('synthetic telemetry constructor failure')

        monkeypatch.setattr(telemetry, 'DemandTelemetry', unavailable)
    elif failure == 'attachment':
        monkeypatch.setattr(telemetry, 'DemandTelemetry', lambda _cohort: _BrokenAttachment())
    elif failure in {'labels', 'mutation'}:
        broken = _BrokenMetric(failure)
        for name in ('CAPTURE_AUDIO', 'WIRE_AUDIO', 'OUTPUT_EVENTS', 'OUTPUT_LATENCY', 'EXHAUSTED_SESSIONS'):
            monkeypatch.setattr(telemetry, name, broken)
        for name in ('WINDOW_CANARY_OUTCOME', 'COST_CANARY_OUTCOME', 'LIVE_SESSION_TERMINAL_AFTER_TEXT'):
            monkeypatch.setattr(runtime_module, name, broken)
        monkeypatch.setattr(lane_module, 'DEMAND_LANE_SECONDS', broken)
        monkeypatch.setattr(lane_module, 'DEMAND_SWITCHES', broken)
        monkeypatch.setattr(transcription, 'OMI_LIVE_SESSION_TRANSCRIPT_OUTCOME_TOTAL', broken)

    runtime = ListenSessionRuntime(
        ListenRequest(websocket=_FakeWebSocket(_AUDIO), uid=f'synthetic-telemetry-{failure}', codec='pcm16')
    )
    assert runtime.receiver is None
    # Exercise the same omitted optional attributes as bootstrap-only constructors.
    del runtime.demand_telemetry
    del runtime.recovery_enabled
    if failure == 'absent':
        monkeypatch.setattr(demand_routing, 'attach_demand_telemetry', lambda *_: None)
    runtime.persistence = _FakePersistence(fail_usage=False)
    sockets = []
    _install_runtime_fakes(monkeypatch, runtime, sockets, [])
    await runtime.run()
    assert runtime.receiver.live_demand is None
    assert len(sockets) == 1
    assert sockets[0].sent == [_AUDIO]
    assert sockets[0].finished
    assert len(runtime.transcripts.inbound) == 1
    runtime.complete_live_transcription()
    assert runtime.state.live_transcript_delivered
    if failure in {'absent', 'constructor', 'attachment'}:
        assert telemetry.host_cohort(runtime) == 'ineligible'


def test_metric_constructor_failure_does_not_change_demand_admission(monkeypatch):
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    monkeypatch.setattr(demand_routing, 'managed_chain_enabled', lambda _: True)

    def unavailable(_cohort):
        raise RuntimeError('synthetic telemetry failure')

    monkeypatch.setattr(telemetry, 'DemandTelemetry', unavailable)
    h = host()
    del h.recovery_enabled
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    assert demand_routing.capture_demand_admission(h) is None
    assert h._demand_cohort == 'admitted'
    assert demand_routing.attach_live_demand(SimpleNamespace(host=h)).eligible
    assert telemetry.host_cohort(h) == 'ineligible'


@pytest.mark.parametrize('failure', ['labels', 'mutation'])
def test_wire_meter_failure_cannot_change_successful_transport_result(monkeypatch, failure):
    telemetry.current_demand.set(telemetry.DemandTelemetry('admitted'))
    monkeypatch.setattr(telemetry, 'WIRE_AUDIO', _BrokenMetric(failure))
    raw = SimpleNamespace(send=lambda *_: 'written')
    wrapped = telemetry.MeteredSyncTransport(raw, telemetry.WireAudioMeter('deepgram', 16000))
    assert wrapped.send(b'\0\0') == 'written'


@pytest.mark.asyncio
@pytest.mark.parametrize('provider', ['soniox', 'modulate'])
@pytest.mark.parametrize('failure', ['labels', 'mutation'])
async def test_async_wire_metric_failure_keeps_successful_socket_alive(monkeypatch, provider, failure):
    telemetry.current_demand.set(telemetry.DemandTelemetry('admitted'))
    monkeypatch.setattr(telemetry, 'WIRE_AUDIO', _BrokenMetric(failure))
    wire = SimpleNamespace(send=AsyncMock(), close=AsyncMock())
    cls = SafeSonioxSocket if provider == 'soniox' else SafeModulateSocket
    sock = cls(wire, lambda _: None, asyncio.get_running_loop())
    sock._recv_task.cancel()
    sock._send_task.cancel()
    await asyncio.gather(sock._recv_task, sock._send_task, return_exceptions=True)
    pcm = b'\0\0' * 160
    try:
        if provider == 'soniox':
            await sock._write(pcm)
        else:
            assert sock.send(pcm)
            sock._send_queue.put_nowait(b'__EOS__')
            await sock._send_loop()
        assert wire.send.call_args_list[0].args == (pcm,)
        assert not sock.is_connection_dead
    finally:
        sock._closed = True
