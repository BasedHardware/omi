"""Hermetic acceptance: live owner recognition survives a mid-session STT failover.

The 2026-09-25 incident shape: the owner's voiceprint is correct, the owner is
matched live early in the socket, then Modulate dies and the session fails over
to Soniox - whose stream timestamps restart at 0. The queued detections' audio
windows must still land inside the 60 s ring buffer, and the owner's later
segments must be ``is_user=true`` in BOTH the WebSocket output to the client and
the persisted conversation.

Runs the real ListenReceiver (decode, capture clock, per-epoch translators, the
actual ``_failover_stt_socket`` rebuild), the real TranscriptProcessor.process_loop,
the real SpeakerMatcher, and the real fenced conversation persistence - against
an in-memory websocket double, fake provider sockets, an in-memory Firestore and
a deterministic fake embedding model (an 8-bin spectral signature of the PCM; no
model download). The owner and another voice are tones with distinct
cycles-per-clip, so the fake embedding separates them exactly like cosine
distance over real voiceprints would.

Parameterized over AUDIO_TIMELINE_V2: the capture clock is internal to the
listen socket, so recognition must survive the failover with the flag OFF
(legacy persistence, byte-identical fields, no marker) and ON (v2 projected
persistence with the marker).

Fail-old demonstration: this same file, run at the merge base of this branch
(the pre-v2 receiver whose matcher windows are first_audio + provider time),
fails - after the failover the window points minutes before the retained audio,
matching returns before a decision, and the owner's later segments stay
``is_user=false`` in both outputs.
"""

import asyncio
import io
import logging
import time
import wave
from collections import deque
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.websockets import WebSocketDisconnect

import routers.listen.receiver as receiver_module
from database import conversations as conversations_db
from routers.listen.contracts import ListenLimits, ListenSessionState
from routers.listen.receiver import ListenReceiver
from routers.listen.speakers import SpeakerMatcher
from routers.listen.transcripts import TranscriptProcessor
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.audio import AudioRingBuffer
from utils.product_telemetry import set_product_telemetry_client_for_tests
from utils.stt.streaming import STTService
from utils.stt.vad_gate import GatedSTTSocket
from utils.transcribe_store import get_user_name as transcribe_get_user_name
from utils.transcribe_store import user_db

RATE = 16000
UID = 'uid-failover'
CONV = 'conv-failover'
T0 = 1_700_000_000.0
SESSION_ID = 'rec-failover-1'

# Timeline (capture seconds from the first accepted frame):
#   0-60   delivered silence (ages the ring buffer past the first minute)
#   60-63  owner speech   -> provider segment 1 (epoch 1, provider time 60-63)
#   63-70  delivered silence, then the provider dies and the session fails over
#   70-73  owner speech   -> provider segment 2 (epoch 2, provider time 0-3!)
#   73-75.5 owner speech  -> provider segment 3 (epoch 2, provider time 3-5.5)
#   75.5-78 delivered silence
# The owner's first clip alone is below the 5 s evidence minimum, so the
# decision can only come from post-failover audio: exactly the incident.
PRE_STREAM_SECONDS = 70.0
POST_STREAM_SECONDS = 8.0

OWNER_FREQUENCY_HZ = 200.0  # fake-embedding bin identifying the owner's voice
OTHER_FREQUENCY_HZ = 700.0  # a second voice would sit here; far from the owner's bin
_FAKE_FREQS = (100.0, 200.0, 350.0, 700.0)


@pytest.fixture
def anyio_backend():
    return 'asyncio'


class _TelemetryClient:
    def __init__(self):
        self.events = []

    def capture(self, **event):
        self.events.append(event)


@pytest.fixture
def telemetry():
    client = _TelemetryClient()
    set_product_telemetry_client_for_tests(client)
    yield client
    set_product_telemetry_client_for_tests(None)


# ---------------------------------------------------------------------------
# Deterministic audio and the fake embedding model.
# ---------------------------------------------------------------------------
def _tone(frequency_hz: float, seconds: float) -> bytes:
    """A fixed-frequency tone: whatever window is clipped from it, its fake
    embedding keeps landing in the same frequency bin."""
    samples = int(seconds * RATE)
    index = np.arange(samples, dtype=np.float64)
    data = (12000 * np.sin(2 * np.pi * frequency_hz * index / RATE)).astype('<i2')
    return data.tobytes()


def _silence(seconds: float) -> bytes:
    return b'\x00\x00' * int(seconds * RATE)


def _owner(seconds: float) -> bytes:
    return _tone(OWNER_FREQUENCY_HZ, seconds)


def _unit_vector(bin_index: int) -> list:
    vector = np.zeros(len(_FAKE_FREQS), dtype=np.float32)
    vector[bin_index] = 1.0
    return vector.tolist()


def _fake_extract_embedding(wav_bytes: bytes, name: str):
    """Deterministic 'model': the normalized magnitude at fixed frequency bins."""
    with wave.open(io.BytesIO(wav_bytes), 'rb') as handle:
        pcm = handle.readframes(handle.getnframes())
    samples = np.frombuffer(pcm, dtype='<i2').astype(np.float64)
    index = np.arange(len(samples))
    mags = np.abs(
        np.asarray([np.dot(samples, np.exp(-2j * np.pi * freq * index / RATE)) for freq in _FAKE_FREQS])
    ).astype(np.float32)
    norm = float(np.linalg.norm(mags))
    vector = mags / norm if norm else mags
    return vector.reshape(1, -1)


# ---------------------------------------------------------------------------
# Doubles for the outermost IO only.
# ---------------------------------------------------------------------------
class FakeListenWebSocket:
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


class FakeProviderSocket:
    """Provider socket double; `send` accepts the capture-position seam if present."""

    def __init__(self):
        self.is_connection_dead = False
        self.typed_death_reason = None
        self.sent_runs = []

    def send(self, data, **kwargs):
        self.sent_runs.append((kwargs.get('start_sample'), len(data) // 2))
        return True

    def finish(self):
        return None


def _frames_for(audio: bytes, *, seconds_per_frame=1.0):
    """One frame per second of audio, arriving in real time (wall+mono advance)."""
    frames = []
    piece = int(seconds_per_frame * RATE) * 2
    for offset in range(0, len(audio), piece):
        frames.append({'bytes': audio[offset : offset + piece], '_advance': (seconds_per_frame, seconds_per_frame)})
    return frames


def _provider_segment(segment_id, start, end, text):
    return {
        'id': segment_id,
        'speaker': 'SPEAKER_00',
        'speaker_id': 0,
        'start': start,
        'end': end,
        'text': text,
        'is_user': False,
        'person_id': None,
    }


# ---------------------------------------------------------------------------
# The hermetic session.
# ---------------------------------------------------------------------------
class FailoverStack:
    def __init__(self, monkeypatch, *, v2: bool):
        self.clock = {'wall': T0, 'mono': 0.0}
        monkeypatch.setenv('AUDIO_TIMELINE_V2', 'true' if v2 else 'false')
        self.v2 = v2
        # The receiver reads arrival observations through the module's time shim.
        self._real_time = receiver_module.time
        receiver_module.time = SimpleNamespace(time=lambda: self.clock['wall'], monotonic=lambda: self.clock['mono'])
        # Both the death monitor and the explicit failover drive this rebuild.
        self.created_sockets = []

        async def fake_create(self_receiver, callback, sample_rate, modulate_callback=None, **kwargs):
            epoch = kwargs.get('epoch')
            inner = FakeProviderSocket()
            try:
                socket = GatedSTTSocket(inner, gate=None, send_tracker=epoch)
            except TypeError:  # merge base: no capture-position seam
                socket = inner
            self.created_sockets.append({'callback': callback, 'socket': socket, 'inner': inner, 'epoch': epoch})
            return socket

        monkeypatch.setattr(ListenReceiver, '_create_stt_socket', fake_create)
        monkeypatch.setattr(receiver_module, 'should_initialize_vad_gate', lambda **kwargs: False)
        monkeypatch.setattr(
            receiver_module, 'get_stt_service_for_language', lambda *a, **k: (STTService.deepgram, 'en', 'nova-2')
        )

        async def serving(raw):
            return True

        monkeypatch.setattr(receiver_module, 'fallback_socket_is_serving', serving)

        import routers.listen.speakers as speakers_module

        monkeypatch.setattr(speakers_module, 'extract_embedding_from_bytes', _fake_extract_embedding)

        self.store = StrictFirestore()
        self.store.rows[('users', UID, 'conversations', CONV)] = {
            'id': CONV,
            'status': 'in_progress',
            'created_at': datetime.fromtimestamp(T0 - 60, tz=timezone.utc),
            'started_at': datetime.fromtimestamp(T0 - 60, tz=timezone.utc),
            'finished_at': datetime.fromtimestamp(T0 - 60, tz=timezone.utc),
            'structured': {},
            'transcript_segments': [],
        }
        monkeypatch.setattr(conversations_db, 'get_firestore_client', lambda: self.store)

        self.state = ListenSessionState()
        self.state.current_conversation_id = CONV
        self.state.speaker_id_enabled = True
        self.state.audio_ring_buffer = AudioRingBuffer(60.0, RATE)
        self.tasks = []

        async def persistence_call(fn, *args, **kwargs):
            if fn is conversations_db.get_conversation:
                raw = dict(self.store.rows.get(('users', UID, 'conversations', args[1])) or {})
                # The canonical read decode: the stored row carries zlib-compressed
                # transcript segments once the first write has landed.
                return conversations_db.prepare_conversation_for_read(raw, UID)
            if fn is conversations_db.update_conversation_finished_at:
                _uid, conversation_id, finished_at = args
                self.store.rows[('users', UID, 'conversations', conversation_id)]['finished_at'] = finished_at
                return True
            if fn in (
                conversations_db.update_conversation_segments,
                conversations_db.update_conversation,
                conversations_db.store_conversation_photos,
            ):
                return fn(*args, **kwargs)
            if fn is user_db.get_people:
                return []
            if fn is user_db.get_user_speaker_embedding:
                return _unit_vector(1)  # the owner's voiceprint sits in the 200 Hz bin
            if fn is transcribe_get_user_name:
                return 'Alice'
            if fn is user_db.get_person_by_name:
                return None
            raise AssertionError(f'unexpected persistence call: {fn}')

        def spawn(coro, *, name):
            task = asyncio.create_task(coro, name=name)
            self.tasks.append(task)
            return task

        async def wait(seconds):
            try:
                await asyncio.wait_for(self.state.shutdown_event.wait(), timeout=seconds)
                return True
            except asyncio.TimeoutError:
                return False

        async def drain(tasks, *, timeout, label):
            if tasks:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)

        self.request = SimpleNamespace(
            websocket=None,
            uid=UID,
            codec='pcm16',
            sample_rate=RATE,
            channels=1,
            source='desktop',
            vad_gate_override=None,
            create_speakers=False,
            speaker_auto_assign_enabled=False,
        )
        self.host = SimpleNamespace(
            request=self.request,
            state=self.state,
            limits=ListenLimits(),
            is_multi_channel=False,
            use_custom_stt=False,
            audio_bytes_send=None,
            session_id='session-failover-1',
            recording_session_id=SESSION_ID,
            translation_language=None,
            has_speech_profile=True,
            client_device_context=SimpleNamespace(platform='desktop'),
            stt_service=STTService.soniox,
            stt_language='en',
            stt_model='velma-2',
            language='en',
            multi_lang_enabled=False,
            client_kind='test',
            onboarding_handler=None,
            transcript_send=None,
            pusher_enabled=True,
            user_has_credits=True,
            spawn=spawn,
            wait=wait,
            drain=drain,
            persistence=SimpleNamespace(call=persistence_call),
            conversations=SimpleNamespace(
                create_new_in_progress_conversation=_async_noop,
            ),
            send_event=lambda event: None,
            emit_speaker_suggestion=lambda *args, **kwargs: None,
            complete_live_transcription=lambda: None,
        )
        self.processor = TranscriptProcessor(self.host)
        self.host.transcripts = self.processor
        self.host.speakers = SpeakerMatcher(self.host)
        self.receiver = ListenReceiver(self.host, [], {})
        awaiting = getattr(self.state, 'conversations_awaiting_capture_origin', None)
        if awaiting is not None:
            awaiting.add(CONV)

    def restore(self):
        receiver_module.time = self._real_time

    async def run_receive(self, frames):
        self.request.websocket = FakeListenWebSocket(frames, self.clock)
        websocket = self.request.websocket
        self.state.active = True
        await self.receiver.receive_data()
        # receive_data's finally block clears the flag; restore it before any
        # await so the processing loop never observes a false session end.
        self.state.active = True
        return websocket

    def provider(self, index):
        return self.created_sockets[index]

    def decode_segments(self):
        row = self.store.rows[('users', UID, 'conversations', CONV)]
        return conversations_db._decode_transcript_segments_strict(
            UID, row.get('transcript_segments', []), bool(row.get('transcript_segments_compressed'))
        )


async def _async_noop(*args, **kwargs):
    return None


async def _wait_for(predicate, timeout=20.0, message='condition', *, stack=None, caplog=None):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        await asyncio.sleep(0.05)
    detail = ''
    if stack is not None:
        detail = (
            f' speaker_to_person={dict(stack.host.speakers.speaker_to_person)}'
            f' evidence={ {k: [(round(s, 1)) for _, s in v] for k, v in stack.host.speakers.speaker_evidence.items()} }'
            f' covered={stack.host.speakers._covered_audio}'
            f' queue_size={stack.host.speakers.queue.qsize()}'
        )
    if caplog is not None:
        relevant = [
            record.message
            for record in caplog.records
            if 'speaker_id' in record.message or 'audio timeline' in record.message
        ]
        detail += f' logs={relevant[-12:]}'
    raise AssertionError(f'timed out waiting for {message}.{detail}')


async def _run_failover_scenario(monkeypatch, caplog, *, v2: bool):
    stack = FailoverStack(monkeypatch, v2=v2)
    loop_task = asyncio.create_task(stack.processor.process_loop())
    matcher_task = asyncio.create_task(stack.host.speakers.load_and_run())
    stack.tasks.extend([loop_task, matcher_task])
    caplog.set_level(logging.INFO, logger='routers.listen.speakers')
    try:
        await stack.host.speakers.refresh_for_conversation(CONV)
        assert await stack.receiver.initialize_stt()
        assert len(stack.created_sockets) == 1

        # ---- Phase 1: one minute of silence ages the ring buffer, then the
        # owner speaks once (provider time 60-63) and the provider dies.
        pre_audio = _silence(60.0) + _owner(3.0) + _silence(7.0)
        websocket1 = await stack.run_receive(_frames_for(pre_audio))
        stack.provider(0)['callback']([_provider_segment('seg-pre', 60.0, 63.0, 'owner line before the failover')])
        # The owner's first clip accumulates evidence but cannot decide alone.
        await _wait_for(
            lambda: stack.host.speakers.speaker_evidence.get(0),
            message='pre-failover evidence clip',
        )
        await asyncio.sleep(0.3)
        assert 0 not in stack.host.speakers.speaker_to_person, 'one 3 s clip is below the 5 s evidence minimum'
        stack.provider(0)['inner'].is_connection_dead = True

        # ---- The real failover path: a new provider epoch whose stream time
        # restarts at zero.
        assert await stack.receiver._failover_stt_socket()
        assert len(stack.created_sockets) >= 2
        failover_index = len(stack.created_sockets) - 1
        if getattr(stack.receiver, 'capture_timeline', None) is not None:
            assert stack.provider(failover_index)['epoch'] is not stack.provider(0)['epoch']

        # ---- Phase 2: the owner keeps speaking; the new stream's timestamps
        # restart at 0 exactly like the incident. (The replacement provider
        # also opens a new diarization scope, so the owner is now a fresh,
        # unmapped speaker - precisely the incident's "Speaker 1".)
        post_audio = _owner(3.0) + _owner(2.5) + _silence(4.5)
        websocket2 = await stack.run_receive(_frames_for(post_audio))
        stack.provider(failover_index)['callback'](
            [
                _provider_segment('seg-post-1', 0.0, 3.0, 'owner line right after the failover'),
                _provider_segment('seg-post-2', 3.0, 5.5, 'owner line while recognition should recover'),
            ]
        )
        stack.provider(failover_index)['callback'](
            [_provider_segment('seg-post-3', 5.5, 8.0, 'owner line accumulating evidence')]
        )

        # The post-failover clips complete the evidence and decide: owner. On
        # the legacy clock (the merge-base demonstration) no decision ever
        # comes - the is_user assertions below then prove the loss - so the
        # wait is bounded and tolerates absence.
        def _owner_mapped():
            for speaker_id, (person_id, _name) in stack.host.speakers.speaker_to_person.items():
                if person_id == 'user':
                    return speaker_id
            return None

        try:
            await _wait_for(_owner_mapped, timeout=15.0, stack=stack, caplog=caplog)
        except AssertionError:
            pass

        # The mapped speaker's next delivery carries is_user to the client.
        websocket3 = await stack.run_receive(_frames_for(_silence(2.0)))
        stack.provider(failover_index)['callback'](
            [_provider_segment('seg-post-4', 8.0, 10.0, 'owner line delivered as the user')]
        )
        return stack, (websocket1, websocket2, websocket3)
    finally:
        stack.state.active = False
        stack.state.shutdown_event.set()
        await asyncio.wait_for(loop_task, timeout=30)
        for task in stack.tasks:
            task.cancel()
        await asyncio.gather(*stack.tasks, return_exceptions=True)
        stack.restore()


def _items_containing(items, needle):
    return [item for item in items if needle in (item.get('text') or '')]


def _delivered_items(batches, needle):
    return [item for batch in batches if isinstance(batch, list) for item in _items_containing(batch, needle)]


@pytest.mark.anyio
@pytest.mark.parametrize('v2', [False, True])
async def test_owner_recognition_survives_provider_failover(monkeypatch, caplog, telemetry, v2):
    stack, websockets = await _run_failover_scenario(monkeypatch, caplog, v2=v2)
    # Snapshot after the scenario's teardown drained the processing loop, so
    # the final delivery is included.
    batches = [payload for websocket in websockets for payload in websocket.sent_json if isinstance(payload, list)]

    # BOTH outputs: the WebSocket batch delivered to the client... (the live
    # merge may absorb the contiguous owner turns into one segment, so the
    # assertions are on the delivered text, not on provider segment ids).
    delivered = _delivered_items(batches, 'delivered as the user')
    assert delivered, 'the post-recognition owner segment must be delivered'
    assert all(item['is_user'] for item in delivered), (
        'the owner must be is_user in the WebSocket output after the failover; '
        'on the legacy clock this stays false because the queued detections '
        'never located the owner audio'
    )

    # ...and the persisted conversation (the final speaker flush applies the
    # mapping to every segment of the diarized speaker).
    persisted = stack.decode_segments()
    after_failover = _items_containing(persisted, 'after the failover')
    assert after_failover and all(segment['is_user'] for segment in after_failover), persisted
    assert all(item['is_user'] for item in _items_containing(persisted, 'delivered as the user')), persisted

    # Persistence stays exactly as the flag admits it: no v2 marker with the
    # flag off, marker with it on.
    row = stack.store.rows[('users', UID, 'conversations', CONV)]
    if v2:
        assert row.get('audio_timeline') == {'version': 2}
    else:
        assert 'audio_timeline' not in row

    # The matcher logs are attributable by recording session.
    decisions = [record.message for record in caplog.records if 'speaker_id_decision' in record.message]
    assert decisions and all(f'session={SESSION_ID}' in line for line in decisions), decisions
