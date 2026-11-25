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


@pytest.fixture
def rotation_on(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_RECORDING_ROTATION', 'on')


def _v3_row(age_seconds, **changes):
    row = _batch_row(NOW - timedelta(seconds=age_seconds))
    row['recording'] = True
    row.update(changes)
    return row


async def _rotation_pass(monkeypatch, row, speech_clock, *, successor='next', create_error=None):
    """One lifecycle tick. Returns (stages finalized, creates, controller)."""
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
        recording_session_id='session-1',
        batch_record_capture={'id': 'current'},
        recording_session_ids_by_conversation={'current': 'session-1'},
    )
    controller = LiveConversationController(host, clock=lambda: NOW)
    monkeypatch.setattr(conversation_module, 'poll_calendar', AsyncMock())
    stages = []

    async def finalize(fn, conversation_id, *, stage):
        stages.append(stage)

    async def create(*, rollover=False, supersede=None):
        assert supersede in (None, 'current')
        host.recording_session_id = 'session-2'
        host.batch_record_capture = {'id': 'unbound'}
        host.recording_session_ids_by_conversation['unbound'] = 'session-2'
        if create_error:
            raise create_error
        state.current_conversation_id = successor

    async def seal(conversation_id):
        stages.append('v3_rotation')
        return True

    controller._finalize_isolated = finalize
    controller._seal_rotated_recording = seal
    controller.create_new_in_progress_conversation = AsyncMock(side_effect=create)
    await asyncio.wait_for(controller.lifecycle_loop(), 1)
    return stages, controller.create_new_in_progress_conversation.await_count, controller


def _speaking(since_speech):
    opened = NOW - timedelta(minutes=40)
    return _clock(opened=opened, started=opened, speech=NOW - timedelta(seconds=since_speech))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('age', 'since_speech', 'rotates'),
    [
        (190, 2, True),  # past the rotation age, at a pause
        (190, 0.5, False),  # past the age, mid-speech
        (150, 30, False),  # quiet but younger than the rotation age
        (180, 1.5, True),  # exactly the age and exactly the pause
        (179.9, 1.5, False),
        (190, 1.49, False),
        (300, 0, True),  # exactly the hard cap with continuous speech
        (299.9, 0, False),
    ],
)
async def test_v3_recording_rotates_at_a_pause_or_the_cap(monkeypatch, rotation_on, age, since_speech, rotates):
    stages, creates, _ = await _rotation_pass(monkeypatch, _v3_row(age), _speaking(since_speech))
    assert (stages, creates) == ((['v3_rotation'], 1) if rotates else ([], 0))


@pytest.mark.asyncio
async def test_rotation_ages_are_env_tunable(monkeypatch, rotation_on):
    monkeypatch.setenv('CONVERSATIONS_V3_ROTATION_MIN_SECONDS', '120')
    monkeypatch.setenv('CONVERSATIONS_V3_ROTATION_MAX_SECONDS', '240')
    assert (await _rotation_pass(monkeypatch, _v3_row(130), _speaking(2)))[0] == ['v3_rotation']
    monkeypatch.setenv('CONVERSATIONS_V3_ROTATION_MAX_SECONDS', '30')  # invalid pair keeps 180/300
    assert (await _rotation_pass(monkeypatch, _v3_row(130), _speaking(2)))[0] == []


@pytest.mark.asyncio
async def test_v3_row_with_no_speech_of_its_own_never_rotates(monkeypatch, rotation_on):
    assert (await _rotation_pass(monkeypatch, _v3_row(305), _speaking(310)))[1] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('since_speech', [2, 0])
async def test_legacy_row_never_rotates(monkeypatch, rotation_on, since_speech):
    row = _batch_row(NOW - timedelta(minutes=20))
    assert (await _rotation_pass(monkeypatch, row, _speaking(since_speech)))[1] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('failed', [True, False])
@pytest.mark.parametrize(('age', 'rotates'), [(190, False), (300, True)])
async def test_failed_or_absent_clock_uses_only_the_cap(monkeypatch, rotation_on, failed, age, rotates):
    clock = None
    if failed:
        clock = _speaking(2)
        clock.failed = True
    assert (await _rotation_pass(monkeypatch, _v3_row(age), clock))[1] == int(rotates)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', [None, 'off', 'cohort'])
async def test_off_is_the_old_lifecycle(monkeypatch, mode):
    if mode is None:
        monkeypatch.delenv('CONVERSATIONS_V3_RECORDING_ROTATION', raising=False)
    else:
        monkeypatch.setenv('CONVERSATIONS_V3_RECORDING_ROTATION', mode)
    monkeypatch.setattr('config.conversations_v3.in_rollout_cohort', lambda uid, name: False)
    # Speech at the cap: no rotation. Quiet: the existing seal, through the existing path.
    assert await _one_pass(monkeypatch, _v3_row(300), _speaking(0)) == 0
    assert await _one_pass(monkeypatch, _v3_row(300), _speaking(150)) == 1


@pytest.mark.asyncio
async def test_cohort_mode_rotates_only_members(monkeypatch):
    monkeypatch.setenv('CONVERSATIONS_V3_RECORDING_ROTATION', 'cohort')
    members = set()
    monkeypatch.setattr(
        'config.conversations_v3.in_rollout_cohort',
        lambda uid, name: name == 'v3-recording-rotation' and uid in members,
    )
    assert (await _rotation_pass(monkeypatch, _v3_row(190), _speaking(2)))[1] == 0
    members.add('test-owner')
    assert (await _rotation_pass(monkeypatch, _v3_row(190), _speaking(2)))[1] == 1


@pytest.mark.asyncio
async def test_a_failed_successor_keeps_the_recording_and_backs_off(monkeypatch, rotation_on):
    stages, creates, controller = await _rotation_pass(
        monkeypatch, _v3_row(190), _speaking(2), create_error=RuntimeError('firestore')
    )
    assert (stages, creates) == ([], 1)
    assert controller.host.state.current_conversation_id == 'current'
    assert controller.host.recording_session_id == 'session-1'
    assert controller.host.batch_record_capture == {'id': 'current'}
    assert controller.host.recording_session_ids_by_conversation == {'current': 'session-1'}
    redis = [
        c
        for c in controller.host.persistence.call.await_args_list
        if c.args[0].__name__ == 'set_in_progress_conversation_id'
    ]
    assert [c.args[1:] for c in redis] == [('test-owner', 'current')]
    assert controller._rotation_retry_at == NOW + timedelta(seconds=60)
    assert not controller._v3_rotation_due(_v3_row(190))
    controller._rotation_retry_at = NOW - timedelta(seconds=1)
    assert controller._v3_rotation_due(_v3_row(190))


@pytest.mark.asyncio
async def test_a_successor_that_resumes_the_same_row_does_not_seal_it(monkeypatch, rotation_on):
    stages, creates, controller = await _rotation_pass(monkeypatch, _v3_row(190), _speaking(2), successor='current')
    assert (stages, creates) == ([], 1) and controller._rotation_retry_at is not None


@pytest.mark.asyncio
async def test_a_refused_seal_does_not_loop(monkeypatch, rotation_on):
    # process_conversation returning False leaves the retired row for stale/quiet recovery;
    # the socket already writes to the successor, so the next tick cannot rotate it again.
    row = _v3_row(190)
    host = SimpleNamespace(
        state=SimpleNamespace(active=True, current_conversation_id='current', last_audio_received_time=NOW.timestamp()),
        request=SimpleNamespace(uid='test-owner'),
        wait=AsyncMock(side_effect=[False, False, True]),
        persistence=SimpleNamespace(call=AsyncMock(return_value=row)),
        conversation_creation_timeout=120,
        receiver=SimpleNamespace(speech_clock=_speaking(2)),
        transcripts=SimpleNamespace(flush_speaker_assignments=AsyncMock()),
        recording_session_id='session-1',
    )
    controller = LiveConversationController(host, clock=lambda: NOW)
    monkeypatch.setattr(conversation_module, 'poll_calendar', AsyncMock())
    controller.process_conversation = AsyncMock(return_value=False)
    fresh = _v3_row(5)

    async def create(*, rollover=False, supersede=None):
        host.state.current_conversation_id = 'next'
        host.persistence.call.return_value = fresh

    controller.create_new_in_progress_conversation = AsyncMock(side_effect=create)
    await asyncio.wait_for(controller.lifecycle_loop(), 1)
    controller.process_conversation.assert_awaited_once_with('current')
    assert controller.create_new_in_progress_conversation.await_count == 1
    assert host.persistence.call.await_args_list[1].args[1:] == (
        'test-owner',
        'current',
        {'v3_rotation_cap_seconds': 300.0},
    )


@pytest.mark.asyncio
async def test_user_stop_blocks_rotation(monkeypatch, rotation_on):
    stages = []
    state = SimpleNamespace(
        active=True,
        current_conversation_id='current',
        last_audio_received_time=NOW.timestamp(),
        finalization_reason='user_stop',
    )
    host = SimpleNamespace(state=state, request=SimpleNamespace(uid='test-owner'))
    controller = LiveConversationController(host, clock=lambda: NOW)
    host.receiver = SimpleNamespace(speech_clock=_speaking(2))
    assert not controller._v3_rotation_due(_v3_row(190))
    state.finalization_reason = None
    assert controller._v3_rotation_due(_v3_row(190))
    assert not stages


@pytest.mark.asyncio
async def test_a_quiet_seal_tick_wins_over_rotation(monkeypatch, rotation_on):
    # Quiet already closes the row through the existing path; rotation never runs on the same tick.
    stages, creates, _ = await _rotation_pass(monkeypatch, _v3_row(300), _speaking(150))
    assert (stages, creates) == (['lifecycle_rollover'], 1)


@pytest.mark.asyncio
async def test_a_producer_boundary_takes_the_existing_path(monkeypatch, rotation_on):
    row = _v3_row(300, listen_batch_producer={'version': 1, 'boundary_at': NOW - timedelta(seconds=1)})
    stages, creates, _ = await _rotation_pass(monkeypatch, row, _speaking(2))
    assert (stages, creates) == (['lifecycle_rollover'], 1)


@pytest.mark.asyncio
async def test_a_calendar_meeting_does_not_block_v3_rotation(monkeypatch, rotation_on):
    # v3 conversations come from transcript windows; the successor recording inherits the meeting.
    row = _v3_row(190)
    row['has_content'] = True
    row['external_data']['calendar_meeting_context'] = {
        'calendar_event_id': 'evt-3',
        'calendar_source': 'google',
        'start_time': (NOW - timedelta(minutes=10)).isoformat(),
        'end_time': (NOW + timedelta(minutes=30)).isoformat(),
    }
    assert (await _rotation_pass(monkeypatch, row, _speaking(2)))[0] == ['v3_rotation']


@pytest.mark.asyncio
async def test_a_resumed_v3_row_rotates_on_speech_this_socket_heard(monkeypatch, rotation_on):
    clock = _clock(
        opened=NOW - timedelta(minutes=2), started=NOW - timedelta(minutes=2), speech=NOW - timedelta(seconds=2)
    )
    assert (await _rotation_pass(monkeypatch, _v3_row(600), clock))[0] == ['v3_rotation']


def _sealing_controller(process, token=True):
    clock = {'now': NOW}
    host = SimpleNamespace(
        state=SimpleNamespace(active=True, current_conversation_id='next'),
        request=SimpleNamespace(uid='test-owner'),
        persistence=SimpleNamespace(call=AsyncMock(return_value=None)),
        receiver=SimpleNamespace(),
    )
    controller = LiveConversationController(host, clock=lambda: clock['now'])
    controller.process_conversation = process
    controller._unsealed_rotations['old'] = (0, NOW)
    if token:
        controller._batch_producer_tokens['old'] = 'token'
    return controller, clock


@pytest.mark.asyncio
async def test_a_refused_seal_retries_with_backoff_then_hands_off(monkeypatch):
    controller, clock = _sealing_controller(AsyncMock(return_value=False))
    waits = []
    for _ in range(conversation_module.ROTATION_SEAL_ATTEMPTS):
        await controller._seal_rotated()
        if 'old' in controller._unsealed_rotations:
            attempts, due = controller._unsealed_rotations['old']
            waits.append((due - clock['now']).total_seconds())
            await controller._seal_rotated()  # not yet due: no attempt
            clock['now'] = due
    assert waits == [15, 30, 60, 120]
    assert 'old' not in controller._batch_producer_tokens  # handed off: no longer counts toward the cap
    assert controller.process_conversation.await_count == conversation_module.ROTATION_SEAL_ATTEMPTS
    assert controller._unsealed_rotations == {}


@pytest.mark.asyncio
async def test_a_raising_seal_is_retried_and_an_admitted_one_is_dropped(monkeypatch):
    controller, clock = _sealing_controller(AsyncMock(side_effect=[RuntimeError('firestore'), True]))
    controller._batch_producer_tokens['old'] = 'token'
    await controller._seal_rotated()
    assert controller._unsealed_rotations['old'][0] == 1
    clock['now'] += timedelta(seconds=15)
    await controller._seal_rotated()
    assert controller._unsealed_rotations == {} and 'old' not in controller._batch_producer_tokens


@pytest.mark.asyncio
async def test_teardown_drains_pending_seals_once(monkeypatch):
    controller, clock = _sealing_controller(AsyncMock(return_value=False))
    controller._unsealed_rotations['old'] = (2, NOW + timedelta(minutes=5))  # not due, still attempted
    await controller.drain_rotations()
    controller.process_conversation.assert_awaited_once_with('old')
    assert controller._unsealed_rotations == {}


@pytest.mark.asyncio
async def test_ownership_loss_during_a_rotation_closes_the_socket(monkeypatch, rotation_on):
    from fastapi import WebSocketException

    with pytest.raises(WebSocketException):
        await _rotation_pass(
            monkeypatch, _v3_row(190), _speaking(2), create_error=WebSocketException(code=1013, reason='limit')
        )


@pytest.mark.asyncio
async def test_a_reconnect_protocol_row_never_rotates(monkeypatch, rotation_on):
    row = _v3_row(300, listen_batch_producer={'version': 1, 'token': 't', 'phase': 'active'})
    stages, creates, _ = await _rotation_pass(monkeypatch, row, _speaking(2))
    assert (stages, creates) == ([], 0)


@pytest.mark.asyncio
async def test_a_failing_redis_restore_never_masks_ownership_loss(monkeypatch, rotation_on):
    from fastapi import WebSocketException

    from database import redis_db

    host = SimpleNamespace(
        state=SimpleNamespace(current_conversation_id='current', active=True),
        request=SimpleNamespace(uid='test-owner'),
        transcripts=SimpleNamespace(flush_speaker_assignments=AsyncMock()),
        recording_session_id='session-1',
        recording_session_ids_by_conversation={'current': 'session-1'},
    )

    async def call(fn, *args, **kwargs):
        if fn is redis_db.set_in_progress_conversation_id:
            raise RuntimeError('redis down')
        return True

    host.persistence = SimpleNamespace(call=call)
    controller = LiveConversationController(host, clock=lambda: NOW)

    async def create(*, rollover=False, supersede=None):
        host.recording_session_ids_by_conversation['unbound'] = 'session-2'
        raise WebSocketException(code=1013, reason='limit')

    controller.create_new_in_progress_conversation = create
    with pytest.raises(WebSocketException):
        await controller._rotate_v3_recording('current')
    assert host.recording_session_ids_by_conversation == {'current': 'session-1'}


@pytest.mark.asyncio
async def test_a_reconnect_protocol_skip_is_counted_once_per_row(monkeypatch, rotation_on):
    outcomes = []
    monkeypatch.setattr(conversation_module, 'record_rotation', outcomes.append)
    host = SimpleNamespace(
        state=SimpleNamespace(current_conversation_id='current', last_audio_received_time=NOW.timestamp()),
        request=SimpleNamespace(uid='test-owner'),
        receiver=SimpleNamespace(speech_clock=_speaking(2)),
    )
    controller = LiveConversationController(host, clock=lambda: NOW)
    row = _v3_row(300, listen_batch_producer={'version': 1, 'token': 't', 'phase': 'active'})
    assert not controller._v3_rotation_due(row) and not controller._v3_rotation_due(row)
    assert outcomes == ['skipped_producer']


def test_producer_skips_stay_bounded(monkeypatch, rotation_on):
    host = SimpleNamespace(state=SimpleNamespace(), request=SimpleNamespace(uid='test-owner'))
    controller = LiveConversationController(host, clock=lambda: NOW)
    for index in range(100):
        controller._skipped_for_producer({'id': f'r{index}', 'listen_batch_producer': {'version': 1}})
    assert list(controller._producer_skips) == [f'r{index}' for index in range(36, 100)]


@pytest.mark.asyncio
async def test_ownership_loss_skips_the_redis_restore(monkeypatch):
    from fastapi import WebSocketException

    calls = []
    host = SimpleNamespace(
        request=SimpleNamespace(uid='test-owner'),
        persistence=SimpleNamespace(call=AsyncMock(side_effect=lambda fn, *a, **kw: calls.append(fn.__name__))),
    )
    controller = LiveConversationController(host, clock=lambda: NOW)
    await controller._clear_failed_successor('current', {}, WebSocketException(code=1013))
    assert calls == []
    await controller._clear_failed_successor('current', {}, RuntimeError('firestore'))
    assert calls == ['set_in_progress_conversation_id']
