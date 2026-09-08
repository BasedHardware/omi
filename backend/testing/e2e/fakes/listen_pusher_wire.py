"""Loopback peers for the hermetic listen-to-pusher wire-contract tests.

The peers intentionally understand only the transport boundary.  The backend
still owns listen routing, provider selection, pusher framing, and retry
decisions; these helpers merely script the two network services it talks to.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
import struct
import threading
import time
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Optional

import websockets

# The production pusher module currently exposes no named wire constants.  Keep
# the unavoidable protocol literals at this single peer boundary rather than
# copying them through individual tests.  When production exports constants,
# this is the one place to replace them.
PUSHER_TRANSCRIPT = 102
PUSHER_PROCESS_CONVERSATION = 104
PUSHER_PROCESS_RESULT = 201


@dataclass(frozen=True)
class PusherFrame:
    """A production pusher binary frame observed by the loopback peer."""

    connection: int
    header_type: int
    payload: Any
    raw: bytes


def _encode_pusher_result(payload: dict[str, Any]) -> bytes:
    return struct.pack('<I', PUSHER_PROCESS_RESULT) + json.dumps(payload, separators=(',', ':')).encode('utf-8')


def _peer_path(websocket: Any, path: Optional[str]) -> str:
    """Read a WebSocket request path across supported websockets server APIs."""

    if path is not None:
        return path
    request = getattr(websocket, 'request', None)
    return str(getattr(websocket, 'path', None) or getattr(request, 'path', '') or '')


class _LoopbackWebSocketServer:
    """Run an asyncio WebSocket server on a dedicated deterministic test thread."""

    def __init__(self) -> None:
        self._ready = threading.Event()
        self._stopped = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_stop: Optional[asyncio.Event] = None
        self._port: Optional[int] = None
        self._startup_error: Optional[BaseException] = None

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError('loopback peer has not started')
        return self._port

    def start(self) -> '_LoopbackWebSocketServer':
        if self._thread is not None:
            return self
        self._thread = threading.Thread(target=self._thread_main, name=type(self).__name__, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=3.0):
            raise TimeoutError(f'{type(self).__name__} did not bind its loopback port')
        if self._startup_error is not None:
            raise RuntimeError(f'{type(self).__name__} failed to start') from self._startup_error
        return self

    def close(self) -> None:
        if self._thread is None:
            return
        if self._loop is not None and self._async_stop is not None:
            self._loop.call_soon_threadsafe(self._async_stop.set)
        if not self._stopped.wait(timeout=3.0):
            raise TimeoutError(f'{type(self).__name__} did not stop')

    def _thread_main(self) -> None:
        asyncio.run(self._serve())

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._async_stop = asyncio.Event()
        try:
            server = await websockets.serve(self._handle, '127.0.0.1', 0, ping_interval=None)
            sockets = server.sockets or []
            if not sockets:
                raise RuntimeError('loopback server did not expose a socket')
            self._port = int(sockets[0].getsockname()[1])
        except BaseException as error:
            self._startup_error = error
            self._ready.set()
            self._stopped.set()
            return
        self._ready.set()
        try:
            await self._async_stop.wait()
        finally:
            server.close()
            await server.wait_closed()
            self._stopped.set()

    async def _handle(self, websocket: Any, path: Optional[str] = None) -> None:
        raise NotImplementedError


class ScriptedParakeetPeer(_LoopbackWebSocketServer):
    """Minimal /v3/stream peer that emits one deterministic segment per audio send."""

    def __init__(
        self,
        *,
        segment_text: str = 'Parakeet wire-contract transcript.',
        close_after_audio: Optional[int] = None,
    ) -> None:
        super().__init__()
        self.segment_text = segment_text
        self.close_after_audio = close_after_audio
        self._condition = threading.Condition()
        self.paths: list[str] = []
        self.audio_chunks: list[bytes] = []
        self.forced_close_count = 0
        self.connection_count = 0

    @property
    def api_url(self) -> str:
        return f'http://127.0.0.1:{self.port}'

    def wait_for_audio(self, count: int, *, timeout: float = 3.0) -> list[bytes]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while len(self.audio_chunks) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f'expected {count} Parakeet audio chunk(s), saw {len(self.audio_chunks)}')
                self._condition.wait(remaining)
            return list(self.audio_chunks)

    def wait_for_forced_close(self, *, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self.forced_close_count < 1:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Parakeet peer did not close after the scripted audio frame')
                self._condition.wait(remaining)

    async def _handle(self, websocket: Any, path: Optional[str] = None) -> None:
        with self._condition:
            self.connection_count += 1
            self.paths.append(_peer_path(websocket, path))
            self._condition.notify_all()
        # The production Parakeet service confirms stream admission by sending a
        # readiness frame before accepting audio. Mirror that contract so the
        # real ParakeetWebSocketSocket completes its startup handshake.
        await websocket.send(json.dumps({'type': 'ready'}))
        segment_index = 0
        async for message in websocket:
            if isinstance(message, bytes):
                with self._condition:
                    self.audio_chunks.append(message)
                    self._condition.notify_all()
                if self.close_after_audio is not None and len(self.audio_chunks) >= self.close_after_audio:
                    await websocket.close(code=1011, reason='scripted Parakeet send failure')
                    with self._condition:
                        self.forced_close_count += 1
                        self._condition.notify_all()
                    break
                segment_index += 1
                await websocket.send(
                    json.dumps(
                        {
                            'id': f'parakeet-wire-{segment_index}',
                            'text': self.segment_text,
                            'speaker': 'SPEAKER_00',
                            'speaker_id': 0,
                            'is_user': True,
                            'person_id': None,
                            'start': float(segment_index - 1) * 0.25,
                            'end': float(segment_index) * 0.25,
                            'stt_provider': 'parakeet-wire-peer',
                        },
                        separators=(',', ':'),
                    )
                )


class RejectingParakeetPeer(_LoopbackWebSocketServer):
    """A deterministic loopback provider that rejects the WebSocket handshake."""

    @property
    def api_url(self) -> str:
        return f'http://127.0.0.1:{self.port}'

    async def _serve(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._async_stop = asyncio.Event()

        async def reject(_path: str, _headers: Any):
            return HTTPStatus.SERVICE_UNAVAILABLE, [], b'Parakeet test peer unavailable'

        try:
            server = await websockets.serve(
                self._handle,
                '127.0.0.1',
                0,
                ping_interval=None,
                process_request=reject,
            )
            sockets = server.sockets or []
            if not sockets:
                raise RuntimeError('loopback server did not expose a socket')
            self._port = int(sockets[0].getsockname()[1])
        except BaseException as error:
            self._startup_error = error
            self._ready.set()
            self._stopped.set()
            return
        self._ready.set()
        try:
            await self._async_stop.wait()
        finally:
            server.close()
            await server.wait_closed()
            self._stopped.set()

    async def _handle(self, websocket: Any, path: Optional[str] = None) -> None:
        raise AssertionError('rejected Parakeet peer must never complete a WebSocket session')


class ScriptedModulatePeer(_LoopbackWebSocketServer):
    """Minimal Velma-2 peer that returns one final utterance per audio frame.

    The production client sends raw PCM binary frames and signals teardown with
    an empty text frame.  The peer deliberately implements only that wire
    contract, retaining the real client URL construction and socket lifecycle.
    """

    def __init__(self, *, segment_text: str = 'Modulate wire-contract transcript.') -> None:
        super().__init__()
        self.segment_text = segment_text
        self._condition = threading.Condition()
        self.paths: list[str] = []
        self.audio_chunks: list[bytes] = []
        self.connection_count = 0

    @property
    def api_url(self) -> str:
        return f'ws://127.0.0.1:{self.port}'

    def wait_for_audio(self, count: int, *, timeout: float = 3.0) -> list[bytes]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while len(self.audio_chunks) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f'expected {count} Modulate audio chunk(s), saw {len(self.audio_chunks)}')
                self._condition.wait(remaining)
            return list(self.audio_chunks)

    async def _handle(self, websocket: Any, path: Optional[str] = None) -> None:
        with self._condition:
            self.connection_count += 1
            self.paths.append(_peer_path(websocket, path))
            self._condition.notify_all()
        async for message in websocket:
            if isinstance(message, bytes):
                with self._condition:
                    self.audio_chunks.append(message)
                    self._condition.notify_all()
                await websocket.send(
                    json.dumps(
                        {
                            'type': 'utterance',
                            'utterance': {
                                'text': self.segment_text,
                                'start_ms': 0,
                                'duration_ms': 250,
                                'speaker': 1,
                            },
                        },
                        separators=(',', ':'),
                    )
                )
            elif message == '':
                await websocket.send(json.dumps({'type': 'done', 'duration_ms': 250}, separators=(',', ':')))


class ScriptedPusherPeer(_LoopbackWebSocketServer):
    """Script pusher replies while recording the production binary wire contract."""

    def __init__(self, on_finalization: Callable[['ScriptedPusherPeer', PusherFrame, Any], Any]) -> None:
        super().__init__()
        self._condition = threading.Condition()
        self._on_finalization = on_finalization
        self.paths: list[str] = []
        self.frames: list[PusherFrame] = []
        self.completed_finalization_actions = 0
        self.connection_count = 0

    @property
    def api_url(self) -> str:
        return f'http://127.0.0.1:{self.port}'

    def frames_of_type(self, header_type: int) -> list[PusherFrame]:
        with self._condition:
            return [frame for frame in self.frames if frame.header_type == header_type]

    def wait_for_frames(self, header_type: int, count: int, *, timeout: float = 3.0) -> list[PusherFrame]:
        deadline = time.monotonic() + timeout
        with self._condition:
            while len([frame for frame in self.frames if frame.header_type == header_type]) < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    actual = len([frame for frame in self.frames if frame.header_type == header_type])
                    raise TimeoutError(f'expected {count} pusher frame(s) type={header_type}, saw {actual}')
                self._condition.wait(remaining)
            return [frame for frame in self.frames if frame.header_type == header_type]

    def wait_for_connections(self, count: int, *, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self.connection_count < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f'expected {count} pusher connection(s), saw {self.connection_count}')
                self._condition.wait(remaining)

    def wait_for_finalization_actions(self, count: int, *, timeout: float = 3.0) -> None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while self.completed_finalization_actions < count:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(
                        f'expected {count} pusher finalization action(s), saw {self.completed_finalization_actions}'
                    )
                self._condition.wait(remaining)

    async def send_result(self, websocket: Any, payload: dict[str, Any]) -> None:
        await websocket.send(_encode_pusher_result(payload))

    async def _handle(self, websocket: Any, path: Optional[str] = None) -> None:
        with self._condition:
            self.connection_count += 1
            connection = self.connection_count
            self.paths.append(_peer_path(websocket, path))
            self._condition.notify_all()
        async for raw in websocket:
            if not isinstance(raw, bytes) or len(raw) < 4:
                continue
            header_type = struct.unpack('<I', raw[:4])[0]
            payload: Any
            if header_type in (PUSHER_TRANSCRIPT, PUSHER_PROCESS_CONVERSATION):
                payload = json.loads(raw[4:].decode('utf-8'))
            else:
                payload = raw[4:]
            frame = PusherFrame(connection=connection, header_type=header_type, payload=payload, raw=raw)
            with self._condition:
                self.frames.append(frame)
                self._condition.notify_all()
            if header_type == PUSHER_PROCESS_CONVERSATION:
                try:
                    action = self._on_finalization(self, frame, websocket)
                    if asyncio.iscoroutine(action):
                        await action
                finally:
                    with self._condition:
                        self.completed_finalization_actions += 1
                        self._condition.notify_all()


class _TransactionSnapshot:
    """Immutable document view captured by the strict transaction adapter."""

    def __init__(self, reference: '_TransactionalDocument', payload: dict[str, Any] | None) -> None:
        self.reference = reference
        self._payload = deepcopy(payload)

    @property
    def id(self) -> str:
        return self.reference.id

    @property
    def exists(self) -> bool:
        return self._payload is not None

    def to_dict(self) -> dict[str, Any] | None:
        return deepcopy(self._payload)


class _StrictTransaction:
    """Stage writes and reject the Firestore-invalid read-after-write sequence."""

    def __init__(self, database: '_TransactionalFirestore') -> None:
        self._database = database
        self._writes: list[tuple[str, Any, dict[str, Any], dict[str, Any]]] = []
        self._has_written = False
        self._committed = False

    def _raw_reference(self, reference: Any) -> Any:
        raw = getattr(reference, '_raw', reference)
        if getattr(raw, '_data', None) is not self._database._store._data:
            raise ValueError('Firestore transaction and document reference must belong to the same store')
        return raw

    def _assert_read_allowed(self) -> None:
        if self._has_written:
            raise RuntimeError('Firestore transactions must complete all reads before the first write')

    def read(self, reference: '_TransactionalDocument', *args: Any, **kwargs: Any) -> _TransactionSnapshot:
        self._assert_read_allowed()
        raw = self._raw_reference(reference)
        snapshot = raw.get(*args, **kwargs)
        return _TransactionSnapshot(reference, snapshot.to_dict() if getattr(snapshot, 'exists', False) else None)

    def set(self, reference: Any, payload: dict[str, Any], **kwargs: Any) -> None:
        self._writes.append(('set', self._raw_reference(reference), deepcopy(payload), dict(kwargs)))
        self._has_written = True

    def create(self, reference: Any, payload: dict[str, Any]) -> None:
        self._writes.append(('create', self._raw_reference(reference), deepcopy(payload), {}))
        self._has_written = True

    def update(self, reference: Any, payload: dict[str, Any], **kwargs: Any) -> None:
        self._writes.append(('update', self._raw_reference(reference), deepcopy(payload), dict(kwargs)))
        self._has_written = True

    def delete(self, reference: Any, **kwargs: Any) -> None:
        self._writes.append(('delete', self._raw_reference(reference), {}, dict(kwargs)))
        self._has_written = True

    def commit(self) -> None:
        if self._committed:
            raise RuntimeError('strict Firestore transaction committed twice')
        store = self._database._store
        before_data = deepcopy(store._data)
        before_written_docs = set(store._written_docs)
        try:
            for operation, reference, payload, kwargs in self._writes:
                if operation == 'set':
                    reference.set(payload, **kwargs)
                elif operation == 'create':
                    reference.create(payload, **kwargs)
                elif operation == 'update':
                    reference.update(payload, **kwargs)
                else:
                    reference.delete(**kwargs)
        except Exception:
            store._data.clear()
            store._data.update(before_data)
            store._written_docs.clear()
            store._written_docs.update(before_written_docs)
            raise
        self._committed = True


class _TransactionalDocument:
    """Keep normal mock-Firestore reads while making transactional reads strict."""

    def __init__(self, raw: Any, database: '_TransactionalFirestore') -> None:
        self._raw = raw
        self._database = database

    @property
    def id(self) -> str:
        return self._raw.id

    @property
    def path(self) -> Any:
        return self._raw.path

    def get(self, *args: Any, transaction: Any = None, **kwargs: Any) -> Any:
        if transaction is None:
            return self._raw.get(*args, **kwargs)
        if not isinstance(transaction, _StrictTransaction):
            raise TypeError('strict transactional document requires its own transaction')
        return transaction.read(self, *args, **kwargs)

    def collection(self, name: str) -> Any:
        return _TransactionalCollection(self._raw.collection(name), self._database)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._raw, name)


class _TransactionalFirestore:
    """Serialize staged writes over the E2E fake's document-storage shape."""

    def __init__(self, store: Any) -> None:
        self._store = store
        self._lock = threading.RLock()

    def transaction(self) -> _StrictTransaction:
        return _StrictTransaction(self)

    def collection(self, name: str) -> Any:
        return _TransactionalCollection(self._store.collection(name), self)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


class _TransactionalCollection:
    """Preserve the E2E fake's queries while enforcing transactional read ordering."""

    def __init__(self, raw: Any, database: _TransactionalFirestore) -> None:
        self._raw = raw
        self._database = database

    def document(self, name: Optional[str] = None) -> _TransactionalDocument:
        return _TransactionalDocument(self._raw.document(name), self._database)

    def stream(self, *args: Any, transaction: Any = None, **kwargs: Any) -> Any:
        if transaction is not None:
            if not isinstance(transaction, _StrictTransaction):
                raise TypeError('strict transactional collection requires its own transaction')
            transaction._assert_read_allowed()
        return self._raw.stream(*args, transaction=transaction, **kwargs)

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._raw, name)
        if not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            result = attribute(*args, **kwargs)
            return _TransactionalQuery(result, self._database) if hasattr(result, 'stream') else result

        return invoke


class _TransactionalQuery:
    """Proxy query chains so a transaction cannot read after staging a write."""

    def __init__(self, raw: Any, database: _TransactionalFirestore) -> None:
        self._raw = raw
        self._database = database

    def stream(self, *args: Any, transaction: Any = None, **kwargs: Any) -> Any:
        if transaction is not None:
            if not isinstance(transaction, _StrictTransaction):
                raise TypeError('strict transactional query requires its own transaction')
            transaction._assert_read_allowed()
        return self._raw.stream(*args, transaction=transaction, **kwargs)

    def __getattr__(self, name: str) -> Any:
        attribute = getattr(self._raw, name)
        if not callable(attribute):
            return attribute

        def invoke(*args: Any, **kwargs: Any) -> Any:
            result = attribute(*args, **kwargs)
            return _TransactionalQuery(result, self._database) if hasattr(result, 'stream') else result

        return invoke


def _strict_transactional(function: Callable[..., Any]) -> Callable[..., Any]:
    """Run a real reducer against staged, atomic, read-before-write test storage."""

    def execute(transaction: _StrictTransaction, *args: Any, **kwargs: Any) -> Any:
        if not isinstance(transaction, _StrictTransaction):
            raise TypeError('strict transactional wrapper requires _StrictTransaction')
        with transaction._database._lock:
            result = function(transaction, *args, **kwargs)
            transaction.commit()
            return result

    return execute


class _FirestoreTransactionFacade:
    """Scope the strict decorator to listen's durable reducers only."""

    def __init__(self, firestore_module: Any) -> None:
        self._firestore_module = firestore_module

    def transactional(self, function: Callable[..., Any]) -> Callable[..., Any]:
        return _strict_transactional(function)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._firestore_module, name)


def install_fake_firestore_transactions(monkeypatch: Any, store: Any) -> _TransactionalFirestore:
    """Adapt the existing fake Firestore to the production transaction boundary.

    The adapter preserves the E2E fake's storage/query shape, but gives the
    live recording-session and finalization reducers a serializable staged
    commit and Firestore's read-before-write rule.  It intentionally does not
    invent contention/retry behavior; the emulator lifecycle suite owns that
    cross-worker storage proof.
    """

    from database import conversation_finalization_jobs, recording_sessions

    transactional_store = _TransactionalFirestore(store)

    monkeypatch.setattr(conversation_finalization_jobs, 'get_firestore_client', lambda: transactional_store)
    monkeypatch.setattr(recording_sessions, 'get_firestore_client', lambda: transactional_store)
    monkeypatch.setattr(
        conversation_finalization_jobs,
        'firestore',
        _FirestoreTransactionFacade(conversation_finalization_jobs.firestore),
    )
    monkeypatch.setattr(recording_sessions, 'firestore', _FirestoreTransactionFacade(recording_sessions.firestore))
    return transactional_store


class DeterministicListenTiming:
    """Release a real lifecycle tick and zero only pusher reconnect backoff."""

    def __init__(self) -> None:
        self._lifecycle_tick = threading.Event()
        self._closed = threading.Event()

    def trigger_lifecycle_tick(self) -> None:
        self._lifecycle_tick.set()

    def close(self) -> None:
        self._closed.set()
        self._lifecycle_tick.set()


def install_deterministic_listen_timing(monkeypatch: Any) -> DeterministicListenTiming:
    """Remove wall-clock lifecycle/reconnect waits while retaining their real code paths."""

    import routers.listen.runtime as listen_runtime
    import utils.listen_pusher_session as pusher_session

    timing = DeterministicListenTiming()
    production_wait_for_event = listen_runtime.wait_for_event
    production_runtime_wait = listen_runtime.ListenSessionRuntime.wait

    async def zero_backoff_wait(event: asyncio.Event, seconds: float) -> bool:
        if seconds == 0:
            return event.is_set()
        return await production_wait_for_event(event, seconds)

    async def lifecycle_gate(runtime: Any, seconds: float) -> bool:
        if seconds != 5:
            return await production_runtime_wait(runtime, seconds)
        await asyncio.get_running_loop().run_in_executor(None, timing._lifecycle_tick.wait)
        timing._lifecycle_tick.clear()
        return timing._closed.is_set() or runtime.state.shutdown_event.is_set()

    monkeypatch.setattr(listen_runtime, 'wait_for_event', zero_backoff_wait)
    monkeypatch.setattr(listen_runtime.ListenSessionRuntime, 'wait', lifecycle_gate)
    monkeypatch.setattr(pusher_session, 'PUSHER_RECONNECT_BASE_DELAY', 0.0)
    monkeypatch.setattr(pusher_session, 'PUSHER_RECONNECT_MAX_DELAY', 0.0)
    return timing


def clear_finalization_jobs(store: Any, uid: str) -> None:
    """Remove root-level durable jobs that the shared user fixture cannot see."""

    for snapshot in list(store.collection('conversation_finalization_jobs').stream()):
        if (snapshot.to_dict() or {}).get('uid') == uid:
            snapshot.reference.delete()


def finalization_jobs_for_uid(store: Any, uid: str) -> list[dict[str, Any]]:
    """Return root durable jobs with their deterministic IDs for wire assertions."""

    jobs = []
    for snapshot in store.collection('conversation_finalization_jobs').stream():
        payload = snapshot.to_dict() or {}
        if payload.get('uid') == uid:
            jobs.append(payload | {'job_id': snapshot.id})
    return jobs


def terminalize_finalization_job(store: Any, job_id: str, *, fenced: bool) -> None:
    """Model the pusher peer's durable terminal write before it sends its 201."""

    store.collection('conversation_finalization_jobs').document(job_id).update(
        {
            'status': 'completed' if fenced else 'dead_letter',
            'finalization_outcome': 'fenced' if fenced else 'terminal_failure',
        }
    )


def complete_finalization_job(store: Any, job_id: str) -> None:
    """Model pusher's durable completion before its success 201 reaches listen."""

    store.collection('conversation_finalization_jobs').document(job_id).update(
        {
            'status': 'completed',
            'finalization_outcome': 'completed',
            'fanout_status': 'completed',
        }
    )
