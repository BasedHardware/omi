"""Self-heal listen telemetry: VAD zero-byte sessions and the all-source no-audio funnel.

The wedge detector and the accepted -> first_audio -> no_audio funnel depend on
two new bounded counters plus a pure-JSON ``vad_gate_metrics`` stdout line. These
tests pin exactly-once emission, bounded labels, and no overlap with the
phone-specific ``omi_listen_audio_outcome_total`` outcomes.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import routers.listen.receiver as receiver_module
import routers.listen.runtime as runtime_module
from routers.listen.receiver import ListenReceiver
from utils.metrics import (
    OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
    OMI_LISTEN_NO_AUDIO_TEARDOWN_TOTAL,
    OMI_LISTEN_ZERO_BYTE_SESSION_TOTAL,
)
from utils.observability.transcription import emit_listen_vad_gate_metrics


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _counter_value(counter, **labels) -> int:
    return counter.labels(**labels)._value.get()


def _disconnect():
    return {'type': 'websocket.disconnect', 'code': 1000}


class _FakeVadGate:
    def __init__(self, *, bytes_received=0, chunks_total=0, session_duration_sec=0.0, speech_ms_total=0):
        self._metrics = {
            'bytes_received': bytes_received,
            'chunks_total': chunks_total,
            'speech_ms_total': speech_ms_total,
            'mode': 'active',
        }
        self._duration = session_duration_sec

    def get_metrics(self):
        return dict(self._metrics)

    def to_json_log(self):
        return {
            'event': 'vad_gate_metrics',
            'uid': 'uid-1',
            'session_id': 'session-1',
            'session_duration_sec': self._duration,
            **self._metrics,
        }


def _host(**overrides):
    host = SimpleNamespace(
        stt_service='modulate',
        is_multi_channel=False,
        use_custom_stt=True,
        audio_bytes_send=None,
        request=SimpleNamespace(source='omi', codec='pcm', sample_rate=16000, uid='uid-1', websocket=SimpleNamespace()),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        state=SimpleNamespace(
            active=True,
            close_code=None,
            last_audio_received_time=None,
            last_activity_time=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
            audio_ring_buffer=None,
            stt_terminal_failure=False,
            live_transcription_attempt=None,
        ),
        client_device_context=SimpleNamespace(platform='ios'),
    )
    for key, value in overrides.items():
        setattr(host, key, value)
    return host


async def _run_teardown(host, *, vad_gate=None):
    host.request.websocket = SimpleNamespace(receive=AsyncMock(side_effect=[_disconnect()]))
    receiver = ListenReceiver(host, [], {})
    receiver.vad_gate = vad_gate
    await receiver.receive_data()
    return receiver


def test_vad_gate_metrics_emit_pure_json_line_with_bounded_labels(capsys):
    payload = _FakeVadGate(bytes_received=10, chunks_total=1, session_duration_sec=5.0).to_json_log()
    emitted = emit_listen_vad_gate_metrics(payload, source='omi', platform='ios')
    out = capsys.readouterr().out
    line = out.strip().splitlines()[-1]
    parsed = json.loads(line)  # the whole line must be the payload — nothing prefixed
    assert parsed == emitted
    assert parsed['event'] == 'vad_gate_metrics'
    assert parsed['uid'] == 'uid-1'
    assert parsed['session_id'] == 'session-1'
    assert parsed['transcription_source'] == 'omi'
    assert parsed['client_platform'] == 'ios'


@pytest.mark.anyio
async def test_teardown_emits_vad_gate_json_line_and_no_zero_increment_for_normal_session(capsys):
    host = _host()
    gate = _FakeVadGate(bytes_received=640, chunks_total=2, session_duration_sec=0.04)
    before = _counter_value(OMI_LISTEN_ZERO_BYTE_SESSION_TOTAL, transcription_source='omi', client_platform='ios')

    await _run_teardown(host, vad_gate=gate)

    out_lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]
    vad_lines = []
    for line in out_lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if parsed.get('event') == 'vad_gate_metrics':
            vad_lines.append(parsed)
    (vad_line,) = vad_lines
    assert vad_line['transcription_source'] == 'omi'
    assert vad_line['client_platform'] == 'ios'
    assert vad_line['bytes_received'] == 640
    assert (
        _counter_value(OMI_LISTEN_ZERO_BYTE_SESSION_TOTAL, transcription_source='omi', client_platform='ios') == before
    )


@pytest.mark.anyio
async def test_teardown_counts_true_zero_session_exactly_once(capsys):
    host = _host()
    before = _counter_value(OMI_LISTEN_ZERO_BYTE_SESSION_TOTAL, transcription_source='omi', client_platform='ios')

    await _run_teardown(host, vad_gate=_FakeVadGate())

    assert (
        _counter_value(OMI_LISTEN_ZERO_BYTE_SESSION_TOTAL, transcription_source='omi', client_platform='ios')
        == before + 1
    )


@pytest.mark.anyio
async def test_teardown_without_vad_gate_emits_no_zero_and_no_json_line(capsys):
    host = _host()
    before = _counter_value(OMI_LISTEN_ZERO_BYTE_SESSION_TOTAL, transcription_source='omi', client_platform='ios')

    await _run_teardown(host, vad_gate=None)

    assert (
        _counter_value(OMI_LISTEN_ZERO_BYTE_SESSION_TOTAL, transcription_source='omi', client_platform='ios') == before
    )
    assert 'vad_gate_metrics' not in capsys.readouterr().out


@pytest.mark.anyio
async def test_run_listen_session_counts_no_audio_teardown_once(monkeypatch):
    """An accepted session with no first-audio byte increments once — VAD or not."""
    calls = []
    monkeypatch.setattr(
        runtime_module,
        'record_listen_no_audio_teardown',
        lambda *, source, platform: calls.append((source, platform)),
    )

    class _Runtime:
        def __init__(self, request):
            self.request = request
            self.state = SimpleNamespace(first_audio_byte_timestamp=None)
            self.client_device_context = SimpleNamespace(platform='ios')

        async def run(self):
            return None

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', _Runtime)
    request = SimpleNamespace(source='omi')
    await runtime_module.run_listen_session(request)
    assert calls == [('omi', 'ios')]


@pytest.mark.anyio
async def test_run_listen_session_skips_no_audio_when_first_audio_seen(monkeypatch):
    calls = []
    monkeypatch.setattr(
        runtime_module,
        'record_listen_no_audio_teardown',
        lambda *, source, platform: calls.append((source, platform)),
    )

    class _Runtime:
        def __init__(self, request):
            self.request = request
            self.state = SimpleNamespace(first_audio_byte_timestamp=1.0)
            self.client_device_context = SimpleNamespace(platform='ios')

        async def run(self):
            return None

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', _Runtime)
    await runtime_module.run_listen_session(SimpleNamespace(source='omi'))
    assert calls == []


@pytest.mark.anyio
async def test_no_audio_counter_does_not_emit_phone_specific_outcome(monkeypatch):
    """The generic counter never doubles as the phone-specific audio outcome."""
    before_generic = _counter_value(
        OMI_LISTEN_NO_AUDIO_TEARDOWN_TOTAL, transcription_source='omi', client_platform='ios'
    )
    before_phone = _counter_value(
        OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
        transcription_source='omi',
        outcome='no_audio_teardown',
        client_platform='ios',
    )

    class _Runtime:
        def __init__(self, request):
            self.request = request
            self.state = SimpleNamespace(first_audio_byte_timestamp=None)
            self.client_device_context = SimpleNamespace(platform='ios')

        async def run(self):
            return None

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', _Runtime)
    await runtime_module.run_listen_session(SimpleNamespace(source='omi'))

    assert (
        _counter_value(OMI_LISTEN_NO_AUDIO_TEARDOWN_TOTAL, transcription_source='omi', client_platform='ios')
        == before_generic + 1
    )
    assert (
        _counter_value(
            OMI_LISTEN_AUDIO_OUTCOME_TOTAL,
            transcription_source='omi',
            outcome='no_audio_teardown',
            client_platform='ios',
        )
        == before_phone
    )


@pytest.mark.anyio
async def test_run_listen_session_runtime_failure_still_counts_accepted_session(monkeypatch):
    """A crash inside run() still emits exactly one no-audio teardown row."""
    calls = []
    monkeypatch.setattr(
        runtime_module,
        'record_listen_no_audio_teardown',
        lambda *, source, platform: calls.append((source, platform)),
    )

    class _Runtime:
        def __init__(self, request):
            self.request = request
            self.state = SimpleNamespace(first_audio_byte_timestamp=None)
            self.client_device_context = SimpleNamespace(platform='web')

        async def run(self):
            raise RuntimeError('boom')

    monkeypatch.setattr(runtime_module, 'ListenSessionRuntime', _Runtime)
    with pytest.raises(RuntimeError):
        await runtime_module.run_listen_session(SimpleNamespace(source='omi'))
    assert calls == [('omi', 'web')]


def test_receiver_module_uses_stdout_emitter():
    """The prefixed logger line must be gone: structured logs need a pure JSON line."""
    import inspect

    source = inspect.getsource(receiver_module)
    assert 'logger.info(json.dumps(self.vad_gate.to_json_log()))' not in source
