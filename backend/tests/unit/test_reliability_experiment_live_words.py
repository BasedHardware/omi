"""Experiment ``vendor_recognizer_on_opened_app``: the display-only ``/v4/live-words`` connection.

Off (the default) the endpoint refuses before accepting. On, audio the phone sends is forwarded to
Soniox in order (what arrived during the dial first), the provider's words come back as lines timed in
seconds of audio from the connection's first frame, a second connection from the same app install
replaces the first. Silence closes only the provider stream: the phone's connection stays open and the
next audio dials again; a connection without audio for much longer is closed. Nothing is stored and no
text is logged.
"""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import WebSocketException

from config import reliability_experiments
from routers.listen import live_words as module
from routers.listen import watched_stream

EXPERIMENT = 'vendor_recognizer_on_opened_app'
FRAME = b'\x01\x00' * 1600  # 100 ms


class Phone:
    """The phone's end of the connection: a queue of messages to receive, a record of what was sent."""

    def __init__(self, install='abc'):
        self.headers = {'x-app-platform': 'ios', 'x-device-id-hash': install}
        self.inbox: asyncio.Queue = asyncio.Queue()
        self.sent: list[dict] = []
        self.accepted = False
        self.closed: tuple[int, str] | None = None

    async def accept(self):
        self.accepted = True

    async def receive(self):
        return await self.inbox.get()

    async def send_text(self, text):
        self.sent.append(json.loads(text))

    async def close(self, code=1000, reason=''):
        self.closed = (code, reason)

    def audio(self, data=FRAME):
        self.inbox.put_nowait({'type': 'websocket.receive', 'bytes': data})

    def leave(self):
        self.inbox.put_nowait({'type': 'websocket.disconnect'})

    def lines(self):
        return [line for message in self.sent if message['type'] == 'lines' for line in message['lines']]


@pytest.fixture
def h(monkeypatch):
    monkeypatch.setenv(reliability_experiments.ENV, EXPERIMENT)
    monkeypatch.setattr(module, 'RECEIVE_POLL_SECONDS', 0.02)
    module._sessions.clear()
    raw = SimpleNamespace(send=Mock(return_value=True), finish=Mock(), is_connection_dead=False)
    dial = AsyncMock(return_value=raw)
    monkeypatch.setattr(module, 'process_audio_soniox', dial)
    aborted = AsyncMock()
    monkeypatch.setattr(module, 'abort_replay_socket', aborted)
    return SimpleNamespace(raw=raw, dial=dial, aborted=aborted)


def start(phone, codec='pcm16', language='en', uid='owner'):
    return asyncio.create_task(module.run_live_words(phone, uid, language=language, sample_rate=16000, codec=codec))


async def until(condition, timeout=1.0):
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.005)


def word(text, start, end, speaker='SPEAKER_00'):
    return {'text': text, 'start': start, 'end': end, 'speaker': speaker, 'is_user': False}


async def test_off_refuses_before_accepting(monkeypatch, h):
    monkeypatch.delenv(reliability_experiments.ENV, raising=False)
    phone = Phone()
    with pytest.raises(WebSocketException) as refused:
        await module.run_live_words(phone, 'owner', language='en', sample_rate=16000, codec='pcm16')
    assert refused.value.code == 1008
    assert not phone.accepted
    h.dial.assert_not_awaited()
    assert module._sessions == {}


async def test_unsupported_format_is_refused_before_accepting(h):
    for codec, rate in (('aac', 16000), ('pcm16', 8000)):
        phone = Phone()
        with pytest.raises(WebSocketException):
            await module.run_live_words(phone, 'owner', language='en', sample_rate=rate, codec=codec)
        assert not phone.accepted
    h.dial.assert_not_awaited()


async def test_audio_during_the_dial_is_sent_first_then_live_audio(h):
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        await release.wait()
        return h.raw

    h.dial.side_effect = slow
    phone = Phone()
    task = start(phone)
    first, second, third = b'\x01\x00' * 160, b'\x02\x00' * 160, b'\x03\x00' * 160
    phone.audio(first)
    await asyncio.wait_for(started.wait(), timeout=1)
    phone.audio(second)
    await asyncio.sleep(0.05)
    h.raw.send.assert_not_called()  # The receive loop never waits on the dial.
    release.set()
    await until(lambda: h.raw.send.call_count == 2)
    phone.audio(third)
    await until(lambda: h.raw.send.call_count == 3)
    assert [call.args[0] for call in h.raw.send.call_args_list] == [first, second, third]
    # The dial used the language the phone asked for and nothing of a listening session.
    assert h.dial.call_args.args[1:] == (16000, 'en') and h.dial.call_args.kwargs == {'uid': 'owner'}
    phone.leave()
    await asyncio.wait_for(task, timeout=1)
    h.raw.finish.assert_called_once()
    assert phone.closed == (1000, 'client')
    assert module._sessions == {}


async def test_words_become_lines_with_word_times_and_text_is_never_logged(h, caplog):
    caplog.set_level(logging.INFO)
    phone = Phone()
    task = start(phone)
    phone.audio()
    await until(lambda: h.raw.send.call_count == 1)
    words = h.dial.call_args.args[0]
    words([word('Hello', 0.0, 0.4)])
    await until(lambda: len(phone.lines()) == 1)
    words([word('there.', 0.5, 0.9)])
    await until(lambda: len(phone.lines()) == 2)
    words([word('Hi.', 1.0, 1.3, speaker='SPEAKER_01'), word('Later', 9.0, 9.4, speaker='SPEAKER_01')])
    await until(lambda: len(phone.lines()) == 4)
    lines = phone.lines()
    # One line grows under one id; another speaker, or a long pause, starts a new line.
    assert [line['text'] for line in lines] == ['Hello', 'Hello there.', 'Hi.', 'Later']
    assert lines[0]['id'] == lines[1]['id'] and len({line['id'] for line in lines}) == 3
    assert lines[1]['start'] == 0.0 and lines[1]['end'] == 0.9
    assert lines[1]['words'] == [['Hello', 0.0, 0.4], ['there.', 0.5, 0.9]]
    phone.leave()
    await asyncio.wait_for(task, timeout=1)
    # A late callback from the closing stream reaches nobody.
    words([word('late', 10.0, 10.2)])
    await asyncio.sleep(0.02)
    assert len(phone.lines()) == 4
    logged = '\n'.join(record.getMessage() for record in caplog.records)
    assert 'event=live_words action=close' in logged and 'streams=1' in logged and 'lines=3 words=4' in logged
    for spoken in ('Hello', 'there.', 'Hi.', 'Later'):
        assert spoken not in logged


async def test_the_phone_is_told_how_much_audio_arrived(h, monkeypatch):
    monkeypatch.setattr(module, 'ACK_SECONDS', 0.0)
    phone = Phone()
    task = start(phone)
    phone.audio()
    phone.audio()
    await until(lambda: any(m['type'] == 'ack' and m['frames'] == 2 for m in phone.sent))
    ack = [m for m in phone.sent if m['type'] == 'ack'][-1]
    assert ack == {'type': 'ack', 'frames': 2, 'audio_ms': 200}
    phone.leave()
    await asyncio.wait_for(task, timeout=1)


async def test_opus_frames_are_decoded_and_a_bad_frame_is_skipped(h, monkeypatch):
    decoder = SimpleNamespace(decode=Mock(side_effect=[b'\x05\x00' * 160, ValueError('corrupt'), b'\x06\x00' * 160]))
    monkeypatch.setattr(module, '_opus_decoder', lambda: decoder)
    monkeypatch.setattr(module, 'opuslib', object())
    phone = Phone()
    task = start(phone, codec='opus')
    for packet in (b'a', b'b', b'c'):
        phone.audio(packet)
    await until(lambda: h.raw.send.call_count == 2)
    assert [call.args[0] for call in h.raw.send.call_args_list] == [b'\x05\x00' * 160, b'\x06\x00' * 160]
    phone.leave()
    await asyncio.wait_for(task, timeout=1)


async def test_a_new_connection_from_the_same_install_replaces_the_old_one(h):
    first, second, other = Phone('abc'), Phone('abc'), Phone('other')
    one = start(first)
    first.audio()
    await until(lambda: ('owner', 'ios_abc') in module._sessions)
    three = start(other)
    await until(lambda: ('owner', 'ios_other') in module._sessions)
    two = start(second)
    await asyncio.wait_for(one, timeout=1)
    assert first.closed == (module.CLOSE_REPLACED, 'replaced')
    assert other.closed is None and second.closed is None
    assert set(module._sessions) == {('owner', 'ios_abc'), ('owner', 'ios_other')}
    second.leave()
    other.leave()
    await asyncio.wait_for(asyncio.gather(two, three), timeout=1)
    assert module._sessions == {}


async def test_a_connection_without_audio_for_long_is_closed(h, monkeypatch):
    monkeypatch.setattr(module, 'IDLE_SECONDS', 0.05)
    phone = Phone()
    await asyncio.wait_for(start(phone), timeout=1)
    assert phone.closed == (module.CLOSE_IDLE, 'idle')
    h.raw.finish.assert_called_once()


def streams(h, count):
    """Each dial gets a provider stream of its own."""
    made = [
        SimpleNamespace(send=Mock(return_value=True), finish=Mock(), is_connection_dead=False) for _ in range(count)
    ]
    h.dial.side_effect = made
    return made


async def test_silence_closes_only_the_provider_stream_and_the_next_audio_dials_again(h, monkeypatch):
    monkeypatch.setattr(module, 'PROVIDER_IDLE_SECONDS', 0.1)
    monkeypatch.setattr(module, 'RETIRE_GRACE_SECONDS', 0.05)
    monkeypatch.setattr(module, 'REDIAL_SECONDS', 0.0)
    first, second = streams(h, 2)
    phone = Phone()
    task = start(phone)
    phone.audio()  # 100 ms
    phone.audio()
    await until(lambda: first.send.call_count == 2)
    h.dial.call_args.args[0]([word('before', 0.0, 0.1)])
    await until(lambda: len(phone.lines()) == 1)
    # Quiet: the provider stream is given back, then cut; the phone's connection is still there.
    await until(lambda: first.finish.called)
    await until(lambda: h.aborted.await_count == 1)
    assert phone.closed is None and not task.done()
    assert h.dial.await_count == 1  # Silence alone dials nothing.
    # Audio again: a new stream on the same connection, and that audio is its first.
    later = b'\x07\x00' * 1600
    phone.audio(later)
    await until(lambda: second.send.call_count == 1)
    assert second.send.call_args.args[0] == later
    assert h.dial.await_count == 2
    # The new stream counts from its own first sample; the line is timed from the connection's first frame.
    h.dial.call_args.args[0]([word('after', 0.0, 0.1)])
    await until(lambda: len(phone.lines()) == 2)
    before, after = phone.lines()
    assert (before['start'], after['start'], after['end']) == (0.0, 0.2, 0.3)
    assert before['id'] != after['id']
    phone.leave()
    await asyncio.wait_for(task, timeout=1)
    assert phone.closed == (1000, 'client')
    second.finish.assert_called_once()


async def test_the_last_words_of_a_stream_given_back_still_reach_the_phone(h, monkeypatch):
    monkeypatch.setattr(module, 'PROVIDER_IDLE_SECONDS', 0.05)
    monkeypatch.setattr(module, 'RETIRE_GRACE_SECONDS', 5.0)
    phone = Phone()
    task = start(phone)
    phone.audio()
    await until(lambda: h.raw.send.call_count == 1)
    await until(lambda: h.raw.finish.called)
    h.dial.call_args.args[0]([word('last', 0.0, 0.1)])
    await until(lambda: len(phone.lines()) == 1)
    phone.leave()
    await asyncio.wait_for(task, timeout=1)


async def test_a_dead_provider_stream_is_replaced_on_the_same_connection(h, monkeypatch):
    monkeypatch.setattr(module, 'REDIAL_SECONDS', 0.0)
    first, second = streams(h, 2)
    phone = Phone()
    task = start(phone)
    phone.audio()
    await until(lambda: first.send.call_count == 1)
    first.send.return_value = False
    phone.audio()  # The stream refuses it: it is lost, and the phone is not disconnected.
    await asyncio.sleep(0.05)
    assert phone.closed is None
    phone.audio()
    await until(lambda: second.send.call_count == 1)
    assert h.dial.await_count == 2
    phone.leave()
    await asyncio.wait_for(task, timeout=1)
    assert phone.closed == (1000, 'client')


async def test_a_provider_that_keeps_failing_ends_the_connection(h, monkeypatch):
    monkeypatch.setattr(module, 'REDIAL_SECONDS', 0.0)
    h.dial.side_effect = RuntimeError('no route')
    phone = Phone()
    task = start(phone)
    for _ in range(40):
        if task.done():
            break
        phone.audio()
        await asyncio.sleep(0.01)
    await asyncio.wait_for(task, timeout=1)
    assert phone.closed == (1011, 'provider_unavailable')
    assert h.dial.await_count == module.MAX_PROVIDER_FAILURES
    h.raw.finish.assert_not_called()


async def test_dials_are_spaced_so_a_failing_provider_is_not_hammered(h):
    h.dial.side_effect = RuntimeError('no route')
    phone = Phone()
    task = start(phone)
    for _ in range(20):
        phone.audio()
        await asyncio.sleep(0.005)
    assert h.dial.await_count == 1  # REDIAL_SECONDS has not passed.
    phone.leave()
    await asyncio.wait_for(task, timeout=1)


async def test_audio_that_fell_out_of_the_dial_buffer_moves_the_line_clock_on(h, monkeypatch):
    monkeypatch.setattr(module, 'DIAL_BUFFER_SECONDS', 0.2)
    started, release = asyncio.Event(), asyncio.Event()

    async def slow(*args, **kwargs):
        started.set()
        await release.wait()
        return h.raw

    h.dial.side_effect = slow
    phone = Phone()
    task = start(phone)
    for _ in range(5):  # 500 ms into a 200 ms buffer: the oldest 300 ms fall out.
        phone.audio()
    await asyncio.wait_for(started.wait(), timeout=1)
    await asyncio.sleep(0.05)
    release.set()
    await until(lambda: h.raw.send.call_count == 2)
    h.dial.call_args.args[0]([word('word', 0.0, 0.2)])
    await until(lambda: len(phone.lines()) == 1)
    # The provider's zero is 300 ms after the connection's first frame.
    assert phone.lines()[0]['start'] == 0.3 and phone.lines()[0]['end'] == 0.5
    phone.leave()
    await asyncio.wait_for(task, timeout=1)


def test_the_page_only_stream_stands_down_while_this_experiment_is_on(monkeypatch):
    host = SimpleNamespace(
        request=SimpleNamespace(uid='owner'),
        client_device_context=SimpleNamespace(platform='ios'),
        server_batch_only=True,
        batch_record_capture={'record_lane_owner': 'batch_live_v1', 'server_batch_only': True},
        local_preview_batch=False,
        use_custom_stt=False,
        is_multi_channel=False,
    )
    receiver = SimpleNamespace(host=host)
    monkeypatch.setenv(reliability_experiments.ENV, 'instant_live_text')
    assert watched_stream.admitted(receiver)
    monkeypatch.setenv(reliability_experiments.ENV, f'instant_live_text,{EXPERIMENT}')
    assert not watched_stream.admitted(receiver)
