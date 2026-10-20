"""STT cap held (untranscribed) live audio is not metered as transcription seconds.

Held audio is billed once, by recovery, when it is actually transcribed. Seconds
before the hold and after a resume meter exactly as before.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from routers.listen.runtime import ListenSessionRuntime
from utils import stt_cap_dispatch as cap
from utils.stt.streaming import STTService


class _Persistence:
    async def call(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)


@pytest.fixture(autouse=True)
def isolation(monkeypatch):
    import routers.listen.runtime as runtime_module

    monkeypatch.delenv('STT_CAP_DISPATCH_ENFORCEMENT', raising=False)
    monkeypatch.setattr(cap, 'get_byok_key', lambda _: None)
    monkeypatch.setattr(cap, 'record_audio', Mock())
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'managed_chain_enabled', lambda runtime: False)
    monkeypatch.setattr(runtime_module, 'record_live_stt_audio_seconds', lambda **kwargs: None)


@pytest.fixture
def usage(monkeypatch):
    import routers.listen.runtime as runtime_module

    calls = []
    monkeypatch.setattr(runtime_module, 'record_usage', lambda *args, **kwargs: calls.append(kwargs))
    return calls


def _runtime(receiver, *, multi_channel=False):
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='synthetic')
    runtime.use_custom_stt = False
    runtime.is_multi_channel = multi_channel
    runtime.persistence = _Persistence()
    runtime.stt_service = STTService.parakeet
    runtime.client_device_context = SimpleNamespace(platform='ios')
    runtime.state = SimpleNamespace(
        fair_use_track_dg_usage=False,
        dg_usage_ms_pending=0,
        last_usage_record_timestamp=None,
        words_transcribed_since_last_record=0,
        last_audio_received_time=None,
        last_audio_resume_time=None,
    )
    runtime.receiver = receiver
    return runtime


async def _flush(runtime, monkeypatch, start, end, *, final=False):
    import routers.listen.runtime as runtime_module

    runtime.state.last_usage_record_timestamp = start
    runtime.state.last_audio_received_time = end
    monkeypatch.setattr(runtime_module.time, 'time', lambda: end)
    return await runtime._flush_usage(final=final)


def _exhausted_admission():
    admission = cap.LiveAdmission('synthetic')
    admission.managed, admission.remaining = True, 30
    return admission


def _deny(admission, seconds, rate=16000):
    """Exercise the real suppression path the receiver and CapSocket share."""
    raw = Mock(send=Mock(return_value=True), is_connection_dead=False)
    socket = cap.CapSocket(admission, 'parakeet', rate, AsyncMock(), raw)
    admission.managed, admission.remaining = False, 0
    assert socket.suppress(b'\0' * int(2 * rate * seconds)) is True
    raw.send.assert_not_called()


async def test_session_crossing_into_hold_meters_only_pre_hold_seconds(monkeypatch, usage):
    admission = _exhausted_admission()
    runtime = _runtime(SimpleNamespace(vad_gate=None, cap_admission=admission))
    # 150 s of received audio; the hold began after 26 s, so 124 s were held.
    _deny(admission, 124)
    assert await _flush(runtime, monkeypatch, 1000.0, 1150.0) == 26
    assert usage[-1]['transcription_seconds'] == 26
    assert admission.held_audio_seconds == 0


async def test_session_that_resumes_meters_post_resume_seconds_unchanged(monkeypatch, usage):
    admission = _exhausted_admission()
    runtime = _runtime(SimpleNamespace(vad_gate=None, cap_admission=admission))
    _deny(admission, 50.5)
    assert await _flush(runtime, monkeypatch, 1000.0, 1060.0) == 10
    # The fractional held second carries; it never bills a resumed second twice.
    assert admission.held_audio_seconds == pytest.approx(0.5)
    admission.managed, admission.remaining = True, None
    assert await _flush(runtime, monkeypatch, 1060.0, 1120.0) == 60
    assert [call['transcription_seconds'] for call in usage] == [10, 60]


async def test_held_excess_never_goes_negative(monkeypatch, usage):
    admission = _exhausted_admission()
    runtime = _runtime(SimpleNamespace(vad_gate=None, cap_admission=admission))
    _deny(admission, 90)
    assert await _flush(runtime, monkeypatch, 1000.0, 1060.0) == 0
    assert usage == []


async def test_multichannel_held_seconds_count_wall_clock_once(monkeypatch, usage):
    admission = _exhausted_admission()
    receiver = SimpleNamespace(vad_gate=None, cap_admission=admission, channel_configs=[object(), object()])
    runtime = _runtime(receiver, multi_channel=True)
    # 40 s held on each of two channels is 40 wall-clock seconds, not 80.
    _deny(admission, 40)
    _deny(admission, 40)
    assert await _flush(runtime, monkeypatch, 1000.0, 1060.0) == 20


@pytest.mark.parametrize('admission', [None, 'unheld'])
async def test_no_hold_meters_identically(monkeypatch, usage, admission):
    receiver = SimpleNamespace(vad_gate=None)
    if admission == 'unheld':
        receiver.cap_admission = _exhausted_admission()
    runtime = _runtime(receiver)
    assert await _flush(runtime, monkeypatch, 1000.0, 1150.0) == 150
    assert usage[-1]['transcription_seconds'] == 150


def test_admission_suppression_paths_accumulate_once():
    admission = _exhausted_admission()
    admission.managed, admission.remaining = False, 0
    raw = Mock(send=Mock(return_value=True))
    admission.send(raw, b'\0' * 32000, 'parakeet', 16000)
    socket = cap.CapSocket(admission, 'parakeet', 16000, AsyncMock())  # Paused: no raw provider.
    socket.send(b'\0' * 16000)
    assert admission.held_audio_seconds == 1.5
    assert cap.record_audio.call_count == 2
    assert admission.consume_held_seconds() == 1
    assert admission.held_audio_seconds == pytest.approx(0.5)
