"""Client-departure drain contract for STT failover recovery sessions.

An ordinary disconnect must let the receiver drain every accepted tail packet
to the serving leg before EOS, keep the transcript consumer alive for the
final provider callbacks, and never count the heartbeat's lifetime completion
as a live-transcription failure. Flag-off sessions keep the legacy ordering.
"""

import asyncio
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.websockets import WebSocketState

from tests.unit.test_parakeet_window_live import runtime, receiver, Client  # noqa: F401
from tests.unit.test_live_cost_router import controls  # noqa: F401
from tests.unit.test_live_replay_provider_pairs import Transport, stop, until

import routers.listen.receiver as receiver_module
import routers.listen.runtime as runtime_module
import routers.listen.transcripts as transcripts_module
import utils.stt.replay_delivery as replay_delivery_module
from config.live_stt_replay import ReplayLimits
from routers.listen.contracts import ListenLimits, ListenSessionState
from routers.listen.receiver import ListenReceiver
from routers.listen.runtime import ListenSessionRuntime
from routers.listen.transcripts import TranscriptProcessor
from utils.async_tasks import WebSocketTaskSupervisor, wait_for_event
from utils.stt import parakeet_window as window, streaming as st
from utils.stt.live_metrics import REPLAY_SKIPPED
from utils.stt.replay_delivery import ReplayTailSocket
from utils.stt.soniox import SafeSonioxSocket
from utils.stt.streaming import SafeModulateSocket


@pytest.fixture(autouse=True)
def _stt_failover_recovery_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('STT_FAILOVER_RECOVERY_ENABLED', 'true')


class ClientSocket:
    """Queue-fed fake client WebSocket with a flippable connection state."""

    def __init__(self):
        self.client_state = WebSocketState.CONNECTED
        self.application_state = WebSocketState.CONNECTED
        self.incoming: asyncio.Queue = asyncio.Queue()
        self.send_json = AsyncMock()
        self.send_text = AsyncMock(return_value=True)
        self.close = AsyncMock()
        self.headers = {}

    async def receive(self):
        return await self.incoming.get()

    def feed_audio(self, data: bytes) -> None:
        self.incoming.put_nowait({'bytes': data})

    def disconnect(self, code: int = 1000) -> None:
        self.client_state = WebSocketState.DISCONNECTED
        self.application_state = WebSocketState.DISCONNECTED
        self.incoming.put_nowait({'type': 'websocket.disconnect', 'code': code})


def _persistence():
    async def call(fn, *args, **kwargs):
        name = getattr(fn, '__name__', '')
        if 'deletion' in name or 'wipe' in name:
            return False
        if 'get_conversation' in name:
            return {
                'source': 'desktop',
                'transcript_segments': [{'text': 'LAST'}],
                'external_data': {},
            }
        return None

    return SimpleNamespace(call=call)


def make_runtime(ws, monkeypatch):
    rt = object.__new__(ListenSessionRuntime)
    rt.recovery_enabled = True
    rt.request = SimpleNamespace(
        websocket=ws,
        uid='shutdown-tail',
        codec='pcm',
        sample_rate=16000,
        source='desktop',
        client_conversation_id=None,
        owner_persistence_blocked=threading.Event(),
        vad_gate_override=None,
        language='en',
        onboarding_mode=False,
        headers={},
        conversation_timeout=30,
    )
    rt.limits = ListenLimits()
    supervisor = WebSocketTaskSupervisor(uid='shutdown-tail', label='listen')
    rt.task_supervisor = supervisor
    rt.state = ListenSessionState()
    rt.state.shutdown_event = supervisor.shutdown_event
    rt.wait = lambda seconds: wait_for_event(rt.state.shutdown_event, min(seconds, 0.05))
    rt.state.current_conversation_id = 'conv-1'
    rt.state.speaker_id_done.set()
    rt.session_id = 'sess-1'
    rt.recording_session_id = 'rec-1'
    rt.is_multi_channel = False
    rt.use_custom_stt = False
    rt.declared_codec = 'pcm'
    rt.client_conversation_id = None
    rt.recording_session_ids_by_conversation = {}
    rt.language = 'en'
    rt.stt_language = 'multi'
    rt.multi_lang_enabled = True
    rt.language_profile = None
    rt.vocabulary = []
    rt.has_speech_profile = False
    rt.private_cloud_sync_enabled = False
    rt.user_has_credits = True
    rt.translation_language = None
    rt.stt_service = st.STTService.parakeet
    rt.stt_service_selected = st.STTService.parakeet
    rt.stt_model = 'parakeet-window'
    rt.client_device_context = SimpleNamespace(platform='ios')
    rt.client_kind = 'ios'
    rt.pusher_enabled = True
    rt.pusher_tasks = []
    rt.transcript_send = None
    rt.audio_bytes_send = None
    rt.send_speaker_sample_request = None
    rt.pusher_close = None
    rt.request_conversation_processing = None
    rt.onboarding_handler = None
    rt.onboarding_admitted = False
    rt.onboarding_session_id = None
    rt.onboarding_omi_speaker_id = 'omi-speaker'
    rt.language_observations = None
    rt.parity_capture = SimpleNamespace(persist=lambda: None)
    rt.persistence = _persistence()
    rt.conversations = SimpleNamespace(
        send_last_conversation=AsyncMock(),
        prepare=AsyncMock(return_value=False),
        process_pending=lambda _timed_out: asyncio.sleep(0),
        lifecycle_loop=lambda: rt.state.shutdown_event.wait(),
        process_conversation=AsyncMock(return_value=True),
        on_conversation_processed=lambda *a, **k: None,
        note_audio_activity=lambda: None,
    )
    rt.speakers = SimpleNamespace(
        load_and_run=lambda: asyncio.sleep(0),
        drain=AsyncMock(),
        tasks=[],
        segment_assignments={},
        speaker_to_person={},
        clear=lambda: None,
    )
    rt.receiver = ListenReceiver(rt, [], {})
    rt.transcripts = TranscriptProcessor(rt)
    rt._admit = AsyncMock(return_value=True)
    rt._bootstrap = AsyncMock(return_value=True)
    rt._start_pusher = AsyncMock()
    rt._flush_usage = AsyncMock(return_value=0)
    rt._record_usage_periodically = lambda: rt.state.shutdown_event.wait()
    rt.send_event = lambda _event: None
    rt.asend_event = AsyncMock(return_value=True)
    rt.receiver.initialize_decoders = lambda: None
    return rt


def stub_transcript_persistence(rt, persisted, monkeypatch, order=None):
    tp = rt.transcripts

    async def load(_conversation_id, *, force_refresh=False):
        return {'transcript_segments': [], 'data_protection_level': 'standard'}

    tp.cache.get = load

    async def update(conversation, segments, photos, finished_at, started_at, **kwargs):
        persisted.extend(segment.text for segment in segments)
        if order is not None:
            order.extend(('persist', segment.text) for segment in segments)
        return (conversation, segments, [])

    tp._update_live_conversation = update
    tp._speaker_detection = AsyncMock()
    tp.flush_speaker_assignments = AsyncMock()
    tp.flush_translations = AsyncMock()
    monkeypatch.setattr(
        transcripts_module,
        'deserialize_conversation',
        lambda data: SimpleNamespace(id='conv-1', transcript_segments=[]),
    )


def wire_providers(monkeypatch, rt, raws, dials):
    def factory(kind):
        async def connect(callback, *args, **kwargs):
            raw = kind(Transport(), callback, asyncio.get_running_loop())
            raws.append(raw)
            dials.append(raw)
            return raw

        return connect

    for module in (st, receiver_module):
        monkeypatch.setattr(module, 'process_audio_soniox', factory(SafeSonioxSocket))
        monkeypatch.setattr(module, 'process_audio_modulate', factory(SafeModulateSocket))
    monkeypatch.setattr(runtime_module, 'register_listen_session', lambda _rt: None)
    monkeypatch.setattr(runtime_module, 'unregister_listen_session', lambda _rt: None)


def watch_supervise(rt, box):
    original = rt.task_supervisor.supervise

    async def watch(*args, **kwargs):
        box['result'] = await original(*args, **kwargs)
        return box['result']

    rt.task_supervisor.supervise = watch


def marker(n: int, frames: int = 1) -> bytes:
    return (0x7000 + n).to_bytes(2, 'little') * 480 * frames


@pytest.mark.asyncio
async def test_disconnect_drains_accepted_tail_and_final_transcript(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    persisted: list[str] = []
    order: list = []
    stub_transcript_persistence(rt, persisted, monkeypatch, order)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    box: dict = {}
    watch_supervise(rt, box)
    rt.conversations.process_conversation = AsyncMock(
        side_effect=lambda *_a, **_k: order.append(('finalize', 'conv-1')) or True
    )
    labels = dict(source='parakeet', successor='soniox')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        frames = [marker(n, 2) for n in range(3)]
        for frame in frames:
            ws.feed_audio(frame)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= sum(len(frame) for frame in frames))
        actual.stt_socket.raw.fail('first_text_deadline')
        last = marker(99, 2)
        ws.feed_audio(last)
        await until(lambda: isinstance(actual.stt_socket, ReplayTailSocket))
        soniox = raws[-1]
        prefix = b''.join(frames) + last
        await until(lambda: soniox._ws.byte_count >= len(prefix))
        soniox._ws.gate.clear()
        held = [marker(7, 2), marker(8, 2)]
        accepted_end = actual.capture_timeline.next_sample + sum(len(packet) // 2 for packet in held)
        for packet in held:
            ws.feed_audio(packet)
        # The prefix writer may still be marked in-flight. Wait for both
        # client packets to be receiver-accepted before testing tail drain.
        await until(lambda: actual.capture_timeline.next_sample >= accepted_end)
        await until(lambda: bool(actual.stt_socket.tail) or soniox._send_queue.qsize() or soniox._send_queue.inflight)
        emitted = {'last': False}

        def on_send():
            if not emitted['last'] and soniox._ws.sent and soniox._ws.sent[-1] == '':
                emitted['last'] = True
                soniox._stream_transcript(
                    [{'text': 'LAST', 'start': 0.0, 'end': 0.5, 'speaker': 'speaker_0', 'is_user': False}]
                )

        soniox._ws.on_send = on_send
        ws.disconnect()
        await until(lambda: not rt.state.active)
        soniox._ws.gate.set()
        await asyncio.wait_for(run_task, timeout=20)
        expected = prefix + b''.join(held)
        assert soniox._ws.pcm == expected
        assert soniox._ws.sent[-1] == ''
        assert emitted['last']
        assert soniox._ws.closed and soniox._send_task.done() and soniox._recv_task.done()
        assert 'LAST' in persisted
        assert order.index(('persist', 'LAST')) < order.index(('finalize', 'conv-1'))
        assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == 0
        assert box['result'].reason == 'lifetime_done'
        assert box['result'].task_name.endswith('heartbeat')
        assert rt.state.live_transcription_failed is False
        assert rt.state.stt_terminal_failure is False
        assert len(dials) == 1
    finally:
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_shutdown_deadline_bounds_blocked_writer_and_meters_unwritten_once(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_DELIVERY_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(replay_delivery_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    persisted: list[str] = []
    stub_transcript_persistence(rt, persisted, monkeypatch)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    labels = dict(source='parakeet', successor='soniox')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        frames = [marker(n, 2) for n in range(3)]
        for frame in frames:
            ws.feed_audio(frame)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= sum(len(frame) for frame in frames))
        actual.stt_socket.raw.fail('first_text_deadline')
        last = marker(99, 2)
        ws.feed_audio(last)
        await until(lambda: isinstance(actual.stt_socket, ReplayTailSocket))
        soniox = raws[-1]
        prefix = b''.join(frames) + last
        await until(lambda: soniox._ws.byte_count >= len(prefix))
        soniox._ws.gate.clear()
        held = marker(7, 2)
        ws.feed_audio(held)
        await until(lambda: bool(actual.stt_socket.tail) or soniox._send_queue.qsize() or soniox._send_queue.inflight)
        monkeypatch.setattr(Transport, 'abort', lambda self: setattr(self, 'closed', True), raising=False)
        ws.disconnect()
        await asyncio.wait_for(run_task, timeout=10)
        skipped = REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before
        assert skipped == pytest.approx(len(held) / (2 * 16000))
        assert soniox._ws.byte_count == len(prefix)
        assert len(dials) == 1
        assert rt.receiver.stt_drain_complete.is_set()
        assert soniox._ws.closed
        assert soniox._send_task.done() and soniox._recv_task.done()
        assert actual.stt_socket is None
    finally:
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        soniox._ws.gate.set()
        await stop(raws)


@pytest.mark.asyncio
async def test_never_eos_drain_is_bounded_and_aborts_transports(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_DELIVERY_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(replay_delivery_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    stub_transcript_persistence(rt, [], monkeypatch)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        frames = [marker(n, 2) for n in range(3)]
        for frame in frames:
            ws.feed_audio(frame)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= sum(len(frame) for frame in frames))
        actual.stt_socket.raw.fail('first_text_deadline')
        ws.feed_audio(marker(99, 2))
        await until(lambda: isinstance(actual.stt_socket, ReplayTailSocket))
        soniox = raws[-1]
        leg = actual.stt_socket
        original_drain = leg.drain_and_close

        async def stubborn_drain():
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await rt.state.shutdown_event.wait()
            await original_drain()

        monkeypatch.setattr(leg, 'drain_and_close', stubborn_drain)
        monkeypatch.setattr(Transport, 'abort', lambda self: setattr(self, 'closed', True), raising=False)
        ws.disconnect()
        began = time.monotonic()
        await asyncio.wait_for(run_task, timeout=10)
        elapsed = time.monotonic() - began
        assert elapsed < 1.0
        assert rt.receiver.stt_drain_complete.is_set()
        assert actual.stt_socket is None
        assert soniox._ws.closed
        assert soniox._send_task.done() and soniox._recv_task.done()
        tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task() and not task.done()]
        assert not tasks
    finally:
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_departure_mid_connected_prefix_adopts_and_drains(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    persisted: list[str] = []
    stub_transcript_persistence(rt, persisted, monkeypatch)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        frames = [marker(n, 2) for n in range(3)]
        for frame in frames:
            ws.feed_audio(frame)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= sum(len(frame) for frame in frames))
        actual.stt_socket.raw.fail('first_text_deadline')
        last = marker(99, 2)
        ws.feed_audio(last)
        await until(lambda: bool(raws))
        soniox = raws[-1]
        soniox._ws.gate.clear()
        ws.disconnect()
        await until(lambda: actual.client_closing)
        soniox._ws.gate.set()
        await asyncio.wait_for(run_task, timeout=20)
        assert soniox._ws.pcm == b''.join(frames) + last
        assert soniox._ws.closed
        assert len(dials) == 1
        assert rt.state.live_transcription_failed is False
    finally:
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_post_close_adoption_inherits_drain_and_delivers_tail(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    persisted: list[str] = []
    order: list = []
    stub_transcript_persistence(rt, persisted, monkeypatch, order)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    box: dict = {}
    watch_supervise(rt, box)
    rt.conversations.process_conversation = AsyncMock(
        side_effect=lambda *_a, **_k: order.append(('finalize', 'conv-1')) or True
    )
    labels = dict(source='parakeet', successor='soniox')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    prefix_hold = asyncio.Event()
    real_replay_chunks = receiver_module.replay_chunks

    async def held_replay(*args, **kwargs):
        await prefix_hold.wait()
        return await real_replay_chunks(*args, **kwargs)

    monkeypatch.setattr(receiver_module, 'replay_chunks', held_replay)
    start_tail_calls: list = []
    real_start_tail = ReplayTailSocket.start_tail

    def start_tail_spy(self, **kwargs):
        start_tail_calls.append(
            {
                'host_active': self.host.state.active,
                'tail_bytes': self._tail_bytes,
                'deadline': actual.shutdown_deadline,
                'draining_before': self._draining,
            }
        )
        result = real_start_tail(self, **kwargs)
        start_tail_calls[-1]['draining_after'] = self._draining
        return result

    monkeypatch.setattr(ReplayTailSocket, 'start_tail', start_tail_spy)
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        frames = [marker(n, 2) for n in range(3)]
        for frame in frames:
            ws.feed_audio(frame)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= sum(len(frame) for frame in frames))
        actual.stt_socket.raw.fail('first_text_deadline')
        await until(lambda: actual._replay_delivery is not None)
        soniox = raws[-1]
        tail = [marker(7, 2), marker(8, 2)]
        for packet in tail:
            ws.feed_audio(packet)
        delivery = actual._replay_delivery
        await until(lambda: delivery._tail_bytes >= sum(len(packet) for packet in tail))
        emitted = {'last': False}

        def on_send():
            if not emitted['last'] and soniox._ws.sent and soniox._ws.sent[-1] == '':
                emitted['last'] = True
                soniox._stream_transcript(
                    [{'text': 'LAST', 'start': 0.0, 'end': 0.5, 'speaker': 'speaker_0', 'is_user': False}]
                )

        soniox._ws.on_send = on_send
        assert len(dials) == 1
        ws.disconnect()
        await until(lambda: actual.client_closing and not rt.state.active)
        deadline = actual.shutdown_deadline
        assert deadline is not None
        prefix_hold.set()
        await asyncio.wait_for(run_task, timeout=20)
        assert start_tail_calls
        adoption = start_tail_calls[-1]
        assert adoption['host_active'] is False
        assert adoption['tail_bytes'] >= sum(len(packet) for packet in tail)
        assert adoption['deadline'] == deadline == actual.shutdown_deadline
        assert adoption['draining_before'] is False
        assert adoption['draining_after'] is True
        assert soniox._ws.pcm == b''.join(frames) + b''.join(tail)
        assert soniox._ws.sent[-1] == ''
        assert emitted['last']
        assert soniox._ws.closed and soniox._send_task.done() and soniox._recv_task.done()
        assert 'LAST' in persisted
        assert order.index(('persist', 'LAST')) < order.index(('finalize', 'conv-1'))
        assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == 0
        assert box['result'].reason == 'lifetime_done'
        assert rt.state.live_transcription_failed is False
        assert rt.state.stt_terminal_failure is False
        assert len(dials) == 1
    finally:
        prefix_hold.set()
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_post_close_adoption_deadline_bounds_held_wire_and_meters_once(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_DELIVERY_SECONDS', 0.6, raising=False)
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(replay_delivery_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    stub_transcript_persistence(rt, [], monkeypatch)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    labels = dict(source='parakeet', successor='soniox')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    prefix_hold = asyncio.Event()
    real_replay_chunks = receiver_module.replay_chunks

    async def held_replay(*args, **kwargs):
        await prefix_hold.wait()
        return await real_replay_chunks(*args, **kwargs)

    monkeypatch.setattr(receiver_module, 'replay_chunks', held_replay)
    monkeypatch.setattr(Transport, 'abort', lambda self: setattr(self, 'closed', True), raising=False)
    prefix_bytes = sum(len(marker(n, 2)) for n in range(3))
    tail_hold = asyncio.Event()
    tail_write_attempted = asyncio.Event()
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        frames = [marker(n, 2) for n in range(3)]
        for frame in frames:
            ws.feed_audio(frame)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= sum(len(frame) for frame in frames))
        actual.stt_socket.raw.fail('first_text_deadline')
        await until(lambda: actual._replay_delivery is not None)
        soniox = raws[-1]
        tail = marker(7, 2)
        ws.feed_audio(tail)
        delivery = actual._replay_delivery
        await until(lambda: delivery._tail_bytes >= len(tail))
        real_send = soniox._ws.send

        async def held_tail_send(data):
            if isinstance(data, bytes) and soniox._ws.byte_count >= prefix_bytes:
                tail_write_attempted.set()
                await tail_hold.wait()
            return await real_send(data)

        monkeypatch.setattr(soniox._ws, 'send', held_tail_send)
        assert len(dials) == 1
        began = time.monotonic()
        ws.disconnect()
        await until(lambda: actual.client_closing and not rt.state.active)
        deadline = actual.shutdown_deadline
        assert deadline is not None
        prefix_hold.set()
        await asyncio.wait_for(run_task, timeout=10)
        elapsed = time.monotonic() - began
        assert elapsed < 1.5
        assert tail_write_attempted.is_set()
        assert replay_delivery_module.clock() >= deadline
        assert actual.shutdown_deadline == deadline
        assert soniox._ws.byte_count == prefix_bytes
        skipped = REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before
        assert skipped == pytest.approx(len(tail) / (2 * 16000))
        assert len(dials) == 1
        assert rt.receiver.stt_drain_complete.is_set()
        assert soniox._ws.closed
        assert soniox._send_task.done() and soniox._recv_task.done()
        orphans = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and not task.done() and 'stt_' in (task.get_name() or '')
        ]
        assert not orphans
    finally:
        prefix_hold.set()
        tail_hold.set()
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_terminal_state_and_deletion_do_not_wait_for_receive(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    for deletion in (False, True):
        ws = ClientSocket()
        rt = make_runtime(ws, monkeypatch)
        stub_transcript_persistence(rt, [], monkeypatch)
        actual = rt.receiver
        monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
        monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
        raws: list = []
        dials: list = []
        wire_providers(monkeypatch, rt, raws, dials)
        run_task = asyncio.create_task(rt.run())
        try:
            await until(lambda: actual.stt_socket is not None)
            if deletion:
                rt.request.owner_persistence_blocked.set()
            else:
                rt.state.stt_terminal_failure = True
            ws.disconnect()
            await asyncio.wait_for(run_task, timeout=10)
            assert rt.state.live_transcription_failed is True
        finally:
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)
            await stop(raws)


@pytest.mark.asyncio
async def test_error_close_is_not_ordinary_and_does_not_drain(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    stub_transcript_persistence(rt, [], monkeypatch)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    box: dict = {}
    watch_supervise(rt, box)
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        ws.feed_audio(marker(1, 2))
        ws.incoming.put_nowait({'type': 'websocket.disconnect', 'code': 1011})
        await until(lambda: actual.client_closing)
        ws.client_state = WebSocketState.DISCONNECTED
        ws.application_state = WebSocketState.DISCONNECTED
        began = time.monotonic()
        await asyncio.wait_for(run_task, timeout=10)
        assert time.monotonic() - began < 5.0
        assert box['result'].reason in {'disconnect', 'lifetime_done'}
        assert rt.state.live_transcription_failed is True
    finally:
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_departure_with_no_connected_candidate_meters_tail_and_dials_nothing(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    stub_transcript_persistence(rt, [], monkeypatch)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    labels = dict(source='parakeet', successor='unknown')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    box: dict = {}
    watch_supervise(rt, box)
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)

        async def no_candidate(*args, **kwargs):
            raise ConnectionError('no candidate')

        monkeypatch.setattr(receiver_module, 'process_audio_parakeet', no_candidate)
        held = marker(5, 2)
        ws.feed_audio(held)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= len(held))
        actual.stt_socket.raw.fail('first_text_deadline')
        ws.feed_audio(marker(6, 2))
        await until(lambda: actual._replay_tail_bytes > 0)
        owed = actual._replay_tail_bytes
        ws.disconnect()
        await asyncio.wait_for(run_task, timeout=10)
        assert len(dials) == 0
        assert box['result'].reason in {'disconnect', 'lifetime_done'}
        assert REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before == pytest.approx(owed / (2 * 16000))
        assert rt.receiver.stt_drain_complete.is_set()
    finally:
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_written_tail_packet_is_never_metered_under_held_confirmation(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_DELIVERY_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(replay_delivery_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    stub_transcript_persistence(rt, [], monkeypatch)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    labels = dict(source='parakeet', successor='soniox')
    skipped_before = REPLAY_SKIPPED.labels(**labels)._value.get()
    confirm_hold = asyncio.Event()
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        frames = [marker(n, 2) for n in range(3)]
        for frame in frames:
            ws.feed_audio(frame)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= sum(len(frame) for frame in frames))
        actual.stt_socket.raw.fail('first_text_deadline')
        ws.feed_audio(marker(99, 2))
        await until(lambda: isinstance(actual.stt_socket, ReplayTailSocket))
        soniox = raws[-1]
        leg = actual.stt_socket
        real_confirm = replay_delivery_module.await_frozen_writes

        async def held_confirm(socket, deadline):
            await confirm_hold.wait()
            return await real_confirm(socket, deadline)

        monkeypatch.setattr(replay_delivery_module, 'await_frozen_writes', held_confirm)
        first, second = marker(7, 2), marker(8, 2)
        ws.feed_audio(first)
        baseline = soniox._ws.byte_count
        await until(lambda: soniox._ws.byte_count >= baseline + len(first))
        ws.feed_audio(second)
        await until(lambda: bool(leg.tail))
        ws.disconnect()
        await asyncio.wait_for(run_task, timeout=10)
        skipped = REPLAY_SKIPPED.labels(**labels)._value.get() - skipped_before
        assert skipped == pytest.approx(len(second) / (2 * 16000))
        assert soniox._ws.pcm.endswith(first)
        assert soniox._ws.sent.count('') <= 1
        assert soniox._send_task.done() and soniox._recv_task.done()
    finally:
        confirm_hold.set()
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_crash_cancel_aborts_pending_drain_without_late_callbacks(monkeypatch):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_DELIVERY_SECONDS', 5.0, raising=False)
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(replay_delivery_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    persisted: list[str] = []
    stub_transcript_persistence(rt, persisted, monkeypatch)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        frames = [marker(n, 2) for n in range(3)]
        for frame in frames:
            ws.feed_audio(frame)
        ring_bytes = lambda: sum(len(data) for _, data in (actual._window_ring() or []).snapshot())
        await until(lambda: ring_bytes() >= sum(len(frame) for frame in frames))
        actual.stt_socket.raw.fail('first_text_deadline')
        ws.feed_audio(marker(99, 2))
        await until(lambda: isinstance(actual.stt_socket, ReplayTailSocket))
        soniox = raws[-1]
        emitted = {'last': False}

        def on_send():
            if not emitted['last'] and soniox._ws.sent and soniox._ws.sent[-1] == '':
                emitted['last'] = True
                soniox._stream_transcript(
                    [{'text': 'LAST', 'start': 0.0, 'end': 0.5, 'speaker': 'speaker_0', 'is_user': False}]
                )

        soniox._ws.on_send = on_send
        soniox._ws.gate.clear()
        ws.feed_audio(marker(7, 2))
        ws.disconnect()
        await until(lambda: actual.client_closing)
        run_task.cancel()
        await asyncio.wait_for(asyncio.shield(asyncio.gather(run_task, return_exceptions=True)), timeout=10)
        assert rt.receiver.stt_drain_complete.is_set()
        assert soniox._ws.closed
        assert soniox._send_task.done() and soniox._recv_task.done()
        assert not emitted['last']
        assert 'LAST' not in persisted
        orphans = [
            task
            for task in asyncio.all_tasks()
            if task is not asyncio.current_task() and not task.done() and 'stt_shutdown' in (task.get_name() or '')
        ]
        assert not orphans
    finally:
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
@pytest.mark.parametrize('exit_mode', ['lifetime_done', 'disconnect'])
async def test_close_deadline_bounds_monitored_drain_and_cancel_ack(monkeypatch, exit_mode):
    monkeypatch.setattr(st, 'stt_service_models', ['parakeet-window', 'soniox'])
    monkeypatch.setattr(window, 'get_stt_client', lambda: Client())
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_DELIVERY_SECONDS', 0.15, raising=False)
    monkeypatch.setattr(receiver_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    monkeypatch.setattr(replay_delivery_module, 'SHUTDOWN_CLEANUP_SECONDS', 0.05, raising=False)
    ws = ClientSocket()
    rt = make_runtime(ws, monkeypatch)
    rt.limits = replace(rt.limits, bg_drain_timeout=0.3)
    persisted: list[str] = []
    stub_transcript_persistence(rt, persisted, monkeypatch)
    persist_attempted = asyncio.Event()
    release = asyncio.Event()

    async def held_update(conversation, segments, photos, finished_at, started_at, **kwargs):
        assert [segment.text for segment in segments] == ['LAST']
        persist_attempted.set()
        await release.wait()
        persisted.extend(segment.text for segment in segments)
        return (conversation, segments, [])

    rt.transcripts._update_live_conversation = held_update
    rt.conversations.process_conversation = AsyncMock(return_value=True)
    actual = rt.receiver
    monkeypatch.setattr(actual, '_run_on_listen_loop', lambda action, segments: action(segments))
    monkeypatch.setattr(actual, '_capture', lambda *a, **k: None)

    async def held_drain():
        actual._enqueue_stt_segments(
            [{'text': 'LAST', 'start': 0.0, 'end': 0.5, 'speaker': 'speaker_0', 'is_user': False}]
        )
        await release.wait()

    monkeypatch.setattr(actual, '_drain_stt_sockets', held_drain)
    if exit_mode == 'disconnect':
        rt._heartbeat = lambda: rt.state.shutdown_event.wait()
    raws: list = []
    dials: list = []
    wire_providers(monkeypatch, rt, raws, dials)
    teardown_started: dict = {}
    real_teardown = rt._teardown

    async def timed_teardown():
        teardown_started['at'] = time.monotonic()
        release.set()
        await real_teardown()

    rt._teardown = timed_teardown
    drain_calls: list = []
    real_drain = rt.task_supervisor.drain_monitored

    async def drain_spy(**kwargs):
        drain_calls.append(kwargs)
        return await real_drain(**kwargs)

    rt.task_supervisor.drain_monitored = drain_spy
    worker: asyncio.Task | None = None
    box: dict = {}
    watch_supervise(rt, box)
    run_task = asyncio.create_task(rt.run())
    try:
        await until(lambda: actual.stt_socket is not None)
        ws.feed_audio(marker(1, 2))
        await until(lambda: rt.state.first_audio_byte_timestamp is not None)

        async def held_worker():
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await release.wait()
                raise

        worker = rt.task_supervisor.create_lifetime_task(held_worker(), name='held_worker')
        departed = replay_delivery_module.clock()
        if exit_mode == 'lifetime_done':
            ws.disconnect()
        else:
            ws.incoming.put_nowait({'type': 'websocket.disconnect', 'code': 1000})
        await asyncio.wait_for(run_task, timeout=3)
        bound = 0.15 + 0.05
        assert box['result'].reason == exit_mode
        assert teardown_started['at'] - departed <= bound + 0.15
        assert drain_calls and drain_calls[-1].get('deadline') is not None
        assert persist_attempted.is_set()
        assert worker.cancelled()
        rt.conversations.process_conversation.assert_awaited()
        assert len(dials) == 0
    finally:
        release.set()
        run_task.cancel()
        await asyncio.gather(run_task, return_exceptions=True)
        if worker is not None:
            worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)
        await stop(raws)


@pytest.mark.asyncio
async def test_stalled_soniox_queue_during_drain_reports_local_capacity(monkeypatch):
    transport = Transport()
    raw = SafeSonioxSocket(transport, lambda _: None, asyncio.get_running_loop())
    assert raw.recovery_enabled

    monkeypatch.setattr(raw, 'replay_limits', ReplayLimits(queue_wait_seconds=0.01))
    raw._send_task.cancel()
    await asyncio.gather(raw._send_task, return_exceptions=True)
    while not raw._send_queue.full():
        raw._send_queue.put_nowait(b'\x01\x00')
    try:
        assert not await raw.wait_send_capacity()
        assert raw.typed_death_reason == 'capacity_full'
        assert raw.is_connection_dead
    finally:
        await stop([raw])
