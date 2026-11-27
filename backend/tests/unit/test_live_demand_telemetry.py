"""Exercise pinned admission, socket writes, replay and delivered-output telemetry offline."""

import asyncio
import json
import threading
from types import MethodType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from deepgram.clients.common.v1.abstract_sync_websocket import AbstractSyncWebSocketClient
from prometheus_client import REGISTRY

from models.transcript_segment import TranscriptSegment
from routers.listen import demand_routing
from routers.listen import receiver as receiver_module
from routers.listen import runtime as runtime_module
from routers.listen import lane_meter as lane_module
from routers.listen.contracts import ListenRequest
from routers.listen.runtime import ListenSessionRuntime
from routers.listen.transcripts import TranscriptProcessor
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
from utils.stt.safe_socket import SafeDeepgramSocket
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
    'field,value,reason',
    [
        ('recovery_enabled', False, 'recovery_off'),
        ('is_multi_channel', True, 'unmanaged_chain'),
        ('use_custom_stt', True, 'unmanaged_chain'),
        ('multi_lang_enabled', True, 'language_unqualified'),
        ('language', 'pt', 'language_unqualified'),
        ('language_profile', None, 'no_profile'),
        ('source', 'phone_call', 'phone_call'),
        ('onboarding_mode', True, 'onboarding'),
    ],
)
def test_safety_exclusions_never_become_control(monkeypatch, field, value, reason):
    monkeypatch.setattr(demand_routing, 'managed_chain_enabled', lambda _: True)
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    h = host()
    setattr(h.request if field in {'source', 'onboarding_mode'} else h, field, value)
    pinned = demand_routing.capture_demand_admission(h)
    assert pinned.cohort == 'ineligible'
    # The first failing admission condition names the exclusion (ruling f12e4a).
    assert pinned.ineligible_reason == reason


def test_ineligible_reason_is_the_first_failing_condition_and_eligible_has_none(monkeypatch):
    monkeypatch.setattr(demand_routing, 'managed_chain_enabled', lambda _: True)
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    h = host()
    h.recovery_enabled = False
    h.request.source = 'phone_call'  # also fails, but recovery is checked first
    assert demand_routing.ineligible_reason(h) == 'recovery_off'
    assert demand_routing.capture_demand_admission(h).ineligible_reason == 'recovery_off'
    assert demand_routing.ineligible_reason(host()) is None
    eligible = demand_routing.capture_demand_admission(host())
    assert eligible.cohort == 'admitted' and eligible.ineligible_reason == 'none'
    # Bounded: a reason only exists for the ineligible cohort and only from the closed set.
    assert telemetry.DemandTelemetry('admitted', 'phone_call').ineligible_reason == 'none'
    assert telemetry.DemandTelemetry('ineligible', 'free text').ineligible_reason == 'none'
    assert telemetry.DemandTelemetry('ineligible', 'no_profile').ineligible_reason == 'no_profile'


def test_exhausted_sessions_carry_the_ineligible_reason_and_zero_children_exist():
    pinned = telemetry.DemandTelemetry('ineligible', 'unmanaged_chain')
    before = value(
        telemetry.EXHAUSTED_SESSIONS, demand_cohort='ineligible', outcome='no', ineligible_reason='unmanaged_chain'
    )
    pinned.finish()
    assert (
        value(
            telemetry.EXHAUSTED_SESSIONS, demand_cohort='ineligible', outcome='no', ineligible_reason='unmanaged_chain'
        )
        - before
        == 1
    )
    for reason in telemetry.INELIGIBLE_REASONS:
        for outcome in ('yes', 'no'):
            assert (
                REGISTRY.get_sample_value(
                    'omi_listen_demand_exhausted_sessions_total',
                    {'demand_cohort': 'ineligible', 'outcome': outcome, 'ineligible_reason': reason},
                )
                is not None
            ), (reason, outcome)
    # 'none' exists for every cohort: the eligible ones always, and ineligible
    # for a session a batch preview moved there after admission.
    for cohort in ('admitted', 'eligible_control', 'ineligible'):
        assert (
            REGISTRY.get_sample_value(
                'omi_listen_demand_exhausted_sessions_total',
                {'demand_cohort': cohort, 'outcome': 'yes', 'ineligible_reason': 'none'},
            )
            is not None
        )


def value(metric, **labels):
    if metric is telemetry.WIRE_AUDIO:
        labels.setdefault('origin', 'initial')
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
    before = value(telemetry.EXHAUSTED_SESSIONS, demand_cohort='admitted', outcome='yes', ineligible_reason='none')
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
    assert (
        value(telemetry.EXHAUSTED_SESSIONS, demand_cohort='admitted', outcome='yes', ineligible_reason='none') - before
        == 1
    )


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


def _registry_label_sets(name: str) -> set[frozenset]:
    """One registry pass: every child of ``name`` as an immutable label set.

    ``REGISTRY.get_sample_value`` collects the whole registry on every call, so a
    cardinality assertion over 144 connected-seconds children would spend its
    entire fast-unit CPU budget there instead of testing the product.
    """
    return {
        frozenset(sample.labels.items())
        for family in REGISTRY.collect()
        for sample in family.samples
        if sample.name == name
    }


def test_metrics_only_expose_closed_labels():
    for metric in (
        telemetry.WIRE_AUDIO,
        telemetry.CAPTURE_AUDIO,
        telemetry.EXHAUSTED_SESSIONS,
        telemetry.OUTPUT_LATENCY,
        telemetry.SONIOX_CONNECTED,
    ):
        for family in metric.collect():
            for sample in family.samples:
                assert set(sample.labels) <= {
                    'demand_cohort',
                    'provider',
                    'outcome',
                    'trigger',
                    'le',
                    'ineligible_reason',
                    'origin',
                    'visibility',
                    'fallback_reason',
                }
                assert sample.labels['demand_cohort'] in telemetry.DEMAND_COHORTS
                visibility = sample.labels.get('visibility')
                if visibility is not None:
                    assert visibility in telemetry.VISIBILITY_BUCKETS
                fallback_reason = sample.labels.get('fallback_reason')
                if fallback_reason is not None:
                    assert fallback_reason in telemetry.FALLBACK_REASONS
                reason = sample.labels.get('ineligible_reason')
                if reason is not None:
                    assert reason in telemetry.INELIGIBLE_REASONS or reason == 'none'
                    if sample.labels['demand_cohort'] != 'ineligible':
                        assert reason == 'none'
    wire_labels = _registry_label_sets('omi_stt_provider_wire_audio_seconds_total')
    capture_labels = _registry_label_sets('omi_listen_demand_capture_audio_seconds_total')
    connected_labels = _registry_label_sets('omi_soniox_connected_seconds_total')
    for cohort in telemetry.DEMAND_COHORTS:
        assert (
            frozenset(
                {
                    'provider': 'soniox',
                    'demand_cohort': cohort,
                    'origin': 'initial',
                }.items()
            )
            in wire_labels
        )
        for visibility in telemetry.VISIBILITY_BUCKETS:
            assert (
                frozenset(
                    {
                        'demand_cohort': cohort,
                        'visibility': visibility,
                    }.items()
                )
                in capture_labels
            )
            for fallback_reason in telemetry.FALLBACK_REASONS:
                assert (
                    frozenset(
                        {
                            'provider': 'soniox',
                            'demand_cohort': cohort,
                            'origin': 'initial',
                            'visibility': visibility,
                            'fallback_reason': fallback_reason,
                        }.items()
                    )
                    in connected_labels
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
        self.attempts = 0

    def labels(self, **_labels):
        if self.failure == 'labels':
            self.attempts += 1
            raise RuntimeError('synthetic label binding failure')
        return self

    def inc(self, *_args):
        self.attempts += 1
        raise RuntimeError('synthetic counter failure')

    def observe(self, *_args):
        self.attempts += 1
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
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')
    telemetry.current_demand.set(telemetry.DemandTelemetry('admitted'))
    broken = _BrokenMetric(failure)
    monkeypatch.setattr(telemetry, 'WIRE_AUDIO', broken)
    wire = SimpleNamespace(send=AsyncMock(), close=AsyncMock())
    cls = SafeSonioxSocket if provider == 'soniox' else SafeModulateSocket
    sock = cls(wire, lambda _: None, asyncio.get_running_loop())
    sock._recv_task.cancel()
    sock._send_task.cancel()
    await asyncio.gather(sock._recv_task, sock._send_task, return_exceptions=True)
    pcm = b'\0\0' * 160
    try:
        assert sock.send(pcm)
        assert sock.send(pcm)  # an actual replay is still exactly one write
        sock._send_queue.put_nowait(b'' if provider == 'soniox' else b'__EOS__')
        await sock._send_loop()
        assert [call.args[0] for call in wire.send.call_args_list] == [pcm, pcm, '']
        assert broken.attempts == 2
        assert sock._send_queue.written_audio == 2
        assert sock._send_queue.inflight == 0
        assert sock._send_queue.empty()
        assert not sock.is_connection_dead
    finally:
        sock._closed = True


@pytest.mark.parametrize('failure', ['labels', 'mutation'])
def test_deepgram_sdk_and_safe_socket_keep_accepting_audio_when_wire_metric_raises(monkeypatch, failure):
    telemetry.current_demand.set(telemetry.DemandTelemetry('admitted'))
    broken = _BrokenMetric(failure)
    monkeypatch.setattr(telemetry, 'WIRE_AUDIO', broken)
    raw = SimpleNamespace(send=Mock())
    # Exercise the installed SDK's real exception-to-False boundary without dialing.
    sdk = SimpleNamespace(
        _socket=telemetry.MeteredSyncTransport(raw, telemetry.WireAudioMeter('deepgram', 16000)),
        _exit_event=threading.Event(),
        _lock_send=threading.Lock(),
        _logger=Mock(),
        _config=SimpleNamespace(options={}),
        is_connected=lambda: True,
        finish=lambda: None,
    )
    sdk.send = MethodType(AbstractSyncWebSocketClient.send, sdk)
    sock = SafeDeepgramSocket(sdk)
    try:
        pcm = b'\0\0' * 160
        assert sock.send(pcm)
        assert sock.send(pcm)
        assert raw.send.call_count == broken.attempts == 2
        assert not sock.is_connection_dead
        # Genuine transport failure must still cross the same boundary as False.
        raw.send.side_effect = RuntimeError('synthetic vendor write failure')
        assert not sock.send(pcm)
        assert sock.is_connection_dead
        assert not sock.send(pcm)
        assert raw.send.call_count == 3
    finally:
        sock.finish()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['labels', 'mutation'])
async def test_receive_loop_preserves_audio_and_client_state_when_metrics_raise(monkeypatch, failure):
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'false')
    capture, events = _BrokenMetric(failure), _BrokenMetric(failure)
    monkeypatch.setattr(telemetry, 'CAPTURE_AUDIO', capture)
    monkeypatch.setattr(telemetry, 'OUTPUT_EVENTS', events)
    websocket = _FakeWebSocket(_AUDIO)
    websocket._messages[:0] = [
        {'type': 'websocket.receive', 'text': json.dumps(dict(type='client_state', **payload))}
        for payload in (
            {'foreground': False, 'transcript_visible': False},
            {'foreground': True, 'transcript_visible': True},
        )
    ]
    runtime = ListenSessionRuntime(
        ListenRequest(websocket=websocket, uid=f'synthetic-state-metric-{failure}', codec='pcm16')
    )
    runtime.persistence = _FakePersistence(fail_usage=False)
    sockets = []
    _install_runtime_fakes(monkeypatch, runtime, sockets, [])

    build_components = runtime._build_components

    def build_with_translation_demand():
        build_components()
        runtime.transcripts.on_translation_demand_changed = AsyncMock()

    monkeypatch.setattr(runtime, '_build_components', build_with_translation_demand)

    def attach(receiver):
        routing = demand_routing.LiveDemandRouting(receiver, eligible=False)
        monkeypatch.setattr(routing, 'publish', AsyncMock(return_value=False))
        return routing

    monkeypatch.setattr(receiver_module, 'attach_live_demand', attach)
    await runtime.run()
    assert runtime.state.close_code == 1000
    assert sockets[0].sent == [_AUDIO]
    assert len(runtime.transcripts.inbound) == 1
    assert capture.attempts > 0 and events.attempts > 0
    policy = runtime.receiver.live_demand.policy
    assert policy.state == 'visible' and policy.reports == 2
    assert policy.decide(enabled=True, visible=False, consumer=False) == 'vendor'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['labels', 'mutation'])
async def test_real_transcript_delivery_continues_and_records_transcribed_when_latency_metric_raises(
    monkeypatch, failure
):
    runtime = ListenSessionRuntime(ListenRequest(websocket=_FakeWebSocket(b''), uid='synthetic-delivery'))
    runtime.pusher_enabled = True
    runtime.demand_telemetry = telemetry.DemandTelemetry('admitted')
    runtime.demand_telemetry.capture(1)
    runtime.demand_telemetry.observe_visibility({'foreground': False, 'transcript_visible': False})
    runtime.demand_telemetry.observe_visibility({'foreground': True, 'transcript_visible': True})
    broken = _BrokenMetric(failure)
    monkeypatch.setattr(telemetry, 'OUTPUT_LATENCY', broken)
    processor = TranscriptProcessor(runtime)
    segment = TranscriptSegment(id='synthetic-segment', text='synthetic text', is_user=False, start=0, end=1)
    before = value(OMI_LIVE_SESSION_TRANSCRIPT_OUTCOME_TOTAL, outcome='transcribed', demand_cohort='admitted')
    for _ in range(2):
        await processor._deliver_live_updates(
            SimpleNamespace(id='synthetic-conversation'), [segment], [], [segment], 'synthetic-conversation'
        )
    assert len(runtime.request.websocket.sent) == 2
    assert runtime.state.active and runtime.state.live_transcript_delivered
    assert broken.attempts == 2  # first output and visible return, despite two deliveries
    runtime._record_session_transcript_outcome()
    assert (
        value(OMI_LIVE_SESSION_TRANSCRIPT_OUTCOME_TOTAL, outcome='transcribed', demand_cohort='admitted') == before + 1
    )


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['labels', 'mutation'])
async def test_demand_lifetime_loop_survives_lane_metrics_and_returns_to_vendor(monkeypatch, failure):
    monkeypatch.setenv('STT_LIVE_DEMAND_ENABLED', 'true')
    monkeypatch.setenv('STT_LIVE_DEMAND_PERCENT', '100')
    broken = _BrokenMetric(failure)
    monkeypatch.setattr(lane_module, 'DEMAND_LANE_SECONDS', broken)
    monkeypatch.setattr(lane_module, 'DEMAND_SWITCHES', broken)
    h = host()
    h.state = SimpleNamespace(active=True, stt_terminal_failure=False)
    h.stt_model = 'parakeet-window'
    meter = lane_module.LiveLaneMeter()
    meter.transition('parakeet')
    receiver = SimpleNamespace(host=h, lane_meter=meter)
    routing = demand_routing.LiveDemandRouting(receiver, eligible=True)
    routing.policy.observe({'foreground': False, 'transcript_visible': False})
    waits = []

    async def wait(_seconds):
        waits.append(True)
        routing.policy.observe({'foreground': True, 'transcript_visible': True})
        return len(waits) == 2

    async def switch(desired):
        assert desired == 'vendor'
        meter.transition('soniox', reason=routing.policy.reason)
        h.stt_model = 'soniox'
        return True

    h.wait = wait
    receiver._switch_live_demand = AsyncMock(side_effect=switch)
    monkeypatch.setattr(routing, 'publish', AsyncMock(return_value=False))
    monkeypatch.setattr(demand_routing, 'realtime_consumer_active', AsyncMock(return_value=False))
    await routing.run()
    assert len(waits) == 2 and broken.attempts >= 5
    receiver._switch_live_demand.assert_awaited_once_with('vendor')
    assert h.state.active and not h.state.stt_terminal_failure
    assert routing.closed


@pytest.mark.parametrize(
    'payload',
    [
        {'foreground': 'true', 'transcript_visible': True},
        {'foreground': False, 'transcript_visible': True},
    ],
)
def test_invalid_visibility_preserves_open_wait_and_last_valid_background_state(monkeypatch, payload):
    now = [10.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: now[0])
    cohort = telemetry.DemandTelemetry('admitted')
    cohort.observe_visibility({'foreground': False, 'transcript_visible': False})
    cohort.observe_visibility(payload)
    assert cohort.visibility == 'background'
    cohort.observe_visibility({'foreground': True, 'transcript_visible': True})
    now[0] = 14
    cohort.observe_visibility(payload)
    cohort.observe_visibility({'foreground': True, 'transcript_visible': True})
    assert cohort.visible_at == 10
    labels = dict(demand_cohort='admitted', trigger='visible_return', outcome='no_output')
    before = value(telemetry.OUTPUT_EVENTS, **labels)
    cohort.finish()
    assert value(telemetry.OUTPUT_EVENTS, **labels) == before + 1


@pytest.mark.parametrize(
    'payload,expected',
    [
        ({'foreground': True, 'transcript_visible': True}, 'visible'),
        ({'foreground': True, 'transcript_visible': False}, 'foreground'),
        ({'foreground': False, 'transcript_visible': False}, 'background'),
    ],
)
def test_visibility_buckets_name_the_client_state(payload, expected):
    cohort = telemetry.DemandTelemetry('admitted')
    assert cohort.visibility is None
    cohort.observe_visibility(payload)
    assert cohort.visibility == expected


def test_capture_audio_is_attributed_once_to_the_visibility_in_force(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: now[0])
    cohort = telemetry.DemandTelemetry('admitted')
    token = telemetry.current_demand.set(cohort)
    try:
        before = {
            bucket: value(telemetry.CAPTURE_AUDIO, demand_cohort='admitted', visibility=bucket)
            for bucket in telemetry.VISIBILITY_BUCKETS
        }
        cohort.capture(2)  # never reported
        cohort.observe_visibility({'foreground': False, 'transcript_visible': False})
        cohort.capture(3)
        cohort.observe_visibility({'foreground': True, 'transcript_visible': False})
        cohort.capture(5)
        cohort.observe_visibility({'foreground': True, 'transcript_visible': True})
        cohort.capture(7)
        after = {
            bucket: value(telemetry.CAPTURE_AUDIO, demand_cohort='admitted', visibility=bucket)
            for bucket in telemetry.VISIBILITY_BUCKETS
        }
        assert after['unreported'] - before['unreported'] == pytest.approx(2)
        assert after['background'] - before['background'] == pytest.approx(3)
        assert after['foreground'] - before['foreground'] == pytest.approx(5)
        assert after['visible'] - before['visible'] == pytest.approx(7)
    finally:
        telemetry.current_demand.reset(token)


def test_connected_seconds_split_at_a_transition_inside_one_flush(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: now[0])
    cohort = telemetry.DemandTelemetry('ineligible')
    token = telemetry.current_demand.set(cohort)
    try:
        cohort.observe_visibility({'foreground': True, 'transcript_visible': False})
        meter = telemetry.create_connected_meter()
        labels = dict(provider='soniox', demand_cohort='ineligible', origin='initial', fallback_reason='none')
        before = {
            bucket: value(telemetry.SONIOX_CONNECTED, visibility=bucket, **labels)
            for bucket in telemetry.VISIBILITY_BUCKETS
        }
        now[0] += 2
        cohort.observe_visibility({'foreground': False, 'transcript_visible': False})
        now[0] += 4
        meter.flush(close=True)
        after = {
            bucket: value(telemetry.SONIOX_CONNECTED, visibility=bucket, **labels)
            for bucket in telemetry.VISIBILITY_BUCKETS
        }
        assert after['foreground'] - before['foreground'] == pytest.approx(2)
        assert after['background'] - before['background'] == pytest.approx(4)
        assert after['visible'] - before['visible'] == pytest.approx(0)
        assert after['unreported'] - before['unreported'] == pytest.approx(0)
    finally:
        telemetry.current_demand.reset(token)


def test_connected_seconds_split_exactly_past_the_transition_cap(monkeypatch):
    """A flapping client inside one flush must not be costed as ``unreported``.

    More than ``MAX_VISIBILITY_TRANSITIONS`` changes land between the flush
    start and its end, so the cap folds the oldest ones away; the flush still
    has to count every second once, in the bucket that actually held it.
    """
    now = [100.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: now[0])
    cohort = telemetry.DemandTelemetry('ineligible')
    token = telemetry.current_demand.set(cohort)
    try:
        cohort.observe_visibility({'foreground': True, 'transcript_visible': False})
        meter = telemetry.create_connected_meter()
        labels = dict(provider='soniox', demand_cohort='ineligible', origin='initial', fallback_reason='none')
        before = {
            bucket: value(telemetry.SONIOX_CONNECTED, visibility=bucket, **labels)
            for bucket in telemetry.VISIBILITY_BUCKETS
        }
        # One transition every 10 ms for 6 s: 600 alternating reports, more than
        # the cap, all inside the same flush interval.
        transitions = telemetry.MAX_VISIBILITY_TRANSITIONS + 88
        for step in range(transitions):
            now[0] += 0.01
            cohort.observe_visibility({'foreground': step % 2 == 1, 'transcript_visible': False})
        assert cohort._visibility_carry is not None
        assert len(cohort._visibility_log) <= telemetry.MAX_VISIBILITY_TRANSITIONS
        meter.flush(close=True)
        after = {
            bucket: value(telemetry.SONIOX_CONNECTED, visibility=bucket, **labels)
            for bucket in telemetry.VISIBILITY_BUCKETS
        }
        # 100.00-100.01 foreground, then 599 ten-millisecond windows alternating
        # from background: 3.00 s each, 6.00 s total, none unknown.
        assert after['unreported'] - before['unreported'] == pytest.approx(0)
        assert after['visible'] - before['visible'] == pytest.approx(0)
        assert after['foreground'] - before['foreground'] == pytest.approx(3.0)
        assert after['background'] - before['background'] == pytest.approx(3.0)
    finally:
        telemetry.current_demand.reset(token)


def test_folded_visibility_seconds_are_counted_once_across_flushes(monkeypatch):
    """The span the cap folded belongs to one flush; the next one must not repeat it."""
    now = [100.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: now[0])
    cohort = telemetry.DemandTelemetry('ineligible')
    token = telemetry.current_demand.set(cohort)
    try:
        cohort.observe_visibility({'foreground': True, 'transcript_visible': False})
        first = telemetry.create_connected_meter()
        labels = dict(provider='soniox', demand_cohort='ineligible', origin='initial', fallback_reason='none')
        before = {
            bucket: value(telemetry.SONIOX_CONNECTED, visibility=bucket, **labels)
            for bucket in telemetry.VISIBILITY_BUCKETS
        }
        for step in range(telemetry.MAX_VISIBILITY_TRANSITIONS + 88):
            now[0] += 0.002
            cohort.observe_visibility({'foreground': step % 2 == 1, 'transcript_visible': False})
        now[0] = 105.0
        first.flush(close=True)
        second = telemetry.create_connected_meter()
        now[0] = 107.0
        cohort.observe_visibility({'foreground': False, 'transcript_visible': False})
        now[0] = 110.0
        second.flush(close=True)
        after = {
            bucket: value(telemetry.SONIOX_CONNECTED, visibility=bucket, **labels)
            for bucket in telemetry.VISIBILITY_BUCKETS
        }
        delta = {bucket: after[bucket] - before[bucket] for bucket in telemetry.VISIBILITY_BUCKETS}
        assert delta['unreported'] == pytest.approx(0)
        assert delta['visible'] == pytest.approx(0)
        assert sum(delta.values()) == pytest.approx(10.0)
        assert delta['foreground'] + delta['background'] == pytest.approx(10.0)
    finally:
        telemetry.current_demand.reset(token)


def test_completed_flush_forgets_its_history_without_losing_the_next_bucket(monkeypatch):
    """Spent transitions are dropped, but the next interval still starts known."""
    now = [100.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: now[0])
    cohort = telemetry.DemandTelemetry('admitted')
    cohort.observe_visibility({'foreground': True, 'transcript_visible': False})
    now[0] += 2
    cohort.observe_visibility({'foreground': False, 'transcript_visible': False})
    now[0] += 3
    assert cohort.visibility_seconds(100.0, 105.0) == [('foreground', 2.0), ('background', 3.0)]
    assert cohort._visibility_log == [(105.0, 'background')]
    assert cohort.visibility_seconds(105.0, 108.0) == [('background', 3.0)]


def test_connected_seconds_carry_the_custody_fallback_reason(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(telemetry, 'monotonic', lambda: now[0])
    cohort = telemetry.DemandTelemetry('ineligible')
    token = telemetry.current_demand.set(cohort)
    try:
        meter = telemetry.create_connected_meter()
        labels = dict(provider='soniox', demand_cohort='ineligible', origin='initial', visibility='unreported')
        before = value(telemetry.SONIOX_CONNECTED, fallback_reason='claim', **labels)
        cohort.note_fallback_reason('claim')
        now[0] += 6
        meter.flush(close=True)
        assert value(telemetry.SONIOX_CONNECTED, fallback_reason='claim', **labels) == pytest.approx(before + 6)
        # Bounded: an unknown reason never becomes a label value.
        cohort.note_fallback_reason('unbounded-input')
        assert cohort.fallback_reason == 'claim'
    finally:
        telemetry.current_demand.reset(token)
