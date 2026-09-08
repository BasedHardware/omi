"""Behavioral coverage for parity capture through the real listen runtime seam."""

import json
import logging
from collections import Counter
from functools import wraps
from typing import Any, cast

import pytest
from starlette.websockets import WebSocketState

from routers.listen.contracts import ListenRequest
from routers.listen.parity_capture import ListenParityCapture
from routers.listen.receiver import ListenReceiver
from routers.listen.runtime import ListenSessionRuntime
from utils.executors import storage_executor
from utils.listen_session_bootstrap import ListenConnectBase
from utils.stt.streaming import STTService

_PRINCIPAL = 'allowed-runtime-principal'
_TRANSCRIPT = 'synthetic runtime transcript'
_GCS_URI = 'gs://runtime-capture-bucket/parity-pack/v0'
_CREDENTIAL = 'synthetic-private-credential'
_AUDIO = (b'privacy-sensitive-audio' * 42)[:960]


class _FakeWebSocket:
    def __init__(self, audio: bytes):
        self.headers = {}
        self.client_state = WebSocketState.CONNECTED
        self._messages = [
            {'type': 'websocket.receive', 'bytes': audio},
            {'type': 'websocket.disconnect', 'code': 1000},
        ]
        self.sent = []

    async def receive(self):
        if not self._messages:
            raise RuntimeError('unexpected extra WebSocket receive after scripted disconnect')
        message = self._messages.pop(0)
        if message['type'] == 'websocket.disconnect':
            self.client_state = WebSocketState.DISCONNECTED
        return message

    async def send_json(self, payload):
        self.sent.append(payload)

    async def send_text(self, payload):
        self.sent.append(payload)

    async def close(self, code=1000, reason=None):
        self.client_state = WebSocketState.DISCONNECTED


class _FakeSTTSocket:
    def __init__(self, callback):
        self.callback = callback
        self.sent = []
        self.finished = False

    @property
    def is_connection_dead(self):
        return False

    def send(self, audio):
        self.sent.append(audio)
        self.callback([{'text': _TRANSCRIPT, 'start': 0.0, 'end': 0.03}])
        return True

    def finish(self):
        self.finished = True

    async def drain_and_close(self):
        self.finish()


class _FakeTranscripts:
    def __init__(self, runtime):
        self.runtime = runtime
        self.inbound = []

    def enqueue(self, segments):
        self.inbound.extend(segments)
        self.runtime.state.words_transcribed_since_last_record += 1

    async def process_loop(self):
        await self.runtime.state.shutdown_event.wait()

    async def flush_translations(self):
        return None

    def clear(self):
        return None


class _FakeConversations:
    def __init__(self, runtime):
        self.runtime = runtime

    async def send_last_conversation(self):
        return None

    async def prepare(self):
        return []

    async def lifecycle_loop(self):
        await self.runtime.state.shutdown_event.wait()

    async def process_pending(self, _timed_out):
        return None


class _FakeSpeakers:
    async def load_and_run(self):
        return None

    def clear(self):
        return None


class _FakePersistence:
    def __init__(self, *, fail_usage):
        self.fail_usage = fail_usage
        self.calls = []

    async def call(self, function, *args, **kwargs):
        self.calls.append(function.__name__)
        if function.__name__ == 'record_usage' and self.fail_usage:
            raise RuntimeError('synthetic teardown persistence failure')
        return False


def _install_runtime_fakes(monkeypatch, runtime, stt_sockets, blocking_calls):
    import routers.listen.receiver as receiver_module
    import routers.listen.runtime as runtime_module

    async def load_base(*_args, **_kwargs):
        return ListenConnectBase(
            user_exists=True,
            user_has_credits=True,
            transcription_prefs={'single_language_mode': False, 'uses_custom_stt': False},
            fair_use_init_stage=None,
            fair_use_track_dg_usage=False,
            fair_use_dg_budget_exhausted=False,
        )

    async def create_stt_socket(_receiver, callback, _sample_rate, modulate_callback=None):
        socket = _FakeSTTSocket(callback)
        stt_sockets.append(socket)
        return socket

    def build_components():
        runtime.receiver = ListenReceiver(runtime, [], {})
        runtime.transcripts = _FakeTranscripts(runtime)
        runtime.conversations = _FakeConversations(runtime)
        runtime.speakers = _FakeSpeakers()

    async def run_blocking_fake(executor, function, *args, **kwargs):
        blocking_calls.append((executor, function))
        if getattr(function, '__self__', None) is runtime.parity_capture and function.__name__ == 'persist':
            return function(*args, **kwargs)
        return False

    monkeypatch.setattr(runtime_module, 'run_blocking', run_blocking_fake)
    monkeypatch.setattr(runtime_module, 'load_listen_connect_base', load_base)
    monkeypatch.setattr(
        runtime_module,
        'get_stt_service_for_language',
        lambda *_args, **_kwargs: (STTService.parakeet, 'en', 'parakeet_streaming'),
    )
    monkeypatch.setattr(runtime_module, 'FAIR_USE_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'PUSHER_ENABLED', False)
    monkeypatch.setattr(runtime_module, 'should_load_speech_profile', lambda **_kwargs: False)
    monkeypatch.setattr(runtime_module, 'should_enable_speaker_identification', lambda **_kwargs: False)
    monkeypatch.setattr(receiver_module, 'should_initialize_vad_gate', lambda **_kwargs: False)
    monkeypatch.setattr(ListenReceiver, '_create_stt_socket', create_stt_socket)
    monkeypatch.setattr(runtime, '_build_components', build_components)


@pytest.mark.asyncio
@pytest.mark.parametrize('fail_usage', [False, True], ids=['normal-close', 'teardown-persistence-failure'])
async def test_listen_runtime_persists_and_exports_capture_exactly_once_after_close(
    tmp_path, monkeypatch, caplog, fail_usage
):
    """Bootstrap, real receiver callback attachment, audio, close, persist, export."""
    import routers.listen.parity_pack_export as export_module

    root = tmp_path / 'absolute-capture-root'
    monkeypatch.setenv('OMI_ENV_STAGE', 'dev')
    monkeypatch.setenv('OMI_PARITY_PACK_CAPTURE', '1')
    monkeypatch.setenv('OMI_PARITY_PACK_ALLOWED_PRINCIPALS', _PRINCIPAL)
    monkeypatch.setenv('OMI_PARITY_PACK_ROOT', str(root))
    monkeypatch.setenv('OMI_PARITY_PACK_GCS_URI', _GCS_URI)
    monkeypatch.setenv('SERVICE_ACCOUNT_JSON', _CREDENTIAL)

    uploaded = []
    reconcile_calls = []
    persist_calls = []
    original_persist = ListenParityCapture.persist

    @wraps(original_persist)
    def persist_once(capture):
        persist_calls.append(capture)
        return original_persist(capture)

    class FakeBlob:
        def __init__(self, bucket, object_name):
            self.bucket = bucket
            self.object_name = object_name

        def upload_from_filename(self, filename, content_type=None):
            uploaded.append((self.bucket, self.object_name, filename, content_type))

    class FakeBucket:
        def __init__(self, name):
            self.name = name

        def blob(self, object_name):
            return FakeBlob(self.name, object_name)

    class FakeClient:
        def bucket(self, name):
            return FakeBucket(name)

    monkeypatch.setattr(ListenParityCapture, 'persist', persist_once)
    monkeypatch.setattr(export_module, 'ensure_reconcile_loop', lambda *, environ=None: reconcile_calls.append(environ))
    monkeypatch.setattr(export_module, '_storage_client', lambda: FakeClient())

    websocket = _FakeWebSocket(audio=_AUDIO)
    runtime = ListenSessionRuntime(ListenRequest(websocket=websocket, uid=_PRINCIPAL, codec='pcm16', sample_rate=16000))
    runtime.persistence = cast(Any, _FakePersistence(fail_usage=fail_usage))
    stt_sockets = []
    blocking_calls = []
    _install_runtime_fakes(monkeypatch, runtime, stt_sockets, blocking_calls)
    caplog.set_level(logging.INFO)

    if fail_usage:
        with pytest.raises(RuntimeError, match='synthetic teardown persistence failure'):
            await runtime.run()
    else:
        await runtime.run()

    assert runtime.parity_capture.enabled is True
    assert len(stt_sockets) == 1
    assert stt_sockets[0].sent == [_AUDIO]
    assert len(runtime.transcripts.inbound) == 1
    inbound = runtime.transcripts.inbound[0]
    assert inbound['text'] == _TRANSCRIPT
    assert inbound['start'] == 0.0
    assert inbound['end'] == 0.03
    assert inbound['stt_provider'] == 'parakeet'
    assert inbound['speaker_id_scope'].endswith(':0')
    assert len(persist_calls) == 1
    persist_offloads = [
        (executor, function)
        for executor, function in blocking_calls
        if executor is storage_executor
        and getattr(function, '__self__', None) is runtime.parity_capture
        and function.__name__ == 'persist'
    ]
    assert len(persist_offloads) == 1

    cassette_files = list((root / 'cassettes').glob('*.json'))
    assert len(cassette_files) == 1
    cassette = json.loads(cassette_files[0].read_text(encoding='utf-8'))
    assert Counter(event['direction'] for event in cassette['events']) == Counter(
        {'client': 1, 'inbound': 1, 'outbound': 1}
    )
    assert uploaded == [
        (
            'runtime-capture-bucket',
            f'parity-pack/v0/cassettes/{cassette_files[0].name}',
            str(cassette_files[0]),
            'application/json',
        )
    ]
    assert reconcile_calls == [None]

    lifecycle_messages = Counter(
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith('listen_parity_capture_lifecycle ')
    )
    assert lifecycle_messages == Counter(
        {
            'listen_parity_capture_lifecycle boundary=enabled result=enabled error_type=none': 1,
            'listen_parity_capture_lifecycle boundary=admitted result=allowed error_type=none': 1,
            'listen_parity_capture_lifecycle boundary=bootstrap result=succeeded error_type=none': 1,
            'listen_parity_capture_lifecycle boundary=observe result=succeeded error_type=none': 3,
            'listen_parity_capture_lifecycle boundary=persist result=attempted error_type=none': 1,
            'listen_parity_capture_lifecycle boundary=persist result=succeeded error_type=none': 1,
            'listen_parity_capture_lifecycle boundary=export result=attempted error_type=none': 1,
            'listen_parity_capture_lifecycle boundary=export result=succeeded error_type=none': 1,
        }
    )

    for sensitive in (
        _PRINCIPAL,
        runtime.session_id,
        _TRANSCRIPT,
        _AUDIO.decode('ascii'),
        _CREDENTIAL,
        str(root),
        _GCS_URI,
        cassette_files[0].name,
    ):
        assert sensitive not in caplog.text
