"""Hermetic receiver -> pusher -> storage -> conversation readback -> clip regression.

Runs the actual listen receiver frame/epoch logic (CaptureTimeline, epoch
translators, GatedSTTSocket send accounting), the actual ListenPusherSession
run buffering and flush, the actual pusher websocket handler (capability ack,
continuity reconciliation, batch splitting, span-carrying uploads), the actual
storage upload/listing/grouping/merge, the actual fenced conversation
persistence, and the actual clip helper — against in-memory doubles for the
outermost IO only.

Fail-old / pass-new: the same burst scenario runs once with AUDIO_TIMELINE_V2
off — which *is* the legacy calculation (chunk timestamp = last arrival minus
the whole buffered duration while segments use first-audio + provider time) —
and once with v2 on. The legacy run is asserted to misplace the audio
(the acceptance criterion fails on the old calculation); the v2 run is asserted
to select the exact phrase bytes.
"""

import asyncio
import struct
import time
from collections import Counter
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

import routers.pusher as pusher
import routers.listen.receiver as receiver_module
import utils.other.storage as storage_module
from database import conversations as conversations_db
from routers.listen import transcripts as transcripts_module
from routers.listen.contracts import ListenLimits, ListenSessionState
from routers.listen.receiver import ListenReceiver
from routers.listen.transcripts import ConversationCache, TranscriptProcessor
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.audio_timeline import coverage_outcome
from utils.audio import AudioRingBuffer
from utils.listen_pusher_session import ListenPusherSession, ListenPusherSessionConfig, ListenPusherSessionDeps
from utils.product_telemetry import set_product_telemetry_client_for_tests
from utils.stt.vad_gate import GatedSTTSocket
from utils.stt import vad_gate as vad_gate_module
from utils.stt.soniox import SafeSonioxSocket
from utils.stt.streaming import SafeModulateSocket

RATE = 16000
UID = 'uid-at'
CONV1 = 'conv-at-1'
CONV2 = 'conv-at-2'
T0 = 1_700_000_000.0


@pytest.fixture
def anyio_backend():
    return 'asyncio'


def _phrase(marker: int, seconds: float) -> bytes:
    """Identifiable PCM16: every sample encodes (marker, index-in-phrase)."""
    samples = int(seconds * RATE)
    out = bytearray()
    for i in range(samples):
        out += ((marker * 7919 + i) & 0x7FFF).to_bytes(2, 'little')
    return bytes(out)


def _silence(seconds: float) -> bytes:
    return b'\x00\x00' * int(seconds * RATE)


def _slice(pcm: bytes, start_s: float, end_s: float) -> bytes:
    return pcm[int(start_s * RATE) * 2 : int(end_s * RATE) * 2]


# ---------------------------------------------------------------------------
# In-memory GCS double: blobs carry metadata (the v2 span contract).
# ---------------------------------------------------------------------------
class _Writer:
    def __init__(self, blob):
        self.blob = blob
        self.buf = bytearray()

    def write(self, data):
        self.buf.extend(data)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.blob._store(bytes(self.buf))


class FakeBlob:
    def __init__(self, bucket, name):
        self.bucket = bucket
        self.name = name
        self._data = None
        self.metadata = None

    @property
    def size(self):
        return len(self._data) if self._data is not None else None

    def _store(self, data):
        self._data = data
        self.bucket.blobs[self.name] = self

    def exists(self):
        return self._data is not None

    def open(self, mode, content_type=None):
        assert mode == 'wb'
        return _Writer(self)

    def download_as_bytes(self):
        if self._data is None:
            raise FileNotFoundError(self.name)
        return self._data

    def delete(self):
        self.bucket.blobs.pop(self.name, None)


class FakeBucket:
    def __init__(self):
        self.blobs = {}

    def blob(self, name):
        return self.blobs.get(name) or FakeBlob(self, name)

    def list_blobs(self, prefix=None):
        return [self.blobs[name] for name in sorted(self.blobs) if name.startswith(prefix)]


class FakeStorageClient:
    def __init__(self):
        self._buckets = {}

    def bucket(self, name):
        return self._buckets.setdefault(name, FakeBucket())


# ---------------------------------------------------------------------------
# Websocket doubles
# ---------------------------------------------------------------------------
class FakeListenWebSocket:
    """Client-side /v4/listen websocket: preloaded frames + a controllable clock."""

    def __init__(self, frames, clock):
        self.frames = deque(frames)
        self.clock = clock
        self.sent_json = []

    async def send_json(self, payload):
        self.sent_json.append(payload)

    async def close(self, code=1000, reason=None):
        return None

    async def receive(self):
        if self.frames:
            frame = self.frames.popleft()
            advance = frame.pop('_advance', None)
            if advance is not None:
                self.clock['wall'] += advance[0]
                self.clock['mono'] += advance[1]
            return frame
        await asyncio.sleep(0)
        raise WebSocketDisconnect(1000)


class FakeServerWebSocket:
    """Pusher-side socket: frames arrive from the listen session's client double."""

    def __init__(self):
        self.frames = deque()
        self.client_inbox = deque()
        self.client_state = WebSocketState.CONNECTED
        self.close_code = None

    async def accept(self):
        return None

    async def close(self, code=1000, reason=None):
        self.close_code = code
        self.client_state = WebSocketState.DISCONNECTED

    async def receive_bytes(self):
        await asyncio.sleep(0)
        if self.frames:
            return self.frames.popleft()
        await asyncio.sleep(0.05)
        if self.frames:
            return self.frames.popleft()
        raise WebSocketDisconnect(1000)

    async def send_bytes(self, data):
        self.client_inbox.append(data)


class FakePusherClientWebSocket:
    """Listen-side client socket: sends into the server's frame deque."""

    def __init__(self, server_ws):
        self.server = server_ws

    async def send(self, data):
        if self.server.client_state != WebSocketState.CONNECTED:
            raise WebSocketDisconnect(1006)
        self.server.frames.append(data)

    async def recv(self):
        while True:
            if self.server.client_inbox:
                return self.server.client_inbox.popleft()
            if self.server.client_state != WebSocketState.CONNECTED:
                raise WebSocketDisconnect(1006)
            await asyncio.sleep(0.01)

    async def close(self, code=1000):
        if self.server.client_state == WebSocketState.CONNECTED:
            await self.server.close(code)


# ---------------------------------------------------------------------------
# Fake provider socket: the GatedSTTSocket wrapper accounts accepted sends on
# the epoch translator; segments are emitted at provider-relative times.
# ---------------------------------------------------------------------------
class FakeProviderSocket:
    def __init__(self):
        self.accepted_samples = 0

    def send(self, data):
        self.accepted_samples += len(data) // 2
        return True

    def finalize(self):
        return None

    def finish(self):
        return None

    @property
    def is_connection_dead(self):
        return False

    @property
    def death_reason(self):
        return None


class _TelemetryClient:
    def __init__(self):
        self.events = []

    def capture(self, **event):
        self.events.append(event)


def _frame(pcm: bytes, advance_wall: float, advance_mono: float):
    return {'bytes': pcm, '_advance': (advance_wall, advance_mono)}


def _disconnect_frame():
    return {'type': 'websocket.disconnect', 'code': 1000}


def _provider_segment(start_s, end_s, text):
    return {
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'start': start_s,
        'end': end_s,
        'text': text,
        'is_user': False,
        'person_id': None,
    }


@pytest.fixture
def telemetry():
    client = _TelemetryClient()
    set_product_telemetry_client_for_tests(client)
    yield client
    set_product_telemetry_client_for_tests(None)


@pytest.fixture
def gcs(monkeypatch):
    client = FakeStorageClient()
    monkeypatch.setattr(storage_module, '_get_storage_client', lambda: client)
    monkeypatch.setattr(storage_module.users_db, 'get_data_protection_level', lambda uid: 'standard')
    return client


@pytest.fixture
def pusher_env(monkeypatch):
    audio_files_by_conversation = {}

    monkeypatch.setattr(pusher, 'get_audio_bytes_webhook_seconds', lambda uid: None)
    monkeypatch.setattr(pusher, 'is_audio_bytes_app_enabled', lambda uid: False)
    monkeypatch.setattr(pusher.users_db, 'get_user_private_cloud_sync_enabled', lambda uid: True)
    monkeypatch.setattr(pusher.users_db, 'get_data_protection_level', lambda uid: 'standard')
    monkeypatch.setattr(pusher, 'PUSHER_ACTIVE_WS_CONNECTIONS', MagicMock())
    monkeypatch.setattr(pusher, 'PUSHER_PRIVATE_CLOUD_UPLOAD_DROPS', MagicMock())
    monkeypatch.setattr(pusher, 'is_audio_merge_dispatch_enabled', lambda: False)
    monkeypatch.setattr(pusher.ReadinessGate, 'is_serving', lambda: True)

    def update_conversation(uid, conversation_id, data):
        row = audio_files_by_conversation.setdefault(conversation_id, {'audio_files': []})
        if 'audio_files' in data:
            row['audio_files'] = data['audio_files']
        return True

    monkeypatch.setattr(pusher.conversations_db, 'update_conversation', update_conversation)
    return audio_files_by_conversation


class _Stack:
    """One hermetic listen session wired to real pusher server tasks."""

    def __init__(self, monkeypatch, *, v2: bool, conversation_id: str):
        self.clock = {'wall': T0, 'mono': 0.0}
        self.v2 = v2
        monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if v2 else 'false')
        # Control the receiver's arrival observations (module-scoped shim).
        self._real_time_module = receiver_module.time
        receiver_module.time = SimpleNamespace(time=lambda: self.clock['wall'], monotonic=lambda: self.clock['mono'])
        self.segments_collected = []

        state = ListenSessionState()
        state.current_conversation_id = conversation_id
        self.host = SimpleNamespace(
            request=SimpleNamespace(
                uid=UID, websocket=None, codec='pcm16', sample_rate=RATE, channels=1, source='desktop'
            ),
            state=state,
            limits=ListenLimits(),
            is_multi_channel=False,
            use_custom_stt=False,
            audio_bytes_send=None,
            transcripts=SimpleNamespace(enqueue=self.segments_collected.extend),
            client_device_context=SimpleNamespace(platform='desktop'),
            stt_service='fake',
            spawn=self._spawn,
        )
        self.tasks = []
        self.receiver = ListenReceiver(self.host, [], {})
        if self.receiver.capture_timeline is not None:
            state.conversations_awaiting_capture_origin.add(conversation_id)

        callbacks, _modulate, self.epoch = self.receiver._build_stt_callbacks()
        self.provider_callback = callbacks
        self.provider = FakeProviderSocket()
        self.receiver.stt_socket = GatedSTTSocket(self.provider, gate=None, send_tracker=self.epoch)

        self.conversation_ids = [conversation_id]
        self.server_ws = None
        self.session = None

    def _spawn(self, coro, *, name):
        task = asyncio.create_task(coro)
        self.tasks.append(task)
        return task

    def build_session(self):
        current = {'id': self.conversation_ids[0]}

        async def connect_to_pusher(uid, sample_rate, retries=3, is_active=None, client_kind='unknown', **kwargs):
            return FakePusherClientWebSocket(self.server_ws)

        session = ListenPusherSession(
            ListenPusherSessionConfig(
                uid=UID,
                session_id='session-at',
                sample_rate=RATE,
                is_multi_channel=False,
                language='en',
                audio_bytes_enabled=True,
                max_segment_buffer_size=100,
                max_audio_buffer_size=10 * 1024 * 1024,
                max_pending_requests=10,
                max_pending_speaker_sample_requests=10,
                client_kind='test',
                audio_timeline_v2=self.v2,
            ),
            ListenPusherSessionDeps(
                get_current_conversation_id=lambda: current['id'],
                is_active=lambda: True,
                shutdown_event=asyncio.Event(),
                get_byok_keys=lambda: {},
                on_conversation_processed=lambda cid: None,
                wait_for_event=self._wait_or_timeout,
                connect_to_pusher=connect_to_pusher,
            ),
        )
        self.session = session
        self._current = current
        self.host.audio_bytes_send = session.audio_bytes_send
        return session

    @staticmethod
    async def _wait_or_timeout(event, seconds):
        try:
            await asyncio.wait_for(event.wait(), timeout=seconds)
            return True
        except asyncio.TimeoutError:
            return False

    def start_pusher_server(self):
        self.server_ws = FakeServerWebSocket()
        self.server_task = asyncio.create_task(
            pusher._websocket_util_trigger(self.server_ws, UID, RATE, 'test', 2 if self.v2 else None)
        )

    async def stop_pusher_server(self):
        # Exhausting the server's frames ends receive_tasks; the drain flushes
        # every queued/batched chunk before the task completes.
        deadline = time.monotonic() + 30
        while not self.server_task.done() and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
        if not self.server_task.done():
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
        server, self.server_ws = self.server_ws, None
        return server

    def restore(self):
        receiver_module.time = self._real_time_module


async def _run_receiver_frames(stack, frames):
    stack.host.request.websocket = FakeListenWebSocket(frames, stack.clock)
    await stack.receiver.receive_data()


async def _persist_collected(stack, store, monkeypatch):
    """Run the real TranscriptProcessor v2 batch path over the collected segments."""
    if not stack.segments_collected:
        return

    def _row(cid):
        return store.rows.get(('users', UID, 'conversations', cid)) or {}

    class _Persistence:
        @staticmethod
        async def call(fn, *args, **kwargs):
            if fn is conversations_db.update_conversation_segments:
                return fn(*args, **kwargs)
            if fn is conversations_db.update_conversation_finished_at:
                _uid, cid, finished = args
                _row(cid)['finished_at'] = finished
                return True
            if fn is conversations_db.get_conversation:
                return dict(_row(args[1]))
            return None

    async def loader(conversation_id):
        return dict(_row(conversation_id))

    host = SimpleNamespace(
        request=SimpleNamespace(uid=UID, websocket=stack.host.request.websocket),
        state=stack.host.state,
        persistence=_Persistence(),
        speakers=SimpleNamespace(
            segment_assignments={},
            speaker_to_person={},
            segment_identity_status={},
            person_embeddings={},
            queue=None,
        ),
        conversations=SimpleNamespace(create_new_in_progress_conversation=_async_noop),
        onboarding_handler=None,
        transcript_send=None,
        pusher_enabled=True,
        user_has_credits=True,
        client_kind='test',
        language='en',
        send_event=lambda event: None,
        emit_speaker_suggestion=lambda *args, **kwargs: None,
        complete_live_transcription=lambda: None,
    )
    processor = object.__new__(TranscriptProcessor)
    processor.host = host
    processor.cache = ConversationCache(loader)
    processor.current_session_segments = {}
    processor.suggested_segments = set()
    processor.speaker_id_allocator = transcripts_module.ConversationSpeakerIdAllocator()
    processor.translation_coordinator = None
    processor.translation_language = None
    processor._v2_committed_ids = set()
    processor._v2_photos_committed = False
    processor._v2_photos_requeued = False
    processor._v2_retry_counts = {}
    processor._v2_retry_until = 0.0
    processor.segment_buffer = deque()

    segments = list(stack.segments_collected)
    stack.segments_collected.clear()
    await processor._process_v2_batches(segments, [], {})


async def _async_noop(*args, **kwargs):
    return None


def _decode_segments(row):
    return conversations_db._decode_transcript_segments_strict(
        UID, row.get('transcript_segments', []), bool(row.get('transcript_segments_compressed'))
    )


def _seed_conversation(store, cid):
    store.rows[('users', UID, 'conversations', cid)] = {
        'id': cid,
        'status': 'in_progress',
        'created_at': datetime.fromtimestamp(T0 - 60, tz=timezone.utc),
        # Creation-wall placeholders; the v2 pin replaces started_at with the
        # first accepted audio origin in the same transaction as the marker.
        'started_at': datetime.fromtimestamp(T0 - 60, tz=timezone.utc),
        'finished_at': datetime.fromtimestamp(T0 - 60, tz=timezone.utc),
        'structured': {},
        'transcript_segments': [],
    }


@pytest.mark.parametrize('first,second', [('modulate', 'soniox'), ('soniox', 'modulate')])
@pytest.mark.parametrize('codec', ['pcm16', 'opus'])
async def test_prod_order_failover_keeps_text_and_locates_second_leg_audio(monkeypatch, first, second, codec):
    """Prod-shaped adapter replay: parser messages, active gate, Opus/PCM.

    The 31-minute logical inter-arrival hiatus exercises capture anchors
    without a long sleep. Opus uses a deterministic decoder double because
    the native codec library is not available in the hermetic test lane.
    """
    monkeypatch.setenv('STT_CONNECT_ORDER_FROM_CONFIG', 'true')
    monkeypatch.setattr(vad_gate_module, '_get_ort_session', lambda: None)
    monkeypatch.setattr(vad_gate_module.VADStreamingGate, '_run_vad', lambda self, pcm: any(pcm))
    stack = _Stack(monkeypatch, v2=True, conversation_id=CONV1)
    stack.host.request.codec = codec
    stack.host.state.audio_ring_buffer = AudioRingBuffer(30, RATE)
    store = StrictFirestore()
    _seed_conversation(store, CONV1)
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    decoded_by_packet = {}

    class OpusDecoder:
        def decode(self, packet, frame_size):
            return decoded_by_packet[packet]

    if codec == 'opus':
        stack.receiver.opus_decoder = OpusDecoder()

    def frames(marker):
        result = []
        pcm = _phrase(marker, 4.0)
        chunk = RATE  # 0.5 second PCM16
        for index in range(8):
            part = pcm[index * chunk : (index + 1) * chunk]
            if codec == 'opus':
                packet = f'op{marker}-{index}'.encode()
                decoded_by_packet[packet] = part
            else:
                packet = part
            result.append(_frame(packet, 0.5, 0.5))
        for index in range(4):
            silence = b'\x00\x00' * (RATE // 2)
            if codec == 'opus':
                packet = f'os{marker}-{index}'.encode()
                decoded_by_packet[packet] = silence
            else:
                packet = silence
            result.append(_frame(packet, 0.5, 0.5))
        # Speech after skipped VAD silence creates a real capture discontinuity
        # in Soniox's continuous provider timeline.
        for index in range(4):
            part = _slice(_phrase(marker + 10, 2.0), index * 0.5, (index + 1) * 0.5)
            if codec == 'opus':
                packet = f'op{marker}-tail-{index}'.encode()
                decoded_by_packet[packet] = part
            else:
                packet = part
            result.append(_frame(packet, 0.5, 0.5))
        result.append(_disconnect_frame())
        return result

    try:
        for leg_index, provider in enumerate((first, second)):
            gate = vad_gate_module.VADStreamingGate(sample_rate=RATE, mode='active', hangover_ms=300)
            stack.receiver.vad_gate = gate
            gated_callback, passthrough_callback, epoch = stack.receiver._build_stt_callbacks()
            raw = FakeProviderSocket()
            stack.receiver.stt_socket = GatedSTTSocket(
                raw, gate=gate, passthrough_audio=provider == 'modulate', send_tracker=epoch
            )
            stack.host.state.active = True
            replay = frames(leg_index + 1)
            if leg_index:
                replay[0]['_advance'] = (31 * 60.5, 31 * 60.5)
            await _run_receiver_frames(stack, replay)
            assert raw.accepted_samples >= 4 * RATE
            callback = passthrough_callback if provider == 'modulate' else gated_callback
            if provider == 'modulate':
                adapter = object.__new__(SafeModulateSocket)
                adapter._stream_transcript = callback
                adapter._preseconds = 0
                adapter._prev_partial_text = ''
                adapter._prev_partial_start_ms = 0
                adapter._prev_partial_word_count = 0
                adapter._observe_served = lambda: None
                adapter._handle_partial_utterance({'text': 'preview only', 'start_ms': 500})
                adapter._handle_utterance(
                    {'text': f'{provider} words', 'start_ms': 500, 'duration_ms': 2500, 'speaker': 1}
                )
            else:
                adapter = object.__new__(SafeSonioxSocket)
                adapter._stream_transcript = callback
                adapter._preseconds = 0
                adapter._pending_segment = None
                adapter._handle_tokens([{'text': 'draft', 'is_final': False, 'start_ms': 500, 'end_ms': 1000}])
                adapter._handle_tokens(
                    [{'text': f'{provider} words ', 'is_final': True, 'start_ms': 500, 'end_ms': 3000}]
                )
                adapter._handle_tokens([{'text': '<fin>', 'is_final': True}])
                adapter._handle_tokens([{'text': 'vad bridge ', 'is_final': True, 'start_ms': 3500, 'end_ms': 5000}])
                adapter._handle_tokens([{'text': 'after gap ', 'is_final': True, 'start_ms': 5000, 'end_ms': 6000}])
            if leg_index:
                if provider == 'modulate':
                    adapter._handle_utterance({'text': 'point word', 'start_ms': 1000, 'duration_ms': 0})
                    adapter._handle_utterance({'text': 'late word', 'start_ms': 30000, 'duration_ms': 1000})
                    adapter._handle_partial_utterance({'text': 'partial tail', 'start_ms': 1100})
                    adapter._flush_partial()
                else:
                    adapter._handle_tokens(
                        [{'text': 'point word ', 'is_final': True, 'start_ms': 1000, 'end_ms': 1000}]
                    )
                    adapter._handle_tokens(
                        [{'text': 'late word ', 'is_final': True, 'start_ms': 30000, 'end_ms': 31000}]
                    )

        expected = Counter({f'{first} words': 1, f'{second} words': 1, 'point word': 1, 'late word': 1})
        expected['vad bridge'] += 1
        expected['after gap'] += 1
        if second == 'modulate':
            expected['partial tail'] += 1
        assert Counter(s['text'] for s in stack.segments_collected) == expected
        second_segment = next(s for s in stack.segments_collected if s['text'] == f'{second} words')
        window = stack.host.state.audio_ring_buffer.get_time_range()
        assert window is not None
        assert window[0] <= second_segment['start'] < second_segment['end'] <= window[1]
        clip = stack.host.state.audio_ring_buffer.extract(second_segment['start'], second_segment['end'])
        assert clip and clip != b'\x00' * len(clip)
        for text in ('late word', 'vad bridge'):
            unplaced = next(s for s in stack.segments_collected if s['text'] == text)
            assert unplaced['audio_alignment'] == 'unplaced'
            assert unplaced['start'] == unplaced['end']
        soniox_before = next(s for s in stack.segments_collected if s['text'] == 'soniox words')
        soniox_after = next(s for s in stack.segments_collected if s['text'] == 'after gap')
        assert soniox_before['audio_capture_run'] != soniox_after['audio_capture_run']

        await _persist_collected(stack, store, monkeypatch)
        persisted = _decode_segments(store.rows[('users', UID, 'conversations', CONV1)])
        # LiveTranscriptMerge may combine adjacent rows while preserving the
        # word stream. Check multiplicity, including adapter final/tail text.
        assert Counter(' '.join(s['text'] for s in persisted).split()) == Counter(' '.join(expected.elements()).split())
        assert not any('soniox words after gap' in s['text'] for s in persisted)
        assert all(s['start'] == s['end'] == -1.0 for s in persisted if s.get('audio_alignment') == 'unplaced')
        assert any(s.get('audio_alignment') == 'unplaced' for s in persisted)
        assert (
            next(s for s in persisted if s['text'] == 'soniox words')['audio_capture_run']
            != next(s for s in persisted if s['text'] == 'after gap')['audio_capture_run']
        )
    finally:
        stack.restore()


async def _run_scenario(monkeypatch, gcs, pusher_env, *, v2: bool):
    """Burst phrase A, logical wall-clock jump, real-time phrase B, reconnect, rollover C."""
    phrase_a = _phrase(1, 10.0)
    phrase_b = _phrase(2, 5.0)
    phrase_c = _phrase(3, 5.0)
    silence = _silence(5.0)

    stack = _Stack(monkeypatch, v2=v2, conversation_id=CONV1)
    store = StrictFirestore()
    _seed_conversation(store, CONV1)
    _seed_conversation(store, CONV2)
    monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: store)
    try:
        stack.build_session()
        stack.start_pusher_server()
        await stack.session.connect()
        assert stack.session.pusher_connected
        if v2:
            assert stack.session.audio_timeline_active, 'pusher must acknowledge v2'

        # Phrase A: a 10 s burst delivered in 20 frames, each arriving 5 ms
        # apart (a client replaying buffered audio after a connectivity gap).
        frames = []
        chunk = int(0.5 * RATE * 2)
        for i in range(20):
            frames.append(_frame(phrase_a[i * chunk : (i + 1) * chunk], 0.005, 0.005))
        # The wall clock steps forward an hour while monotonic advances 50 ms:
        # not an hour of recorded audio, and no new anchor.
        frames.append({'_advance': (3600.0, 0.05)})
        # Five seconds of delivered PCM silence at real-time pace.
        piece = int(0.2 * RATE * 2)
        for i in range(25):
            frames.append(_frame(silence[i * piece : (i + 1) * piece], 0.02, 0.02))
        # Phrase B at real-time pace.
        for i in range(25):
            frames.append(_frame(phrase_b[i * piece : (i + 1) * piece], 0.02, 0.02))
        frames.append(_disconnect_frame())

        await _run_receiver_frames(stack, frames)
        await stack.session._audio_bytes_flush()

        if v2:
            translated = stack.epoch.translate(
                [_provider_segment(0.0, 10.0, 'phrase a'), _provider_segment(15.0, 20.0, 'phrase b')]
            )
            stack.receiver._enqueue_translated_segments(translated, provider='fake')
            rejected_before = stack.epoch.rejected_segments
            dropped = stack.epoch.translate([_provider_segment(25.0, 26.0, 'hallucinated')])
            assert [segment['text'] for segment in dropped] == ['hallucinated']
            assert dropped[0]['audio_alignment'] == 'unplaced'
            assert stack.epoch.rejected_segments == rejected_before + 1
            await _persist_collected(stack, store, monkeypatch)
        else:
            # Legacy: the plain callbacks pass provider-relative times through.
            stack.provider_callback(
                [_provider_segment(0.0, 10.0, 'phrase a'), _provider_segment(15.0, 20.0, 'phrase b')]
            )

        server1 = await stack.stop_pusher_server()

        # Reconnect: a new pusher socket, ack required again; phrase C is for
        # the rollover conversation and must keep its own position/origin.
        stack._current['id'] = CONV2
        stack.host.state.current_conversation_id = CONV2
        if stack.receiver.capture_timeline is not None:
            stack.host.state.conversations_awaiting_capture_origin.add(CONV2)
        # The continued socket builds a fresh provider connection: a new epoch
        # whose provider time restarts at zero, sharing the same capture
        # timeline. Round 1's teardown cleared the previous socket.
        callbacks2, _modulate2, stack.epoch = stack.receiver._build_stt_callbacks()
        stack.provider = FakeProviderSocket()
        stack.receiver.stt_socket = GatedSTTSocket(stack.provider, gate=None, send_tracker=stack.epoch)
        stack.session._mark_disconnected()
        stack.start_pusher_server()
        await stack.session.connect()
        assert stack.session.pusher_connected
        if v2:
            assert stack.session.audio_timeline_active

        frames_c = []
        for i in range(25):
            frames_c.append(_frame(phrase_c[i * piece : (i + 1) * piece], 0.02, 0.02))
        frames_c.append(_disconnect_frame())
        # A new socket's receive loop: the shared capture timeline and origins
        # continue, but the session-active flag is per receive loop.
        stack.host.state.active = True
        await _run_receiver_frames(stack, frames_c)
        await stack.session._audio_bytes_flush()

        if v2:
            translated_c = stack.epoch.translate([_provider_segment(0.0, 5.0, 'phrase c')])
            stack.receiver._enqueue_translated_segments(translated_c, provider='fake')
            await _persist_collected(stack, store, monkeypatch)

        await stack.stop_pusher_server()

        rows = {}
        if v2:
            for cid in (CONV1, CONV2):
                row = dict(store.rows[('users', UID, 'conversations', cid)])
                files = pusher_env.get(cid, {}).get('audio_files', [])
                row.setdefault('audio_files', [])
                row['audio_files'].extend(files)
                row['private_cloud_sync_enabled'] = True
                rows[cid] = row
        return {
            'stack': stack,
            'rows': rows,
            'store': store,
            'pusher_audio_files': pusher_env,
            'phrase_a': phrase_a,
            'phrase_b': phrase_b,
            'phrase_c': phrase_c,
        }
    finally:
        stack.restore()


async def test_v2_end_to_end_alignment(monkeypatch, gcs, pusher_env, telemetry):
    result = await _run_scenario(monkeypatch, gcs, pusher_env, v2=True)
    row1 = result['rows'][CONV1]
    row2 = result['rows'][CONV2]

    # Origin pinning: started_at is the first accepted frame's projected wall
    # time (arrival minus the frame duration); the marker is pinned with it.
    assert row1['audio_timeline'] == {'version': 2}
    started1 = row1['started_at']
    assert isinstance(started1, datetime)
    assert abs(started1.timestamp() - (T0 - 0.5)) < 0.05, started1
    assert row2['audio_timeline'] == {'version': 2}
    # The hour-long wall-clock step must NOT mint an hour of recorded audio:
    # the rollover origin continues the pre-jump capture axis (+20 s of
    # captured audio), never started1 + 3600.
    assert abs(row2['started_at'].timestamp() - (started1.timestamp() + 20.0)) < 0.05

    # Persisted segment offsets select the phrases. The live merge joins the
    # two same-speaker phrases into one turn spanning [0, 20]; the rollover
    # conversation's segment starts at its own origin.
    segments1 = _decode_segments(row1)
    assert len(segments1) == 1
    assert 'phrase a' in segments1[0]['text'] and 'phrase b' in segments1[0]['text']
    assert abs(segments1[0]['start'] - 0.0) < 0.05
    assert abs(segments1[0]['end'] - 20.0) < 0.05
    segments2 = _decode_segments(row2)
    assert abs(segments2[0]['start'] - 0.0) < 0.05  # rollover origin at phrase C

    # Coverage vocabulary: spans cover the phrases and the delivered silence;
    # a window past the captured audio is missing, never guessed.
    from utils.speaker_tag_prompts.clips import conversation_clip_pcm

    assert coverage_outcome(row1, 0.0, 10.0) == 'covered'
    assert coverage_outcome(row1, 10.0, 15.0) == 'covered'  # delivered silence is captured audio
    assert coverage_outcome(row1, 15.0, 20.0) == 'covered'
    assert coverage_outcome(row1, 20.5, 24.5) == 'missing'
    assert coverage_outcome(row2, 0.0, 5.0) == 'covered'

    # Byte-pattern identity: a clip at the segment offset is exactly that
    # phrase's stored samples, not merely some chunk that exists.
    clip_a = conversation_clip_pcm(UID, row1, 0.2, 1.2)
    assert clip_a == _slice(result['phrase_a'], 0.2, 1.2)
    clip_b = conversation_clip_pcm(UID, row1, 15.2, 16.2)
    assert clip_b == _slice(result['phrase_b'], 0.2, 1.2)
    clip_c = conversation_clip_pcm(UID, row2, 0.5, 1.5)
    assert clip_c == _slice(result['phrase_c'], 0.5, 1.5)
    assert conversation_clip_pcm(UID, row1, 20.2, 21.2) is None

    # The logical wall-clock jump created neither an anchor nor an hour of audio.
    timeline = result['stack'].receiver.capture_timeline
    assert len(timeline.anchors) == 1
    spans1 = row1['audio_files'][0]['chunk_spans']
    assert spans1 and abs(spans1[0]['start'] - (T0 - 0.5)) < 0.05


async def test_legacy_calculation_misplaces_burst_audio(monkeypatch, gcs, pusher_env, telemetry):
    """The same burst under the legacy calculation (flag off) fails the acceptance
    criterion: the chunk timestamp is last arrival minus the whole buffered run
    while the segment sits at first-audio + provider time, so the stored offset
    points far away from the phrase."""

    result = await _run_scenario(monkeypatch, gcs, pusher_env, v2=False)
    # The capture clock runs for every single-channel server-STT session; with
    # the flag off only the v2 persistence/projection is absent, and the wire
    # stays legacy (no capability ack, no projected 101 starts).
    assert result['stack'].receiver.capture_timeline is not None
    assert result['stack'].receiver.capture_timeline_v2 is False
    assert result['stack'].session.config.audio_timeline_v2 is False
    assert not result['stack'].session.audio_timeline_active

    session = result['stack'].session
    last_received = session.audio_buffer_last_received
    buffered_duration = 20.0  # phrase A + silence + phrase B, one run per flush window
    legacy_chunk_start = last_received - buffered_duration
    legacy_first_audio = T0  # arrival of the first burst frame
    assert abs(legacy_chunk_start - legacy_first_audio) > 9.0, (
        'legacy calculation must demonstrably misplace burst audio; if it does '
        'not, this regression no longer encodes the old failure'
    )

    from utils.speaker_tag_prompts.clips import conversation_clip_pcm

    row = {
        'id': CONV1,
        'started_at': datetime.fromtimestamp(legacy_first_audio, tz=timezone.utc),
        'private_cloud_sync_enabled': True,
        'audio_files': result['pusher_audio_files'].get(CONV1, {}).get('audio_files', []),
    }
    assert row['audio_files'], 'the legacy run must still have uploaded chunks to compare against'
    assert coverage_outcome(row, 0.2, 1.2) == 'unsupported', 'a v1-only chunk list is not proof of coverage'
    clip = conversation_clip_pcm(UID, row, 0.2, 1.2)
    assert clip != _slice(result['phrase_a'], 0.2, 1.2)


async def test_capability_loss_withholds_audio_as_coverage_gap(monkeypatch, gcs, pusher_env, telemetry):
    stack = _Stack(monkeypatch, v2=True, conversation_id=CONV1)
    try:
        stack.build_session()
        stack.start_pusher_server()
        await stack.session.connect()
        assert stack.session.audio_timeline_active

        # Capability lost mid-recording: audio is withheld, never downgraded,
        # never terminal; the recording itself keeps going.
        stack.session.audio_timeline_suspended = True
        phrase = _phrase(9, 2.0)
        stack.session.audio_bytes_send(
            phrase, stack.clock['wall'], conversation_id=CONV1, start_wall=stack.clock['wall']
        )
        await stack.session._audio_bytes_flush()
        assert stack.session.audio_total_size > 0, 'withheld audio must stay buffered'
        assert list(stack.server_ws.frames) == [], 'withheld audio must not reach the pusher'

        # A capable pusher returns: the run keeps its original position.
        stack.session.audio_timeline_suspended = False
        await stack.session._audio_bytes_flush()
        assert stack.session.audio_total_size == 0
        frames = list(stack.server_ws.frames)
        headers = [struct.unpack('<I', frame[:4])[0] for frame in frames]
        assert 103 in headers  # conversation announcement precedes the run
        audio_frame = next(frame for frame in frames if struct.unpack('<I', frame[:4])[0] == 101)
        assert abs(struct.unpack('<d', audio_frame[4:12])[0] - stack.clock['wall']) < 0.001
        assert audio_frame[12:] == phrase
    finally:
        stack.restore()
