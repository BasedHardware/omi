"""STT cap held (untranscribed) live audio is not metered as transcription seconds.

Held audio is billed once, by recovery, when it is actually transcribed. Seconds
before the hold and after a resume meter exactly as before.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from routers.listen.runtime import ListenSessionRuntime
from utils import stt_cap_dispatch as cap
from utils.analytics import billable_transcription_seconds
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


def _runtime(admission):
    runtime = object.__new__(ListenSessionRuntime)
    runtime.request = SimpleNamespace(uid='synthetic')
    runtime.use_custom_stt = False
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
    runtime.receiver = SimpleNamespace(vad_gate=None)
    if admission is not None:
        runtime.receiver.cap_admission = admission
    return runtime


async def _flush(runtime, monkeypatch, start, end, *, now=None, resume=None, final=False):
    import routers.listen.runtime as runtime_module

    runtime.state.last_usage_record_timestamp = start
    runtime.state.last_audio_received_time = end
    runtime.state.last_audio_resume_time = resume
    monkeypatch.setattr(runtime_module.time, 'time', lambda: now if now is not None else end)
    return await runtime._flush_usage(final=final)


def _hold(admission, start, end, frame=0.1, spacing=None):
    """Receiver-denied frames received from `start` to `end` (wall clock)."""
    spacing = spacing or frame
    received = start + spacing
    while received <= end + 1e-9:
        admission.note_held(received, frame)
        received += spacing


async def test_session_crossing_into_hold_meters_only_pre_hold_seconds(monkeypatch, usage):
    admission = cap.LiveAdmission('synthetic')
    runtime = _runtime(admission)
    # 150 s of received audio; the hold began after 26 s.
    _hold(admission, 1026.0, 1150.0)
    assert await _flush(runtime, monkeypatch, 1000.0, 1150.0) == 26
    assert usage[-1]['transcription_seconds'] == 26
    assert admission.held_spans == []


async def test_session_that_resumes_meters_post_resume_seconds_unchanged(monkeypatch, usage):
    admission = cap.LiveAdmission('synthetic')
    runtime = _runtime(admission)
    _hold(admission, 1010.0, 1060.0)
    assert await _flush(runtime, monkeypatch, 1000.0, 1060.0) == 10
    assert await _flush(runtime, monkeypatch, 1060.0, 1120.0) == 60
    assert [call['transcription_seconds'] for call in usage] == [10, 60]


async def test_late_socket_suppression_of_admitted_audio_never_reduces_a_later_window(monkeypatch, usage):
    admission = cap.LiveAdmission('synthetic')
    runtime = _runtime(admission)
    assert await _flush(runtime, monkeypatch, 1000.0, 1060.0) == 60
    # Queued audio admitted before the t=60 flush is suppressed by the provider pump afterwards.
    raw = Mock(send=Mock(return_value=True), is_connection_dead=False)
    socket = cap.CapSocket(admission, 'soniox', 16000, AsyncMock(), raw)
    admission.managed, admission.remaining = False, 0
    assert socket.suppress(b'\0' * 32000 * 20) is True
    admission.send(raw, b'\0' * 32000, 'soniox', 16000)
    assert admission.held_spans == []
    admission.managed, admission.remaining = True, None
    assert await _flush(runtime, monkeypatch, 1060.0, 1120.0) == 60


async def test_burst_of_held_backlog_counts_its_arrival_wall_time_only(monkeypatch, usage):
    admission = cap.LiveAdmission('synthetic')
    runtime = _runtime(admission)
    # 20 s transcribed in realtime, then 50 s of buffered audio dumped in 5 s.
    _hold(admission, 1020.0, 1025.0, frame=0.1, spacing=0.01)
    assert await _flush(runtime, monkeypatch, 1000.0, 1025.0) == 19  # One 0.1 s frame of rounding.


async def test_held_wall_time_is_not_multiplied_or_divided_by_channels(monkeypatch, usage):
    both = cap.LiveAdmission('synthetic')
    _hold(both, 1000.0, 1060.0)
    _hold(both, 1000.0, 1060.0)  # Second channel, same wall interval.
    assert await _flush(_runtime(both), monkeypatch, 1000.0, 1060.0) == 0
    one = cap.LiveAdmission('synthetic')
    _hold(one, 1030.0, 1060.0)  # Only one of two configured channels sends.
    assert await _flush(_runtime(one), monkeypatch, 1000.0, 1060.0) == 30


async def test_held_span_past_the_window_carries_to_the_next_flush(monkeypatch, usage):
    admission = cap.LiveAdmission('synthetic')
    runtime = _runtime(admission)
    _hold(admission, 1050.0, 1070.0)
    assert await _flush(runtime, monkeypatch, 1000.0, 1060.0) == 50
    assert await _flush(runtime, monkeypatch, 1060.0, 1120.0) == 50
    assert admission.held_spans == []


async def test_resume_floor_and_idle_clamp_bound_the_subtraction(monkeypatch, usage):
    admission = cap.LiveAdmission('synthetic')
    runtime = _runtime(admission)
    # Held audio before an idle gap is outside the resumed window and is released.
    _hold(admission, 990.0, 1000.0)
    _hold(admission, 1040.0, 1050.0)
    seconds = await _flush(runtime, monkeypatch, 995.0, 1050.0, now=1080.0, resume=1020.0)
    assert seconds == 20  # 1020..1050 received, 1040..1050 held; 1050..1080 idle.
    assert admission.held_spans == []


async def test_final_flush_excludes_held_tail(monkeypatch, usage):
    admission = cap.LiveAdmission('synthetic')
    runtime = _runtime(admission)
    _hold(admission, 1005.0, 1030.0)
    assert await _flush(runtime, monkeypatch, 1000.0, 1030.0, final=True) == 5


@pytest.mark.parametrize('admission', [None, 'unheld'])
@pytest.mark.parametrize(
    'start,end,now,resume',
    [(1000.0, 1150.0, 1150.0, None), (1000.3, 1061.9, 1070.0, 1010.7), (1000.0, None, 1059.5, None)],
)
async def test_no_hold_meters_identically(monkeypatch, usage, admission, start, end, now, resume):
    runtime = _runtime(cap.LiveAdmission('synthetic') if admission == 'unheld' else None)
    expected = billable_transcription_seconds(start, end, now, resume)
    assert await _flush(runtime, monkeypatch, start, end, now=now, resume=resume) == expected


def test_spans_merge_and_stay_bounded(monkeypatch):
    admission = cap.LiveAdmission('synthetic')
    _hold(admission, 1000.0, 1010.0)
    assert admission.held_spans == [[pytest.approx(1000.0), pytest.approx(1010.0)]]
    monkeypatch.setattr(cap, 'MAX_HELD_SPANS', 3)
    for start in (1020.0, 1030.0, 1040.0, 1050.0):
        admission.note_held(start + 1, 1)
    assert len(admission.held_spans) == 3  # Oldest dropped: billed as before, never over-subtracted.
