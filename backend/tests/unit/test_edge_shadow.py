"""D2 edge shadow mirror (utils/stt/edge_shadow.py) and the VAD gate tap."""

import asyncio
import struct
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import scripts.edge_shadow_gate as gate_script
import utils.stt.edge_shadow as edge_shadow
from utils.metrics import OMI_LISTEN_EDGE_SHADOW_SESSIONS_TOTAL
from utils.stt.edge_shadow import (
    EdgeShadowMirror,
    GateTap,
    attach_tap,
    encode_frame,
    encode_gate_start,
    encode_open,
    encode_windows,
    in_cohort,
    maybe_start,
    session_key,
    shadow_percent,
)
from utils.stt.vad_gate import VADStreamingGate
from routers.listen.receiver import ListenReceiver

URL = 'ws://listen-edge:8080/v1/shadow'


def _outcome_count(outcome: str) -> float:
    return OMI_LISTEN_EDGE_SHADOW_SESSIONS_TOTAL.labels(outcome=outcome)._value.get()


class FakeSocket:
    """Edge socket double. ``stall`` makes every send wait forever."""

    def __init__(self, stall: bool = False, closed: bool = False):
        self.sent = []
        self.stall = stall
        self.closed_by_edge = closed
        self.closed = False
        self.send_entered = asyncio.Event()

    async def send(self, message):
        self.send_entered.set()
        if self.closed_by_edge:
            raise edge_shadow.websockets.ConnectionClosed(None, None)
        if self.stall:
            await asyncio.Event().wait()
        self.sent.append(message)

    async def close(self):
        self.closed = True


def _connect_returning(socket):
    async def connect(url, **kwargs):
        connect.url = url
        connect.kwargs = kwargs
        return socket

    return connect


def _spawn(coro, *, name):
    return asyncio.get_running_loop().create_task(coro, name=name)


# --- cohort, key, flag -------------------------------------------------------


@pytest.mark.parametrize(
    'raw,want',
    [(None, 0.0), ('0', 0.0), ('5', 5.0), ('0.5', 0.5), ('150', 100.0), ('-1', 0.0), ('nan', 0.0), ('x', 0.0)],
)
def test_percent_parses_as_kill_switch(monkeypatch, raw, want):
    if raw is None:
        monkeypatch.delenv('EDGE_SHADOW_PERCENT', raising=False)
    else:
        monkeypatch.setenv('EDGE_SHADOW_PERCENT', raw)
    assert shadow_percent() == want


def test_cohort_is_static_and_proportional():
    uids = [f'user-{i}' for i in range(4000)]
    five = {u for u in uids if in_cohort(u, 5)}
    assert five == {u for u in uids if in_cohort(u, 5)}  # deterministic
    assert 120 < len(five) < 280  # ~5%
    assert five <= {u for u in uids if in_cohort(u, 25)}  # nested ramp
    assert not any(in_cohort(u, 0) for u in uids)
    assert all(in_cohort(u, 100) for u in uids)
    assert not in_cohort('', 100)


def test_session_key_is_hashed_hex_without_the_uid():
    key = session_key('session-123')
    assert len(key) == 32 and all(c in '0123456789abcdef' for c in key)
    assert 'session' not in key and key == session_key('session-123') != session_key('session-124')


# --- wire format (must match backend/edge/src/shadow.rs) -----------------------


def test_wire_format_matches_edge_protocol_v1():
    assert encode_frame(320, 320, b'\x01\x02') == b'\x01' + struct.pack('>QI', 320, 320) + b'\x01\x02'
    gs = encode_gate_start(
        3,
        agc=True,
        active=True,
        speech_threshold=0.65,
        continue_threshold=0.65,
        hangover_ms=300,
        origin_sample=960,
    )
    assert len(gs) == 33 and gs[0] == 2 and gs[3] == 1 and gs[4] == 0
    assert struct.unpack('>H', gs[1:3]) == (3,)
    assert struct.unpack('>ddIQ', gs[5:]) == (0.65, 0.65, 300, 960)
    unknown = encode_gate_start(
        1, agc=False, active=False, speech_threshold=0.5, continue_threshold=0.4, hangover_ms=4000, origin_sample=None
    )
    assert unknown[4] == 1 and struct.unpack('>Q', unknown[-8:]) == (2**64 - 1,)
    w = encode_windows(1, 7, [0.25, 0.75])
    assert w[:7] == b'\x03' + struct.pack('>HI', 1, 7) and struct.unpack('>2f', w[7:]) == (0.25, 0.75)
    assert encode_open(1, 960, 0) == b'\x04' + struct.pack('>HQQ', 1, 960, 0)


# --- mirror lifecycle ----------------------------------------------------------


def test_close_flushes_in_order_then_completes():
    async def run():
        socket = FakeSocket()
        connect = _connect_returning(socket)
        mirror = EdgeShadowMirror(URL, codec='opus', sample_rate=16000, session_id='s1', token='t0k', connect=connect)
        before = _outcome_count('completed')
        mirror.start(_spawn)
        for i in range(5):
            mirror.frame(i * 320, 320, bytes([i]))
        mirror.close()
        await asyncio.wait_for(mirror._task, 2)
        assert socket.sent == [encode_frame(i * 320, 320, bytes([i])) for i in range(5)]
        assert socket.closed and mirror.outcome == 'completed'
        assert _outcome_count('completed') == before + 1
        assert connect.url.startswith(URL + '?v=1&codec=opus&sample_rate=16000&session=')
        assert 's1' not in connect.url and connect.kwargs['extra_headers'] == {'x-edge-shadow-token': 't0k'}

    asyncio.run(run())


def test_stalled_edge_never_blocks_the_live_session():
    """A send stuck on the edge never reaches the live session.

    The fake edge's first send never completes. Once that send is pending,
    the session keeps offering frames: every offer is a plain call (no
    await), the queue never exceeds its bound, a concurrent "live" task keeps
    running between frames, and on overflow the mirror stops itself and
    cancels the stuck sender. No wall-clock thresholds.
    """

    async def run():
        socket = FakeSocket(stall=True)
        mirror = EdgeShadowMirror(
            URL,
            codec='pcm16',
            sample_rate=16000,
            session_id='s2',
            queue_messages=64,
            connect=_connect_returning(socket),
        )
        assert not asyncio.iscoroutinefunction(mirror.frame)
        assert not asyncio.iscoroutinefunction(mirror.offer)
        before = _outcome_count('queue_full')
        mirror.start(_spawn)
        payload = b'\x00' * 640
        mirror.frame(0, 320, payload)
        await asyncio.wait_for(socket.send_entered.wait(), 2)  # the sender is now stuck in send

        live_steps = 0

        async def live():
            nonlocal live_steps
            while True:
                live_steps += 1
                await asyncio.sleep(0)

        ticker = asyncio.create_task(live())
        for i in range(1, 200):
            mirror.frame(i * 320, 320, payload)
            assert mirror._queue.qsize() <= 64
            steps = live_steps
            await asyncio.sleep(0)  # the receive loop awaits the next client frame
            await asyncio.sleep(0)
            assert live_steps > steps  # the live task ran while the send stays stuck
        ticker.cancel()
        await asyncio.wait({mirror._task, ticker}, timeout=2)

        assert socket.sent == []  # the stalled send never completed
        assert not mirror.active and mirror.outcome == 'queue_full'
        assert _outcome_count('queue_full') == before + 1
        assert mirror._task.done()  # the stuck sender was cancelled

    asyncio.run(run())


def test_unexpected_errors_stop_the_mirror_not_the_session():
    async def run():
        mirror = EdgeShadowMirror(
            URL, codec='opus', sample_rate=16000, session_id='s5', connect=_connect_returning(FakeSocket())
        )
        mirror.start(_spawn)
        mirror.frame(-1, 320, b'x')  # unencodable position: must not raise
        assert not mirror.active
        mirror.frame(0, 320, b'x')
        mirror.close()
        await asyncio.wait({mirror._task}, timeout=2)

    asyncio.run(run())


def test_connect_failure_disables_the_mirror_quietly():
    async def run():
        async def refuse(url, **kwargs):
            raise OSError('connection refused')

        mirror = EdgeShadowMirror(URL, codec='opus', sample_rate=16000, session_id='s3', connect=refuse)
        before = _outcome_count('connect_failed')
        mirror.start(_spawn)
        await asyncio.wait_for(mirror._task, 2)
        mirror.frame(0, 320, b'x')  # no-op, no raise
        mirror.close()
        assert not mirror.active and mirror.outcome == 'connect_failed'
        assert _outcome_count('connect_failed') == before + 1

    asyncio.run(run())


def test_edge_close_stops_mirroring():
    async def run():
        mirror = EdgeShadowMirror(
            URL, codec='opus', sample_rate=16000, session_id='s4', connect=_connect_returning(FakeSocket(closed=True))
        )
        mirror.start(_spawn)
        mirror.frame(0, 320, b'x')
        await asyncio.wait_for(mirror._task, 2)
        assert not mirror.active and mirror.outcome == 'edge_closed'

    asyncio.run(run())


def test_maybe_start_needs_percent_url_codec_and_cohort(monkeypatch):
    spawned = []

    def spawn(coro, *, name):
        spawned.append(name)
        coro.close()
        return MagicMock()

    kwargs = dict(uid='u', session_id='s', codec='opus', sample_rate=16000, spawn=spawn)
    monkeypatch.delenv('EDGE_SHADOW_PERCENT', raising=False)
    monkeypatch.setenv('EDGE_SHADOW_URL', URL)
    assert maybe_start(**kwargs) is None  # default 0: off
    monkeypatch.setenv('EDGE_SHADOW_PERCENT', '100')
    monkeypatch.delenv('EDGE_SHADOW_URL')
    assert maybe_start(**kwargs) is None  # no URL
    monkeypatch.setenv('EDGE_SHADOW_URL', URL)
    assert maybe_start(**{**kwargs, 'codec': 'lc3'}) is None
    assert maybe_start(**{**kwargs, 'codec': 'aac'}) is None
    assert spawned == []
    mirror = maybe_start(**kwargs)
    assert isinstance(mirror, EdgeShadowMirror) and spawned == ['edge_shadow_mirror']
    monkeypatch.setenv('EDGE_SHADOW_PERCENT', '0.01')
    assert maybe_start(**{**kwargs, 'uid': next(u for u in map(str, range(1000)) if not in_cohort(u, 0.01))}) is None


def test_maybe_start_never_raises(monkeypatch):
    monkeypatch.setenv('EDGE_SHADOW_PERCENT', '100')
    monkeypatch.setenv('EDGE_SHADOW_URL', URL)

    def spawn(coro, *, name):
        coro.close()
        raise RuntimeError('no loop')

    assert maybe_start(uid='u', session_id='s', codec='opus', sample_rate=16000, spawn=spawn) is None


# --- gate tap ------------------------------------------------------------------


class Recorder:
    def __init__(self):
        self.messages = []
        self.gates = 0

    def offer(self, message):
        self.messages.append(message)

    def tap(self):
        self.gates += 1
        return GateTap(self, self.gates)


def _scripted_vad(probs):
    it = iter(probs)

    def run(window, state, context):
        return next(it), state, context

    return run


def _fresh_state():
    return np.zeros((2, 1, 128), dtype=np.float32), np.zeros((1, 64), dtype=np.float32)


def _drive(gate, chunks):
    outs = []
    for i, chunk in enumerate(chunks):
        outs.append(gate.process_audio(chunk, 1.0 + i * 0.04, start_sample=i * 640))
    return outs


def test_tap_reports_gate_windows_and_opens_without_changing_decisions():
    # 40 ms chunks at 16 kHz -> 1.25 windows each; speech from window 4.
    probs = [0.1, 0.2, 0.1, 0.3, 0.9, 0.95, 0.9, 0.8, 0.2, 0.1, 0.1, 0.1]
    chunks = [b'\x01\x00' * 640] * 9

    def run(tapped):
        with (
            patch('utils.stt.vad_gate.run_vad_window', side_effect=_scripted_vad(probs)),
            patch('utils.stt.vad_gate.make_fresh_state', side_effect=_fresh_state),
            patch('utils.stt.vad_gate._get_ort_session'),
        ):
            gate = VADStreamingGate(sample_rate=16000, mode='active')
            rec = Recorder()
            if tapped:
                gate.edge_tap = rec.tap()
            outs = _drive(gate, chunks)
        return [(o.audio_to_send, o.state, o.is_speech, o.should_finalize) for o in outs], rec

    plain, _ = run(False)
    tapped, rec = run(True)
    assert plain == tapped  # the tap observes; it never changes gating

    kinds = [m[0] for m in rec.messages]
    assert kinds[0] == 2  # GATE_START first, at the first chunk's origin
    assert struct.unpack('>Q', rec.messages[0][-8:]) == (0,)
    assert rec.messages[0][3] == 0 and rec.messages[0][4] == 0  # plain, active
    reported = []
    next_ordinal = 0
    for m in rec.messages:
        if m[0] == 3:
            gen, first = struct.unpack('>HI', m[1:7])
            assert gen == 1 and first == next_ordinal
            got = struct.unpack(f'>{(len(m) - 7) // 4}f', m[7:])
            reported.extend(got)
            next_ordinal += len(got)
    assert np.allclose(reported, probs[: len(reported)]) and len(reported) == 11
    opens = [struct.unpack('>HQQ', m[1:]) for m in rec.messages if m[0] == 4]
    assert len(opens) == 1 and opens[0][0] == 1 and opens[0][1] == 3 * 640  # chunk 3 holds window 4


def test_tap_marks_agc_scoring_and_renews_on_activate():
    with (
        patch('utils.stt.vad_gate.run_vad_window', side_effect=lambda w, s, c: (0.1, s, c)),
        patch('utils.stt.vad_gate.make_fresh_state', side_effect=_fresh_state),
        patch('utils.stt.vad_gate._get_ort_session'),
    ):
        gate = VADStreamingGate(sample_rate=16000, mode='shadow')
        rec = Recorder()
        gate.edge_tap = rec.tap()
        chunk = b'\x01\x00' * 640
        gate.process_audio(chunk, 1.0, score_pcm=chunk, start_sample=0)
        gate.activate()
        gate.process_audio(chunk, 1.1, start_sample=640)
    starts = [m for m in rec.messages if m[0] == 2]
    assert [s[3] for s in starts] == [1, 0]  # agc copy scored, then plain
    assert [struct.unpack('>H', s[1:3])[0] for s in starts] == [1, 2]  # activate() is a new gate
    assert starts[0][4] == 1 and starts[1][4] == 0  # shadow, then active
    windows = [struct.unpack('>HI', m[1:7]) for m in rec.messages if m[0] == 3]
    assert windows[0] == (1, 0) and windows[-1] == (2, 0)  # ordinals restart with the new gate


def test_tap_failure_detaches_without_touching_the_gate():
    with (
        patch('utils.stt.vad_gate.run_vad_window', side_effect=lambda w, s, c: (0.9, s, c)),
        patch('utils.stt.vad_gate.make_fresh_state', side_effect=_fresh_state),
        patch('utils.stt.vad_gate._get_ort_session'),
    ):
        gate = VADStreamingGate(sample_rate=16000, mode='active')
        broken = MagicMock()
        broken.chunk.side_effect = RuntimeError('boom')
        gate.edge_tap = broken
        out = gate.process_audio(b'\x01\x00' * 640, 1.0, start_sample=0)
    assert out.is_speech and out.audio_to_send and gate.mode == 'active'
    assert gate.edge_tap is None


def test_receiver_reads_nothing_at_the_default_percent(monkeypatch):

    receiver = ListenReceiver.__new__(ListenReceiver)
    receiver._edge_shadow_checked = False
    receiver.edge_shadow = None
    receiver.capture_timeline = object()
    receiver.host = object()  # any attribute read would raise
    monkeypatch.delenv('EDGE_SHADOW_PERCENT', raising=False)
    with patch.object(edge_shadow, 'maybe_start') as start:
        assert edge_shadow.session_mirror(receiver) is None
        assert receiver.edge_shadow_tap() is None
    start.assert_not_called()


def test_receiver_starts_one_mirror_and_taps_each_gate(monkeypatch):

    receiver = ListenReceiver.__new__(ListenReceiver)
    receiver._edge_shadow_checked = False
    receiver.edge_shadow = None
    receiver.capture_timeline = object()
    request = SimpleNamespace(uid='u1', codec='opus', sample_rate=16000)
    receiver.host = SimpleNamespace(request=request, session_id='sess', spawn=MagicMock())
    monkeypatch.setenv('EDGE_SHADOW_PERCENT', '100')
    rec = Recorder()
    with patch.object(edge_shadow, 'maybe_start', return_value=rec) as start:
        first, second = receiver.edge_shadow_tap(), receiver.edge_shadow_tap()
    start.assert_called_once_with(
        uid='u1', session_id='sess', codec='opus', sample_rate=16000, spawn=receiver.host.spawn
    )
    assert (first.gen, second.gen) == (1, 2)

    no_clock = ListenReceiver.__new__(ListenReceiver)
    no_clock._edge_shadow_checked = False
    no_clock.edge_shadow = None
    no_clock.capture_timeline = None  # multi-channel / custom STT: never mirrored
    assert edge_shadow.session_mirror(no_clock) is None


def _scrape(agree=990, disagree=2, not_comparable=0, unmatched=0, cpu=0.004, audio=1.0, opens=10):
    c = 'omi_edge_shadow_window_compare_total{codec="opus",result="%s",variant="plain"} %s'
    lines = [
        c % ('agree_speech', agree // 2),
        c % ('agree_silence', agree - agree // 2),
        c % ('edge_speech_only', disagree),
        c % ('listen_speech_only', 0),
        c % ('not_comparable', not_comparable),
        c % ('unmatched', unmatched),
        'omi_edge_shadow_gate_open_offset_seconds_bucket{le="0.016"} %s' % opens,
        'omi_edge_shadow_gate_open_offset_seconds_bucket{le="0.032"} %s' % opens,
        'omi_edge_shadow_gate_open_offset_seconds_bucket{le="+Inf"} %s' % opens,
        'omi_edge_shadow_gate_open_offset_seconds_count %s' % opens,
        'omi_edge_shadow_processing_seconds_total{stage="vad"} %s' % cpu,
        'omi_edge_shadow_audio_seconds_total{codec="opus"} %s' % audio,
    ]
    return gate_script.parse('\n'.join(lines))


def test_gate_script_checks_agreement_coverage_offset_and_cpu():
    assert gate_script.evaluate(_scrape())[0]
    assert not gate_script.evaluate(_scrape(disagree=10))[0]  # 99.0% agreement
    assert not gate_script.evaluate(_scrape(not_comparable=100))[0]  # coverage < 95%
    assert not gate_script.evaluate(_scrape(cpu=0.01))[0]  # 10 ms per audio second
    assert not gate_script.evaluate(_scrape(agree=0, disagree=0))[0]  # nothing compared
    # Over a hold: the delta, and a counter reset refuses to compute.
    before = _scrape(agree=100, disagree=0, audio=0.1, cpu=0.0004, opens=0)
    after = _scrape(agree=1100, disagree=1, audio=1.1, cpu=0.0044, opens=10)
    assert gate_script.evaluate(gate_script.delta(after, before))[0]
    with pytest.raises(gate_script.CounterReset):
        gate_script.delta(before, after)


def test_attach_tap_uses_the_receiver_class_only():
    gate = MagicMock(edge_tap=None)
    attach_tap(gate, MagicMock())  # test doubles without the factory: untouched
    assert gate.edge_tap is None
    attach_tap(None, MagicMock())

    class Receiver:
        def edge_shadow_tap(self):
            return 'tap'

    attach_tap(gate, Receiver())
    assert gate.edge_tap == 'tap'
