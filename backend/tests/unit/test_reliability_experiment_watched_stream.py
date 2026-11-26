"""Experiment ``instant_live_text``, part 3: a batch-only phone session streams while it is watched.

Off (the default) a batch-only session opens no provider stream and its decoded audio is dropped after
the archive has it. On, the first ``client_state`` that says the transcript is on screen starts a Soniox
dial at once, the last seconds before it and the audio that arrives during the dial are sent first, and
the first report that is not visible closes the stream. The lines go to the phone only: nothing is
stored, and nothing here can end capture or change who owns the record.
"""

import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from config import reliability_experiments
from routers.listen import watched_stream as module
from routers.listen.receiver import ListenReceiver
from utils.stt.streaming import STTService

EXPERIMENT = 'instant_live_text'
FRAME = b'\x01\x00' * 160
VISIBLE = {'foreground': True, 'transcript_visible': True}
HIDDEN = {'foreground': True, 'transcript_visible': False}


def build(monkeypatch, *, experiment=True):
    if experiment:
        monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    else:
        monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    lifetime = []
    websocket = SimpleNamespace(send_json=AsyncMock())
    stored = Mock()
    host = SimpleNamespace(
        request=SimpleNamespace(uid='owner', local_preview=False, sample_rate=16000, websocket=websocket),
        client_device_context=SimpleNamespace(platform='android'),
        server_batch_only=True,
        batch_record_capture={'record_lane_owner': 'batch_live_v1', 'server_batch_only': True},
        use_custom_stt=False,
        is_multi_channel=False,
        state=SimpleNamespace(active=True, current_conversation_id='conversation', first_audio_byte_timestamp=None),
        stt_service=STTService.parakeet,
        stt_model='parakeet',
        stt_language='en',
        language_profile=None,
        transcripts=SimpleNamespace(enqueue=stored, cache=SimpleNamespace(get=AsyncMock(return_value=None))),
        spawn=lambda coro, **kwargs: asyncio.create_task(coro),
        wait=AsyncMock(return_value=True),
        task_supervisor=SimpleNamespace(
            create_lifetime_task=lambda coro, **kwargs: (lifetime.append(coro), coro.close())
        ),
    )
    raw = SimpleNamespace(send=Mock(return_value=True), finish=Mock(), is_connection_dead=False)
    dial = AsyncMock(return_value=raw)
    monkeypatch.setattr(module, 'process_audio_soniox', dial)
    aborted = AsyncMock()
    monkeypatch.setattr(module, 'abort_replay_socket', aborted)
    receiver = SimpleNamespace(host=host, stt_socket=None, _stt_buffer_start_sample=None, _enqueue_stt_segments=stored)
    return SimpleNamespace(
        receiver=receiver,
        host=host,
        raw=raw,
        dial=dial,
        aborted=aborted,
        websocket=websocket,
        stored=stored,
        lifetime=lifetime,
    )


@pytest.fixture
def h(monkeypatch):
    built = build(monkeypatch)
    module.attach_watched_stream(built.receiver)
    built.watched = built.receiver.watched_stream
    return built


async def flush(h, data=FRAME):
    buffer = bytearray(data)
    await ListenReceiver._flush_stt_buffer(h.receiver, buffer)
    assert buffer == b''


async def settle(h):
    for name in ('opening', 'sender'):
        task = getattr(h.watched, name)
        if task is not None:
            await asyncio.wait_for(task, timeout=1)


def word(text, start, end, speaker='SPEAKER_00'):
    return {'text': text, 'start': start, 'end': end, 'speaker': speaker, 'is_user': False}


def sent(h):
    """Every line the phone was sent, in order, as (id, text)."""
    return [(line['id'], line['text']) for call in h.websocket.send_json.await_args_list for line in call.args[0]]


async def test_off_attaches_nothing_and_the_buffer_is_only_cleared(monkeypatch):
    h = build(monkeypatch, experiment=False)
    module.attach_watched_stream(h.receiver)
    module.observe_client_state(h.receiver, VISIBLE)
    assert not hasattr(h.receiver, 'watched_stream')
    assert not hasattr(h.receiver, '_watched_last_state')
    assert h.lifetime == []
    await flush(h)
    h.dial.assert_not_awaited()


async def test_visible_report_dials_at_once_without_audio_or_dwell(h):
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    h.dial.assert_awaited_once()
    assert h.watched.socket is h.raw
    # The session itself is left as it was: provider selection, custody, and no session-level stream.
    assert h.host.stt_service == STTService.parakeet and h.host.stt_model == 'parakeet'
    assert h.host.server_batch_only is True
    assert h.host.batch_record_capture['record_lane_owner'] == 'batch_live_v1'
    assert h.receiver.stt_socket is None


async def test_audio_during_the_dial_is_sent_first_then_live_audio_and_hide_closes(h):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        await release.wait()
        return h.raw

    h.dial.side_effect = slow
    module.observe_client_state(h.receiver, VISIBLE)
    first, second, third = b'\x01\x00' * 160, b'\x02\x00' * 160, b'\x03\x00' * 160
    # The receive loop never waits on the dial.
    await asyncio.wait_for(flush(h, first), timeout=1)
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.wait_for(flush(h, second), timeout=1)
    h.raw.send.assert_not_called()
    release.set()
    await settle(h)
    await flush(h, third)
    assert [call.args[0] for call in h.raw.send.call_args_list] == [first, second, third]

    words = h.dial.call_args.args[0]
    words([word('synthetic', 0.0, 0.5)])
    await settle(h)
    assert [text for _, text in sent(h)] == ['synthetic']

    module.observe_client_state(h.receiver, HIDDEN)
    h.raw.finish.assert_called_once()
    assert h.watched.socket is None
    words([word('late', 1.0, 1.5)])
    await settle(h)
    assert [text for _, text in sent(h)] == ['synthetic']
    await flush(h)
    assert h.dial.await_count == 1
    assert h.raw.send.call_count == 3


async def test_words_become_lines_sent_to_the_phone_and_are_never_stored(h):
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    await flush(h)
    words = h.dial.call_args.args[0]
    words([word('Hello', 0.0, 0.4)])
    await settle(h)
    words([word('there.', 0.5, 0.9)])
    await settle(h)
    words([word('Hi.', 1.0, 1.3, speaker='SPEAKER_01'), word('Later', 9.0, 9.4, speaker='SPEAKER_01')])
    await settle(h)
    lines = sent(h)
    # One line grows under one id; another speaker, or a long pause, starts a new line.
    assert [text for _, text in lines] == ['Hello', 'Hello there.', 'Hi.', 'Later']
    assert lines[0][0] == lines[1][0]
    assert len({line_id for line_id, _ in lines}) == 3
    first = h.websocket.send_json.await_args_list[0].args[0][0]
    assert first['stt_provider'] == 'soniox' and first['speaker'] == 'SPEAKER_00' and first['is_user'] is False
    # Display only: neither the transcript processor nor the receiver's stored-segment path sees them.
    h.stored.assert_not_called()


async def test_hide_during_the_dial_wins_and_the_candidate_is_aborted(h):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        await release.wait()
        return h.raw

    h.dial.side_effect = slow
    module.observe_client_state(h.receiver, VISIBLE)
    await asyncio.wait_for(started.wait(), timeout=1)
    module.observe_client_state(h.receiver, HIDDEN)
    release.set()
    await settle(h)
    assert h.watched.socket is None
    h.aborted.assert_awaited_once_with(h.raw, timeout=2)
    h.raw.send.assert_not_called()
    assert h.host.state.active


async def test_the_last_seconds_before_opening_are_sent_first(h):
    module.observe_client_state(h.receiver, HIDDEN)
    for index in range(500):  # Five seconds of audio before anyone looks.
        await flush(h, bytes([index % 250 + 1, 0]) * 160)
    h.dial.assert_not_awaited()
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    await flush(h, b'\xff\x00' * 160)
    audio = [call.args[0] for call in h.raw.send.call_args_list]
    kept = int(module.PRE_ROLL_SECONDS * 100)
    # Only the newest three seconds were kept, oldest first, then the live buffer.
    assert len(audio) == kept + 1
    assert audio[0] == bytes([(500 - kept) % 250 + 1, 0]) * 160 and audio[-1] == b'\xff\x00' * 160


async def test_lines_are_timed_from_the_conversation_start(h):
    started = time.time() - 60
    h.host.transcripts.cache.get.return_value = {'started_at': datetime.fromtimestamp(started, tz=timezone.utc)}
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    await flush(h)  # The stream's first frame is captured now: 60 s into the conversation.
    words = h.dial.call_args.args[0]
    words([word('synthetic', 0.25, 0.75)])
    await settle(h)
    line = h.websocket.send_json.await_args_list[0].args[0][0]
    assert line['start'] == pytest.approx(60.25, abs=1.0) and line['end'] - line['start'] == pytest.approx(0.5)
    h.host.transcripts.cache.get.assert_awaited_with('conversation')


async def test_a_new_conversation_reopens_the_stream_against_its_own_clock(h):
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    await flush(h)
    h.host.state.current_conversation_id = 'next-conversation'
    await flush(h)
    h.raw.finish.assert_called_once()
    await settle(h)
    assert h.dial.await_count == 2 and h.watched.conversation_id == 'next-conversation'


async def test_a_session_outside_the_rule_keeps_no_audio(h):
    h.host.local_preview_batch = True
    for _ in range(50):
        await flush(h)
    assert not h.watched.pending and h.watched.pending_bytes == 0


@pytest.mark.parametrize(
    'change',
    [
        lambda host: setattr(host, 'local_preview_batch', True),  # Phone-file session.
        lambda host: setattr(host, 'use_custom_stt', True),
        lambda host: setattr(host, 'is_multi_channel', True),
        lambda host: setattr(host.client_device_context, 'platform', 'macos'),
        lambda host: host.batch_record_capture.update(record_lane_owner=None),
    ],
)
async def test_sessions_outside_the_rule_never_dial(h, change):
    change(h.host)
    module.observe_client_state(h.receiver, VISIBLE)
    await flush(h)
    await settle(h)
    h.dial.assert_not_awaited()
    assert h.watched.socket is None


@pytest.mark.parametrize(
    'report',
    [
        {'foreground': False, 'transcript_visible': True},  # Contradictory: not trusted.
        {'foreground': True},  # Malformed.
        {'foreground': True, 'transcript_visible': False},
    ],
)
async def test_only_a_well_formed_visible_report_opens_the_stream(h, report):
    module.observe_client_state(h.receiver, report)
    await flush(h)
    await settle(h)
    h.dial.assert_not_awaited()


async def test_a_phone_whose_preview_request_was_refused_still_gets_the_stream(h):
    h.host.request.local_preview = True  # Asked for the on-phone preview...
    h.host.local_preview_batch = False  # ...and was not granted it, so its audio is on the socket.
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    h.dial.assert_awaited_once()


async def test_a_stale_visible_report_closes_the_stream(h):
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    assert h.watched.socket is h.raw
    h.watched.reported_at -= module.STALE_REPORT_SECONDS + 1
    await flush(h)
    h.raw.finish.assert_called_once()
    assert h.watched.socket is None


async def test_a_dead_provider_is_redialled_a_few_times_then_waits_for_the_page_to_reopen(h, monkeypatch):
    monkeypatch.setattr(module, 'RETRY_SECONDS', 0.0)
    module.observe_client_state(h.receiver, VISIBLE)
    for attempt in range(module.MAX_FAILURES):
        await flush(h)
        await settle(h)
        assert h.watched.socket is h.raw, attempt
        h.raw.is_connection_dead = True
        await flush(h)
        assert h.watched.socket is None
        h.raw.is_connection_dead = False
    assert h.watched.failed
    await flush(h)
    await settle(h)
    assert h.dial.await_count == module.MAX_FAILURES
    assert h.host.state.active
    # Closing and opening the page starts afresh.
    module.observe_client_state(h.receiver, HIDDEN)
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    assert h.dial.await_count == module.MAX_FAILURES + 1 and h.watched.socket is h.raw


async def test_a_dial_error_never_reaches_the_capture_loop(h):
    h.dial.side_effect = RuntimeError('synthetic dial failure')
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    await flush(h)
    assert h.watched.socket is None and h.watched.failures >= 1
    assert h.host.state.active


async def test_a_phone_that_has_gone_does_not_break_the_stream_or_capture(h):
    h.websocket.send_json.side_effect = RuntimeError('synthetic send after close')
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    await flush(h)
    h.dial.call_args.args[0]([word('synthetic', 0.0, 0.5)])
    await settle(h)
    assert h.host.state.active


async def test_a_report_that_arrived_before_the_session_was_batch_only_is_replayed(monkeypatch):
    h = build(monkeypatch)
    module.observe_client_state(h.receiver, VISIBLE)  # No stream object yet.
    module.attach_watched_stream(h.receiver)
    h.watched = h.receiver.watched_stream
    await settle(h)
    h.dial.assert_awaited_once()
    assert len(h.lifetime) == 1


async def test_shutdown_closes_the_stream_and_drains_it(h):
    module.observe_client_state(h.receiver, VISIBLE)
    await settle(h)
    await h.watched.shutdown()
    h.raw.finish.assert_called_once()
    h.aborted.assert_awaited_once_with(h.raw, timeout=2)
    assert h.watched.socket is None
