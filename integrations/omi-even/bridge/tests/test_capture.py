"""Tests for the G2 -> Omi audio capture session.

Most of what this module encodes is invisible in the happy path and silent when
wrong: a mistyped `source` mislabels every conversation instead of erroring, a
frame of two bytes is dropped by the server without a word, and a stream with
no inbound traffic for 90s is closed from the other end. The tests below assert
those invariants directly rather than through behaviour that would still look
fine on-screen.
"""

import asyncio
import json
import random
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import capture  # noqa: E402
from conftest import FakeAuth, install_mock_transport  # noqa: E402
from capture import CHUNK_BYTES, SOURCE, CaptureSession, CaptureStats, listen_url  # noqa: E402


async def wait_until(predicate, timeout=2.0):
    """Poll `predicate` until true, so tests never depend on a fixed sleep."""
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError(f'condition never became true within {timeout}s')


def drain(queue: asyncio.Queue) -> list:
    items = []
    while not queue.empty():
        items.append(queue.get_nowait())
    return items


def make_session(**kwargs) -> CaptureSession:
    return CaptureSession(FakeAuth(), 'https://api.omi.me', **kwargs)


class FakeSocket:
    """A websockets-style connection: awaitable `send`, async-iterable inbound."""

    def __init__(self) -> None:
        self.sent: list = []
        self.inbound: asyncio.Queue = asyncio.Queue()
        self.closed = False

    async def send(self, frame) -> None:
        self.sent.append(frame)

    def push(self, message) -> None:
        self.inbound.put_nowait(message)

    async def __aiter__(self):
        while True:
            message = await self.inbound.get()
            if message is _END:
                return
            yield message


_END = object()


def fake_connect(socket, *, record=None):
    """Replacement for `websockets.connect` returning `socket`."""

    class _CM:
        def __init__(self, url, **kwargs):
            if record is not None:
                record.append((url, kwargs))

        async def __aenter__(self):
            return socket

        async def __aexit__(self, *exc):
            socket.closed = True
            return False

    return _CM


# --------------------------------------------------------------------------
# listen_url
# --------------------------------------------------------------------------


def params_of(url: str) -> dict:
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}


def test_source_is_rayban_meta():
    """The single most important parameter in this module.

    `ConversationSource._missing_` maps any unknown string to `unknown` instead
    of raising, so a typo here does not fail -- it silently relabels every
    conversation the glasses ever record. `rayban_meta` is also photo-capable,
    which stops `resolve_photo_conversation_source` from later rewriting the
    provenance to `openglass`.
    """
    assert params_of(listen_url('https://api.omi.me'))['source'] == 'rayban_meta'
    assert SOURCE == 'rayban_meta'


def test_audio_parameters_match_what_the_g2_microphone_emits():
    """PCM16 LE mono at 16 kHz, passed through unconverted. A mismatch here is
    not an error either -- it is garbled audio and an empty transcript.
    """
    params = params_of(listen_url('https://api.omi.me'))
    assert params['codec'] == 'pcm16'
    assert params['sample_rate'] == '16000'
    assert params['channels'] == '1'


def test_listen_url_carries_the_remaining_session_parameters():
    params = params_of(listen_url('https://api.omi.me'))
    assert params['language'] == 'en'
    assert params['include_speech_profile'] == 'true'
    # Values below 120 are clamped up server-side; passing the real floor keeps
    # the client's idea of the timeout equal to the server's.
    assert params['conversation_timeout'] == '120'


def test_listen_url_honours_a_language_override():
    assert params_of(listen_url('https://api.omi.me', language='fr'))['language'] == 'fr'


@pytest.mark.parametrize(
    'base,expected',
    [
        ('https://api.omi.me', 'wss://api.omi.me/v4/listen'),
        ('https://api.omi.me/', 'wss://api.omi.me/v4/listen'),
        ('http://localhost:8000', 'ws://localhost:8000/v4/listen'),
        ('http://localhost:8000/', 'ws://localhost:8000/v4/listen'),
    ],
)
def test_listen_url_upgrades_the_scheme_and_normalises_the_path(base, expected):
    url = listen_url(base)
    assert url.split('?')[0] == expected
    assert '//v4' not in url


def test_listen_url_is_properly_query_encoded():
    url = listen_url('https://api.omi.me')
    assert url.count('?') == 1
    assert ' ' not in url


# --------------------------------------------------------------------------
# feed / batching
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_feed_batches_into_chunk_sized_frames():
    session = make_session()
    session.active = True
    session.feed(b'\x01' * (CHUNK_BYTES * 2))
    frames = drain(session._queue)
    assert [len(f) for f in frames] == [CHUNK_BYTES, CHUNK_BYTES]


@pytest.mark.asyncio
async def test_feed_holds_back_the_partial_tail_until_it_fills():
    session = make_session()
    session.active = True
    session.feed(b'\x00' * (CHUNK_BYTES + 100))
    assert [len(f) for f in drain(session._queue)] == [CHUNK_BYTES]
    assert len(session._pending) == 100

    session.feed(b'\x00' * (CHUNK_BYTES - 100))
    assert [len(f) for f in drain(session._queue)] == [CHUNK_BYTES]
    assert len(session._pending) == 0


@pytest.mark.asyncio
async def test_feed_reassembles_across_many_tiny_writes():
    """The glasses deliver audio in whatever size the BLE stack produces."""
    session = make_session()
    session.active = True
    for _ in range(CHUNK_BYTES // 2):
        session.feed(b'\xaa\xbb')
    assert [len(f) for f in drain(session._queue)] == [CHUNK_BYTES]


@pytest.mark.asyncio
async def test_feed_never_emits_a_frame_the_server_would_drop():
    """Frames of <= 2 bytes are silently discarded server-side (receiver.py:491),
    so emitting one loses audio with no error anywhere.
    """
    session = make_session()
    session.active = True
    rng = random.Random(4242)
    for _ in range(400):
        session.feed(bytes(rng.randrange(256) for _ in range(rng.randint(1, 5))))
    for frame in drain(session._queue):
        assert len(frame) > 2, 'the server drops frames of 2 bytes or fewer'


@pytest.mark.asyncio
async def test_feed_loses_no_bytes_and_preserves_order():
    """Property: queued frames + the pending tail reconstruct the input exactly."""
    rng = random.Random(7)
    for _ in range(60):
        session = make_session()
        session.active = True
        writes = [bytes(rng.randrange(256) for _ in range(rng.randint(0, 900))) for _ in range(rng.randint(1, 40))]
        for write in writes:
            session.feed(write)
        frames = drain(session._queue)
        assert all(len(f) == CHUNK_BYTES for f in frames)
        assert b''.join(frames) + bytes(session._pending) == b''.join(writes)


@pytest.mark.asyncio
async def test_feed_is_a_no_op_before_start_and_after_stop():
    session = make_session()
    session.feed(b'\x01' * CHUNK_BYTES)
    assert session._queue.empty()
    assert len(session._pending) == 0


@pytest.mark.asyncio
async def test_feed_ignores_empty_audio():
    session = make_session()
    session.active = True
    session.feed(b'')
    assert session._queue.empty()


@pytest.mark.asyncio
async def test_feed_drops_and_counts_instead_of_blocking_when_the_queue_is_full():
    """`feed` runs on the app WebSocket's read loop. Blocking here stalls every
    other message from the glasses, so a full queue must cost audio, not latency.
    """
    session = make_session()
    session.active = True
    capacity = session._queue.maxsize
    assert capacity > 0

    session.feed(b'\x01' * (CHUNK_BYTES * (capacity + 20)))

    assert session._queue.qsize() == capacity
    assert session.stats.last_error is not None
    assert 'queue full' in session.stats.last_error


@pytest.mark.asyncio
async def test_feed_recovers_once_the_queue_drains():
    session = make_session()
    session.active = True
    session.feed(b'\x01' * (CHUNK_BYTES * (session._queue.maxsize + 5)))
    drain(session._queue)
    session.feed(b'\x02' * CHUNK_BYTES)
    assert session._queue.qsize() == 1


# --------------------------------------------------------------------------
# stop
# --------------------------------------------------------------------------


@pytest.fixture
def fast_flush(monkeypatch):
    """The real settle is 4s of wall clock; the behaviour is identical at 0."""
    monkeypatch.setattr(capture, '_FLUSH_SETTLE_SECONDS', 0.0)


@pytest.mark.asyncio
async def test_stop_on_an_inactive_session_is_a_no_op(fast_flush):
    session = make_session()
    stats = await session.stop(finalize=True)  # finalize would need the network
    assert stats is session.stats
    assert session._queue.empty()


@pytest.mark.asyncio
async def test_stop_flushes_the_partial_frame_before_the_silence(fast_flush):
    """Without this the last fraction of a second of speech never leaves the
    process -- and it is usually the end of the sentence.
    """
    session = make_session()
    session.active = True
    session.feed(b'\x07' * 500)
    assert len(session._pending) == 500

    await session.stop(finalize=False)

    frames = drain(session._queue)
    assert frames[0] == b'\x07' * 500
    assert len(session._pending) == 0


@pytest.mark.asyncio
async def test_stop_appends_a_tail_of_silence_so_the_endpointer_emits(fast_flush):
    """Measured: a 7.4s clip returned only its first 2.8s without this."""
    session = make_session()
    session.active = True
    await session.stop(finalize=False)

    frames = drain(session._queue)
    assert frames[-1] is None, 'the send loop needs its sentinel last'
    silence = frames[:-1]
    assert len(silence) == capture._FLUSH_SILENCE_FRAMES
    assert all(frame == b'\x00' * CHUNK_BYTES for frame in silence)
    # ~2s of silence: past any provider's endpointing window.
    seconds = len(silence) * CHUNK_BYTES / (capture.SAMPLE_RATE * capture.BYTES_PER_SAMPLE)
    assert 1.5 <= seconds <= 3.0


@pytest.mark.asyncio
async def test_stop_never_queues_a_frame_the_server_would_drop(fast_flush):
    session = make_session()
    session.active = True
    session.feed(b'\x01\x02')  # 2 bytes: below the server's floor
    await session.stop(finalize=False)

    for frame in drain(session._queue):
        assert frame is None or len(frame) > 2


@pytest.mark.asyncio
async def test_stop_marks_the_session_inactive_so_later_audio_is_ignored(fast_flush):
    session = make_session()
    session.active = True
    await session.stop(finalize=False)
    assert session.active is False

    before = session._queue.qsize()
    session.feed(b'\x01' * CHUNK_BYTES)
    assert session._queue.qsize() == before, 'audio after stop must not be queued'
    assert len(session._pending) == 0


@pytest.mark.asyncio
async def test_stop_returns_the_stats_object(fast_flush):
    session = make_session()
    session.active = True
    session.stats.bytes_sent = 32000
    stats = await session.stop(finalize=False)
    assert stats.audio_seconds == 1.0


def test_audio_seconds_is_computed_from_the_pcm16_rate():
    assert CaptureStats(bytes_sent=16000 * 2).audio_seconds == 1.0
    assert CaptureStats(bytes_sent=0).audio_seconds == 0.0


# --------------------------------------------------------------------------
# send loop
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_loop_forwards_frames_and_counts_them():
    session = make_session()
    socket = FakeSocket()
    session._queue.put_nowait(b'\x01' * CHUNK_BYTES)
    session._queue.put_nowait(b'\x02' * CHUNK_BYTES)
    session._queue.put_nowait(None)

    await asyncio.wait_for(session._send_loop(socket), timeout=2)

    assert socket.sent == [b'\x01' * CHUNK_BYTES, b'\x02' * CHUNK_BYTES]
    assert session.stats.frames_sent == 2
    assert session.stats.bytes_sent == CHUNK_BYTES * 2


@pytest.mark.asyncio
async def test_send_loop_skips_frames_the_server_would_drop():
    session = make_session()
    socket = FakeSocket()
    for frame in (b'', b'\x01', b'\x01\x02', b'\x01\x02\x03', None):
        session._queue.put_nowait(frame)

    await asyncio.wait_for(session._send_loop(socket), timeout=2)

    assert socket.sent == [b'\x01\x02\x03']
    assert session.stats.frames_sent == 1


@pytest.mark.asyncio
async def test_send_loop_emits_a_keepalive_when_no_audio_arrives(monkeypatch):
    """The server closes with 1001 after 90s of inbound silence. Any frame
    resets the timer, and an unrecognized `type` is a documented server no-op.
    """
    monkeypatch.setattr(capture, '_KEEPALIVE_INTERVAL', 0.01)
    session = make_session()
    socket = FakeSocket()

    task = asyncio.create_task(session._send_loop(socket))
    try:
        await wait_until(lambda: len(socket.sent) >= 2)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    for frame in socket.sent:
        assert isinstance(frame, str), 'a keepalive must be a JSON text frame'
        assert json.loads(frame) == {'type': 'keepalive'}
    assert session.stats.frames_sent == 0, 'keepalives are not audio'


@pytest.mark.asyncio
async def test_send_loop_returns_on_the_sentinel_without_sending_it():
    session = make_session()
    socket = FakeSocket()
    session._queue.put_nowait(None)
    session._queue.put_nowait(b'\x09' * CHUNK_BYTES)

    await asyncio.wait_for(session._send_loop(socket), timeout=2)
    assert socket.sent == []


# --------------------------------------------------------------------------
# receive loop
# --------------------------------------------------------------------------


async def run_recv(session: CaptureSession, messages) -> None:
    socket = FakeSocket()
    for message in messages:
        socket.push(message)
    socket.push(_END)
    await asyncio.wait_for(session._recv_loop(socket), timeout=2)


@pytest.mark.asyncio
async def test_recv_loop_survives_the_literal_ping_heartbeat():
    """The server sends the bare text `ping`, which is not JSON. Parsing it
    blindly raises on every heartbeat and kills the session.
    """
    session = make_session()
    await run_recv(session, ['ping', 'ping'])
    assert session.stats.last_error is None


@pytest.mark.asyncio
async def test_recv_loop_ignores_binary_and_unparseable_frames():
    session = make_session()
    await run_recv(session, [b'\x00\x01', 'not json at all', '{"unterminated'])
    assert session.stats.last_error is None


@pytest.mark.asyncio
async def test_live_transcript_arrives_as_a_bare_array_not_an_envelope():
    """`transcripts.py:314` sends a raw JSON list of new/updated segments."""
    seen = []

    async def on_segments(segments):
        seen.append(segments)

    session = make_session(on_segments=on_segments)
    await run_recv(session, [json.dumps([{'text': 'hello there'}, {'text': 'again'}])])

    assert seen == [[{'text': 'hello there'}, {'text': 'again'}]]
    assert session.stats.segments_received == 2


@pytest.mark.asyncio
async def test_conversation_session_frame_records_the_conversation_id():
    session = make_session()
    await run_recv(session, [json.dumps({'type': 'conversation_session', 'conversation_id': 'conv-42'})])
    assert session.stats.conversation_id == 'conv-42'


@pytest.mark.asyncio
async def test_freemium_threshold_frame_is_surfaced_as_an_error():
    session = make_session()
    await run_recv(session, [json.dumps({'type': 'freemium_threshold_reached'})])
    assert session.stats.last_error and 'quota' in session.stats.last_error


@pytest.mark.asyncio
async def test_every_dict_frame_reaches_the_event_callback():
    events = []

    async def on_event(payload):
        events.append(payload)

    session = make_session(on_event=on_event)
    await run_recv(
        session,
        [
            json.dumps({'type': 'conversation_session', 'conversation_id': 'c1'}),
            json.dumps({'type': 'something_new_the_server_added'}),
        ],
    )
    assert [e['type'] for e in events] == ['conversation_session', 'something_new_the_server_added']


@pytest.mark.asyncio
async def test_recv_loop_without_callbacks_does_not_crash():
    session = make_session()
    await run_recv(session, [json.dumps([{'text': 'hi'}]), json.dumps({'type': 'conversation_session'})])
    assert session.stats.segments_received == 1


# --------------------------------------------------------------------------
# session lifecycle
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_connection_is_recorded_and_never_raises(monkeypatch):
    """The bridge serves three consumers from one process; a dead capture
    socket must not take the chat path down with it.
    """

    def boom(*args, **kwargs):
        raise ConnectionRefusedError('nothing listening')

    monkeypatch.setattr(capture.websockets, 'connect', boom)

    session = make_session()
    await session.start()
    await asyncio.wait_for(session._task, timeout=2)

    assert session.active is False
    assert 'ConnectionRefusedError' in session.stats.last_error


@pytest.mark.asyncio
async def test_start_is_idempotent(monkeypatch, fast_flush):
    """A second `capture: enabled` from the glasses must not open a second socket."""
    socket = FakeSocket()
    connections: list = []
    monkeypatch.setattr(capture.websockets, 'connect', fake_connect(socket, record=connections))

    session = make_session()
    await session.start()
    first = session._task
    await session.start()

    assert session._task is first
    await wait_until(lambda: bool(connections))
    assert len(connections) == 1
    await asyncio.wait_for(session.stop(finalize=False), timeout=5)


@pytest.mark.asyncio
async def test_start_resets_the_stats(monkeypatch):
    def boom(*args, **kwargs):
        raise OSError('nothing listening')

    monkeypatch.setattr(capture.websockets, 'connect', boom)
    session = make_session()
    session.stats.bytes_sent = 999
    await session.start()
    await asyncio.wait_for(session._task, timeout=2)
    assert session.stats.bytes_sent == 0


@pytest.mark.asyncio
async def test_a_full_session_streams_audio_and_receives_transcript(monkeypatch, fast_flush):
    """End to end over a fake socket: connect, batch, send, transcribe, stop."""
    socket = FakeSocket()
    connections: list = []
    monkeypatch.setattr(capture.websockets, 'connect', fake_connect(socket, record=connections))

    segments = []

    async def on_segments(rows):
        segments.append(rows)

    session = make_session(on_segments=on_segments)
    await session.start()
    await wait_until(lambda: bool(connections))

    url, kwargs = connections[0]
    assert params_of(url)['source'] == 'rayban_meta'
    assert kwargs['additional_headers'] == {'Authorization': 'Bearer fake-id-token'}
    assert kwargs['max_size'] is None, 'audio frames must not hit a size cap'

    session.feed(b'\x11\x22' * CHUNK_BYTES)  # two full frames
    await wait_until(lambda: len(socket.sent) >= 2)
    assert all(isinstance(f, bytes) and len(f) == CHUNK_BYTES for f in socket.sent[:2])

    socket.push(json.dumps({'type': 'conversation_session', 'conversation_id': 'conv-7'}))
    socket.push(json.dumps([{'text': 'the battery regression'}]))
    await wait_until(lambda: bool(segments))
    assert segments == [[{'text': 'the battery regression'}]]

    stats = await asyncio.wait_for(session.stop(finalize=False), timeout=5)
    assert stats.conversation_id == 'conv-7'
    assert stats.frames_sent >= 2
    assert stats.audio_seconds > 0
    assert session.active is False


# --------------------------------------------------------------------------
# finalization
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_finalize_posts_to_the_conversations_endpoint(monkeypatch):
    """Disconnect-time finalization is `source == 'desktop'` only, so without
    this explicit POST the conversation lingers `in_progress`.
    """

    def handler(request):
        return httpx.Response(200, json={'id': 'conv-1'})

    requests = install_mock_transport(monkeypatch, handler)
    session = make_session()
    await session._finalize_conversation()

    assert len(requests) == 1
    assert requests[0].method == 'POST'
    assert str(requests[0].url) == 'https://api.omi.me/v1/conversations'
    assert requests[0].headers['authorization'] == 'Bearer fake-id-token'


@pytest.mark.asyncio
async def test_finalize_swallows_http_errors(monkeypatch):
    def handler(request):
        return httpx.Response(500, text='boom')

    install_mock_transport(monkeypatch, handler)
    await make_session()._finalize_conversation()  # must not raise


@pytest.mark.asyncio
async def test_finalize_swallows_auth_errors():
    """`stop()` runs on the disconnect path, where raising strands the socket."""
    session = CaptureSession(FakeAuth(fail=RuntimeError('session revoked')), 'https://api.omi.me')
    await session._finalize_conversation()


@pytest.mark.asyncio
async def test_stop_with_finalize_calls_the_endpoint_once(monkeypatch, fast_flush):
    def handler(request):
        return httpx.Response(200, json={})

    requests = install_mock_transport(monkeypatch, handler)
    session = make_session()
    session.active = True
    await session.stop(finalize=True)
    assert len(requests) == 1
