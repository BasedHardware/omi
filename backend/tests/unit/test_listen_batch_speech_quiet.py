"""Batch-only sockets close a conversation on speech quiet, not on audio quiet."""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import numpy as np
import pytest

from routers.listen import conversations as conversation_module
from routers.listen.conversations import LiveConversationController
from utils.stt import speech_clock as speech_clock_module
from utils.stt.speech_clock import MIN_SPEECH_WINDOWS, SpeechClock, quiet_since

NOW = datetime(2026, 11, 17, 18, 30, tzinfo=timezone.utc)
WINDOW_BYTES = 512 * 2


def _scripted_vad(monkeypatch, probs):
    probs = iter(probs)

    def run(window, state, context):
        return next(probs), state, context

    monkeypatch.setattr(speech_clock_module, 'run_vad_window', run)


def test_sustained_speech_moves_the_clock_and_a_blip_does_not(monkeypatch):
    _scripted_vad(monkeypatch, [0.9] * (MIN_SPEECH_WINDOWS - 1) + [0.1] + [0.9] * MIN_SPEECH_WINDOWS)
    clock = SpeechClock(16000, opened_at=0.0)
    clock.accept(b'\0' * WINDOW_BYTES * MIN_SPEECH_WINDOWS, 10.0)
    assert clock.last_speech_at is None
    clock.accept(b'\0' * WINDOW_BYTES * MIN_SPEECH_WINDOWS, 20.0)
    assert clock.last_speech_at == 20.0
    assert clock.started_at == 10.0


def test_partial_windows_and_odd_bytes_carry_into_the_next_frame(monkeypatch):
    _scripted_vad(monkeypatch, [0.9] * 10)
    clock = SpeechClock(16000, opened_at=0.0)
    for at in range(MIN_SPEECH_WINDOWS * 2):
        clock.accept(b'\0' * (WINDOW_BYTES // 2 + 1), float(at))
    assert clock.last_speech_at is not None
    assert not clock.failed


def test_other_sample_rates_are_resampled(monkeypatch):
    _scripted_vad(monkeypatch, [0.9] * 10)
    clock = SpeechClock(8000, opened_at=0.0)
    clock.accept(b'\0' * (WINDOW_BYTES // 2) * (MIN_SPEECH_WINDOWS + 1), 5.0)
    assert clock.last_speech_at == 5.0


def test_vad_failure_disables_the_clock_without_raising(monkeypatch):
    def boom(window, state, context):
        raise RuntimeError('onnx')

    monkeypatch.setattr(speech_clock_module, 'run_vad_window', boom)
    clock = SpeechClock(16000, opened_at=0.0)
    clock.accept(b'\0' * WINDOW_BYTES, 1.0)
    assert clock.failed
    assert quiet_since(clock, NOW, NOW.timestamp()) is None


def test_real_silero_hears_no_speech_in_silence():
    pytest.importorskip('onnxruntime')
    clock = SpeechClock(16000, opened_at=0.0)
    clock.accept(np.zeros(16000 * 3, dtype='<i2').tobytes(), 1.0)
    assert not clock.failed
    assert clock.last_speech_at is None


def _clock(*, opened, started=None, speech=None):
    clock = SpeechClock(16000, opened_at=opened.timestamp())
    clock.started_at = started.timestamp() if started else None
    clock.last_speech_at = speech.timestamp() if speech else None
    return clock


def test_quiet_since_rules():
    opened = NOW - timedelta(minutes=30)
    now = NOW.timestamp()
    assert quiet_since(None, NOW, now) is None
    # Row created by this socket: quiet counts from its last speech.
    speech = NOW - timedelta(minutes=3)
    assert quiet_since(_clock(opened=opened, speech=speech), NOW - timedelta(minutes=10), now) == speech.timestamp()
    # Rolled-over row with no speech since: stays open, never an empty close.
    assert quiet_since(_clock(opened=opened, speech=speech), NOW - timedelta(minutes=1), now) == now
    # Resumed row from an earlier socket: the resume counts as speech.
    started = NOW - timedelta(minutes=5)
    resumed = quiet_since(_clock(opened=opened, started=started), opened - timedelta(minutes=20), now)
    assert resumed == started.timestamp()


def _batch_row(created_at):
    return {
        'id': 'current',
        'status': 'in_progress',
        'record_lane_owner': 'batch_live_v1',
        'external_data': {'server_batch_only': True},
        'created_at': created_at,
        'recorded_end': created_at,
        'recorded_start': created_at,
        'started_at': created_at,
    }


async def _one_pass(monkeypatch, row, speech_clock):
    state = SimpleNamespace(
        active=True, current_conversation_id='current', last_audio_received_time=NOW.timestamp() - 1
    )
    host = SimpleNamespace(
        state=state,
        request=SimpleNamespace(uid='test-owner'),
        wait=AsyncMock(side_effect=[False, True]),
        persistence=SimpleNamespace(call=AsyncMock(return_value=row)),
        conversation_creation_timeout=120,
        receiver=SimpleNamespace(speech_clock=speech_clock),
        transcripts=SimpleNamespace(flush_speaker_assignments=AsyncMock()),
    )
    controller = LiveConversationController(host, clock=lambda: NOW)
    monkeypatch.setattr(conversation_module, 'poll_calendar', AsyncMock())
    monkeypatch.setattr(conversation_module, 'conversation_action', AsyncMock(return_value=None))
    controller._finalize_isolated = AsyncMock()
    controller.create_new_in_progress_conversation = AsyncMock()
    await asyncio.wait_for(controller.lifecycle_loop(), 1)
    return controller._finalize_isolated.await_count


@pytest.mark.asyncio
async def test_streaming_silence_after_speech_closes_the_conversation(monkeypatch):
    opened = NOW - timedelta(minutes=40)
    clock = _clock(opened=opened, started=opened, speech=NOW - timedelta(seconds=150))
    assert await _one_pass(monkeypatch, _batch_row(NOW - timedelta(minutes=20)), clock) == 1


@pytest.mark.asyncio
async def test_recent_speech_keeps_the_conversation_open(monkeypatch):
    opened = NOW - timedelta(minutes=40)
    clock = _clock(opened=opened, started=opened, speech=NOW - timedelta(seconds=30))
    assert await _one_pass(monkeypatch, _batch_row(NOW - timedelta(minutes=20)), clock) == 0


@pytest.mark.asyncio
async def test_all_silent_row_is_not_closed(monkeypatch):
    opened = NOW - timedelta(minutes=40)
    clock = _clock(opened=opened, started=opened, speech=NOW - timedelta(minutes=25))
    assert await _one_pass(monkeypatch, _batch_row(NOW - timedelta(minutes=20)), clock) == 0


@pytest.mark.asyncio
async def test_without_a_speech_clock_the_audio_clock_still_rules(monkeypatch):
    assert await _one_pass(monkeypatch, _batch_row(NOW - timedelta(minutes=20)), None) == 0


@pytest.mark.asyncio
async def test_a_failed_clock_falls_back_to_the_audio_clock(monkeypatch):
    opened = NOW - timedelta(minutes=40)
    clock = _clock(opened=opened, started=opened, speech=NOW - timedelta(seconds=150))
    clock.failed = True
    assert await _one_pass(monkeypatch, _batch_row(NOW - timedelta(minutes=20)), clock) == 0


@pytest.mark.asyncio
async def test_a_calendar_meeting_keeps_a_silent_batch_row_open_until_its_window(monkeypatch):
    opened = NOW - timedelta(minutes=40)
    clock = _clock(opened=opened, started=opened, speech=NOW - timedelta(seconds=150))
    row = _batch_row(NOW - timedelta(minutes=20))
    row['has_content'] = True
    row['external_data']['calendar_meeting_context'] = {
        'calendar_event_id': 'evt-1',
        'calendar_source': 'google',
        'start_time': (NOW - timedelta(minutes=25)).isoformat(),
        'end_time': (NOW + timedelta(minutes=30)).isoformat(),
    }
    assert await _one_pass(monkeypatch, row, clock) == 0


@pytest.mark.asyncio
async def test_a_row_created_before_the_meeting_still_gets_its_window(monkeypatch):
    opened = NOW - timedelta(minutes=40)
    clock = _clock(opened=opened, started=opened, speech=NOW - timedelta(seconds=150))
    row = _batch_row(NOW - timedelta(minutes=35))
    row['has_content'] = True
    row['external_data']['calendar_meeting_context'] = {
        'calendar_event_id': 'evt-2',
        'calendar_source': 'google',
        'start_time': (NOW - timedelta(minutes=10)).isoformat(),
        'end_time': (NOW + timedelta(minutes=30)).isoformat(),
    }
    assert await _one_pass(monkeypatch, row, clock) == 0
