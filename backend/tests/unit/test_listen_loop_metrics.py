"""Listen loop-health metrics: loop lag probe, per-frame timing, VAD window rate and kill switch."""

import asyncio
import contextvars
import struct
import time
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
import pytest

import utils.observability.listen_loop as listen_loop
from routers.listen.receiver import ListenReceiver
from utils.observability.listen_loop import (
    ENABLED_ENV,
    FRAME_CODECS,
    FrameTimer,
    LISTEN_EVENT_LOOP_LAG_SECONDS,
    LISTEN_FRAME_PROCESSING_SECONDS,
    VAD_INFERENCE_SECONDS_TOTAL,
    VAD_WINDOWS_TOTAL,
    ensure_loop_lag_probe,
    frame_codec_label,
    listen_loop_metrics_enabled,
    record_vad_windows,
)
from utils.byok import get_byok_key, set_validated_byok_keys
from utils.stt.vad_gate import VADStreamingGate


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _sample(metric, suffix, **labels):
    for family in metric.collect():
        for sample in family.samples:
            if sample.name.endswith(suffix) and sample.labels == labels:
                return sample.value
    return 0.0


def _frame_count(codec):
    return _sample(LISTEN_FRAME_PROCESSING_SECONDS, '_count', codec=codec)


def _windows():
    return _sample(VAD_WINDOWS_TOTAL, '_total')


@pytest.mark.parametrize('value', ['', 'true', '1', 'on', 'anything'])
def test_enabled_by_default_and_for_non_off_values(monkeypatch, value):
    monkeypatch.setenv(ENABLED_ENV, value)
    assert listen_loop_metrics_enabled() is True


def test_enabled_when_unset(monkeypatch):
    monkeypatch.delenv(ENABLED_ENV, raising=False)
    assert listen_loop_metrics_enabled() is True


@pytest.mark.parametrize('value', ['false', '0', 'off', 'no', ' FALSE '])
def test_kill_switch_values_disable(monkeypatch, value):
    monkeypatch.setenv(ENABLED_ENV, value)
    assert listen_loop_metrics_enabled() is False


def test_codec_label_is_closed_vocabulary():
    assert frame_codec_label('opus') == 'opus'
    assert frame_codec_label('pcm16') == 'pcm16'
    assert frame_codec_label('opus_fs320') == 'other'
    assert frame_codec_label('uid-abc123') == 'other'
    assert frame_codec_label(None) == 'other'
    assert frame_codec_label('opus', multi_channel=True) == 'multi_channel'


def test_metrics_carry_no_identity_labels():
    FrameTimer('opus', enabled=True)  # materialise one labelled child
    allowed = {'codec', 'le'}
    for metric in (LISTEN_EVENT_LOOP_LAG_SECONDS, LISTEN_FRAME_PROCESSING_SECONDS, VAD_WINDOWS_TOTAL):
        for family in metric.collect():
            for sample in family.samples:
                assert set(sample.labels) <= allowed
                assert sample.labels.get('codec', 'opus') in FRAME_CODECS


def test_frame_timer_observes_once_per_started_frame():
    before = _frame_count('lc3')
    timer = FrameTimer('lc3', enabled=True)
    timer.stop()  # nothing started: no observation
    timer.start()
    timer.stop()
    timer.stop()  # already stopped: no double count
    assert _frame_count('lc3') == before + 1


def test_frame_timer_disabled_is_noop(monkeypatch):
    monkeypatch.setenv(ENABLED_ENV, 'false')
    before = _frame_count('aac')
    timer = FrameTimer('aac')
    timer.start()
    timer.stop()
    assert _frame_count('aac') == before


def test_record_vad_windows_counts_windows_and_seconds():
    windows, seconds = _windows(), _sample(VAD_INFERENCE_SECONDS_TOTAL, '_total')
    record_vad_windows(0, 1.0)  # buffering-only call: time counts, no window
    assert _windows() == windows
    assert _sample(VAD_INFERENCE_SECONDS_TOTAL, '_total') == pytest.approx(seconds + 1.0)
    seconds = _sample(VAD_INFERENCE_SECONDS_TOTAL, '_total')
    record_vad_windows(0, 0.0)
    assert _sample(VAD_INFERENCE_SECONDS_TOTAL, '_total') == seconds
    record_vad_windows(3, 0.002)
    assert _windows() == windows + 3
    assert _sample(VAD_INFERENCE_SECONDS_TOTAL, '_total') == pytest.approx(seconds + 0.002)


@pytest.mark.anyio
async def test_lag_probe_measures_blocked_loop_and_is_idempotent(monkeypatch):
    monkeypatch.delenv(ENABLED_ENV, raising=False)
    monkeypatch.setattr(listen_loop, '_probe', None)
    count = _sample(LISTEN_EVENT_LOOP_LAG_SECONDS, '_count')
    total = _sample(LISTEN_EVENT_LOOP_LAG_SECONDS, '_sum')
    task = ensure_loop_lag_probe(interval=0.01)
    assert task is not None
    try:
        assert ensure_loop_lag_probe(interval=0.01) is task
        await asyncio.sleep(0)  # let the probe arm its sleep
        time.sleep(0.08)  # block the loop well past the probe interval
        await asyncio.sleep(0.03)
        assert _sample(LISTEN_EVENT_LOOP_LAG_SECONDS, '_count') > count
        assert _sample(LISTEN_EVENT_LOOP_LAG_SECONDS, '_sum') - total >= 0.05
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    # A finished probe is replaced on the next session.
    replacement = ensure_loop_lag_probe(interval=0.01)
    assert replacement is not None
    assert replacement is not task
    replacement.cancel()
    await asyncio.gather(replacement, return_exceptions=True)


@pytest.mark.anyio
async def test_lag_probe_kill_switch(monkeypatch):
    monkeypatch.setenv(ENABLED_ENV, 'false')
    monkeypatch.setattr(listen_loop, '_probe', None)
    assert ensure_loop_lag_probe(interval=0.01) is None
    assert getattr(listen_loop, '_probe') is None


def test_lag_probe_without_running_loop_is_noop(monkeypatch):
    monkeypatch.delenv(ENABLED_ENV, raising=False)
    monkeypatch.setattr(listen_loop, '_probe', None)
    assert ensure_loop_lag_probe() is None


def _fresh_state():
    return np.zeros((2, 1, 128), dtype=np.float32), np.zeros((1, 64), dtype=np.float32)


def _silence(samples):
    return struct.pack(f'<{samples}h', *([0] * samples))


@pytest.mark.parametrize(('env', 'expected'), [(None, 2), ('false', 0)])
def test_vad_gate_counts_inferred_windows(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv(ENABLED_ENV, raising=False)
    else:
        monkeypatch.setenv(ENABLED_ENV, env)
    with (
        patch('utils.stt.vad_gate._get_ort_session'),
        patch('utils.stt.vad_gate.make_fresh_state', side_effect=_fresh_state),
        patch('utils.stt.vad_gate.run_vad_window', side_effect=lambda w, s, c: (0.1, s, c)),
    ):
        gate = VADStreamingGate(sample_rate=16000, channels=1, mode='active')
        before = _windows()
        gate.process_audio(_silence(1024 + 100), 0.0)
        assert _windows() == before + expected


class _FramesWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)

    async def receive(self):
        return next(self.frames)


class _BrokenDecoder:
    def decode(self, *_args, **_kwargs):
        raise ValueError('malformed frame')


def _receiver(frames, codec='opus'):
    host = SimpleNamespace(
        request=SimpleNamespace(websocket=_FramesWebSocket(frames), uid='test-uid', codec=codec),
        state=SimpleNamespace(
            current_conversation_id=None,
            active=True,
            close_code=1001,
            last_audio_received_time=None,
            last_activity_time=None,
            first_audio_byte_timestamp=None,
            last_usage_record_timestamp=None,
            audio_ring_buffer=None,
        ),
        limits=SimpleNamespace(ws_receive_timeout=1.0),
        is_multi_channel=False,
        use_custom_stt=True,
        audio_bytes_send=None,
        transcripts=SimpleNamespace(enqueue=lambda segments: None),
        start_live_transcription=lambda: None,
    )
    receiver = ListenReceiver(host, [], {})
    receiver.opus_decoder = _BrokenDecoder()
    return receiver


@pytest.mark.anyio
@pytest.mark.parametrize(('env', 'expected'), [(None, 2), ('false', 0)])
async def test_receiver_times_each_audio_frame_but_not_text_or_heartbeats(monkeypatch, env, expected):
    if env is None:
        monkeypatch.delenv(ENABLED_ENV, raising=False)
    else:
        monkeypatch.setenv(ENABLED_ENV, env)
    before = _frame_count('opus')
    receiver = _receiver(
        [
            {'bytes': b'frame-one'},
            {'text': '{"type": "unknown"}'},
            {'bytes': b'\x00'},  # heartbeat-sized frame: not an audio frame
            {'bytes': b'frame-two'},
            {'type': 'websocket.disconnect', 'code': 1000},
        ]
    )
    await receiver.receive_data()
    assert _frame_count('opus') == before + expected


@pytest.mark.anyio
async def test_lag_probe_does_not_inherit_session_byok_or_uid_context(monkeypatch):
    monkeypatch.delenv(ENABLED_ENV, raising=False)
    monkeypatch.setattr(listen_loop, '_probe', None)
    captured: list[contextvars.Context] = []

    async def capture(_interval: float) -> None:
        captured.append(contextvars.copy_context())

    monkeypatch.setattr(listen_loop, '_probe_loop_lag', capture)

    async def session() -> asyncio.Task:
        set_validated_byok_keys({'deepgram': 'secret-key'}, 'user-1')
        assert get_byok_key('deepgram') == 'secret-key'
        task = ensure_loop_lag_probe(interval=0.01)
        assert task is not None
        return task

    task = await asyncio.create_task(session())
    await task
    assert len(captured) == 1
    leaked = {var.name: value for var, value in captured[0].items() if var.name.startswith('byok')}
    assert all(value in (None, False) for value in leaked.values()), leaked
    assert 'secret-key' not in repr(list(captured[0].values()))
    assert 'user-1' not in repr(list(captured[0].values()))
