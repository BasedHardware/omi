"""Regression: an OOMing Redis must not tear down the live listen session.

Drives the REAL LiveConversationController (routers/listen/conversations.py)
through its production paths with the REAL database.redis_db pointer writers —
only the Redis socket is faked. Before the fix, the ``OutOfMemoryError`` from
``set_in_progress_conversation_id`` propagated out of
``create_new_in_progress_conversation`` into:

- ``lifecycle_loop`` — the ``lifecycle`` lifetime task crashed, and
  ``supervise_tasks`` classifies any task exception as ``crash``, tearing down
  the whole live session mid-recording.
- ``prepare()`` — the raise surfaced as the ``Exception in ASGI application``
  traceback at WebSocket bootstrap.

Both writes happen AFTER the authoritative Firestore create; the pointer is a
best-effort accelerator whose readers fall back to Firestore. The session
contract: a capacity-full Redis skips the pointer write and keeps the session
alive.

Seam: the controller receives its host and storage through
``host.persistence.call``; storage functions are dispatched by identity. The
tests substitute only ``redis_db.r`` (the socket) so the production
``set_in_progress_conversation_id`` / ``set_conversation_meeting_id`` code
runs for real, exercising the fail-open boundary, and the fake persistence
dispatch passes real functions through when asked.

The fake ``open_live_recording_session`` binds the PROPOSED conversation id
(``args[2]``) exactly as production routing does, so a rollover's
server-generated id never probes Firestore (the controller's own
guaranteed-NOT_FOUND short-circuit), while a client-supplied id is probed at
``LISTEN_CLIENT_ID_PROBE`` and the fixture decides resume vs. terminal.

Failure-Class: FC-post-commit-index-maintenance-terminal — containment at the
boundary, not at call sites.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest

import database.redis_db as redis_db
from routers.listen.conversations import LiveConversationController


class OutOfMemoryError(Exception):
    """Shape-matched to redis.exceptions.OutOfMemoryError by class name.

    Defined locally (not imported) so the name-match logic in
    ``_cache_set_fail_open`` — which cannot import the type from redis-py
    typings — is exercised exactly as it runs in production.
    """


class _MaxMemorySocket:
    """Redis socket at maxmemory: every write command raises OOM."""

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        raise OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")

    def expire(self, key: str, ttl: int) -> None:
        raise OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")

    def get(self, key: str) -> Optional[bytes]:
        return None

    def delete(self, key: str) -> None:
        raise OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")


class _ExpireOnlyOOMSocket(_MaxMemorySocket):
    """SET lands (memory freed mid-incident) but EXPIRE still raises OOM."""

    def __init__(self) -> None:
        self.store: Dict[str, Any] = {}

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        self.store[key] = value


class _RecordingSocket:
    """Healthy Redis socket recording writes for assertions."""

    def __init__(self) -> None:
        self.store: Dict[str, bytes] = {}
        self.ttls: Dict[str, int] = {}

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        self.store[key] = value.encode() if isinstance(value, str) else value

    def expire(self, key: str, ttl: int) -> None:
        self.ttls[key] = ttl

    def get(self, key: str) -> Optional[bytes]:
        return self.store.get(key)

    def delete(self, key: str) -> None:
        self.store.pop(key, None)


class _Host:
    """Minimal listen host driving the real controller.

    Storage calls dispatch by function: the real ``redis_db`` pointer writers
    run against the (possibly OOMing) socket fake; Firestore-side functions
    return canned fixtures. ``get_conversation`` is read-site aware because the
    controller reads the same document through different sites
    (LISTEN_LIFECYCLE_POLL vs LISTEN_CLIENT_ID_PROBE) and the routing decision
    differs per site.

    ``recover_socket`` models capacity restored mid-session: from the second
    Redis dispatch onward the healthy socket serves the writes, proving the
    session that survived the incident also resumes correct caching without a
    restart.
    """

    def __init__(
        self,
        self_socket: Any,
        *,
        meetings: Optional[List[Dict[str, Any]]] = None,
        lifecycle_conversations: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
        client_probe_conversations: Optional[Dict[str, Optional[Dict[str, Any]]]] = None,
        retrieve_in_progress: Optional[Dict[str, Any]] = None,
        wait_returns: Optional[List[bool]] = None,
        conversation_creation_timeout: int = 120,
        source: str = 'omi',
        current_conversation_id: Optional[str] = None,
        client_conversation_id: Optional[str] = None,
        is_multi_channel: bool = False,
        recover_socket: Any = None,
    ) -> None:
        self.request = SimpleNamespace(
            uid='uid-1',
            source=source,
            codec=None,
            conversation_role=None,
            geolocation=None,
            call_id=None,
            onboarding_mode=None,
        )
        self.client_device_context = SimpleNamespace(client_device_id='dev-1', platform='desktop')
        self.language = 'en'
        self.use_custom_stt = False
        self.client_conversation_id = client_conversation_id
        self.recording_session_id = 'session-1'
        self.is_multi_channel = is_multi_channel
        self.private_cloud_sync_enabled = False
        self.onboarding_admitted = False
        self.request_conversation_processing = None
        self.conversation_creation_timeout = conversation_creation_timeout
        self.state = SimpleNamespace(current_conversation_id=current_conversation_id, active=True)
        self.recording_session_ids_by_conversation: Dict[str, str] = {}
        self._socket = self_socket
        self._recover_socket = recover_socket
        self._redis_dispatches = 0
        self._meetings = meetings
        self._lifecycle_conversations = lifecycle_conversations or {}
        self._client_probe = client_probe_conversations or {}
        self._retrieve_in_progress = retrieve_in_progress
        self._wait_returns = wait_returns or [False]
        self._wait_index = 0
        self.sent_events: List[Any] = []
        self.storage_calls: List[str] = []
        self.transcripts = SimpleNamespace(flush_speaker_assignments=self._flush_speakers)
        self.persistence = SimpleNamespace(call=self._call)

    async def wait(self, seconds: float) -> bool:
        index = min(self._wait_index, len(self._wait_returns) - 1)
        self._wait_index += 1
        return self._wait_returns[index]

    def send_event(self, event: Any) -> None:
        self.sent_events.append(event)

    async def _flush_speakers(self, conversation_id: Optional[str]) -> None:
        return None

    def spawn(self, coro: Any, name: str = '') -> Any:
        return asyncio.get_event_loop().create_task(coro)

    async def _call(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        self.storage_calls.append(fn.__name__)
        # Real Redis writers run against the socket fake — this is the seam
        # that proves the production boundary holds.
        if getattr(fn, '__module__', '') == 'database.redis_db':
            self._redis_dispatches += 1
            if self._recover_socket is not None and self._redis_dispatches > 1:
                self._socket = self._recover_socket
            saved = redis_db.r
            redis_db.r = self._socket
            try:
                return fn(*args, **kwargs)
            finally:
                redis_db.r = saved
        if fn.__name__ == 'open_live_recording_session':
            # Production routing: the binding resolves to the PROPOSED id
            # (server-generated on rollover, client-supplied on reconnect).
            return {
                'requires_rollover': False,
                'conversation_id': args[2],
                'lifecycle_version': 1,
                'lifecycle_phase': 'open',
                'lifecycle_sequence': 1,
                'conversation_snapshot_known': False,
            }
        if fn.__name__ == 'get_conversation':
            read_site = kwargs.get('read_site')
            if read_site is not None and 'LISTEN_CLIENT_ID_PROBE' in str(read_site):
                return self._client_probe.get(args[1])
            return self._lifecycle_conversations.get(args[1])
        if fn.__name__ == 'retrieve_in_progress_conversation':
            return self._retrieve_in_progress
        if fn.__name__ == 'get_meetings_in_time_range':
            return self._meetings
        if fn.__name__ == 'create_in_progress_conversation':
            return None
        if fn.__name__ == 'delete_empty_recording_conversation':
            return True
        return None


def _stale_empty_conversation(conversation_id: str = 'conv-1') -> Dict[str, Any]:
    return {
        'id': conversation_id,
        'status': 'in_progress',
        'transcript_segments': [],
        'has_content': False,
        'finished_at': datetime.now(timezone.utc) - timedelta(seconds=600),
    }


def _fresh_conversation(conversation_id: str = 'conv-1') -> Dict[str, Any]:
    return {
        'id': conversation_id,
        'status': 'in_progress',
        'discarded': False,
        'finished_at': datetime.now(timezone.utc),
    }


def _overlapping_meeting() -> Dict[str, Any]:
    return {
        'id': 'meeting-9',
        'start_time': datetime.now(timezone.utc) - timedelta(minutes=1),
        'end_time': datetime.now(timezone.utc) + timedelta(minutes=1),
    }


@contextmanager
def _swap_redis_socket(socket: Any) -> Iterator[None]:
    saved = redis_db.r
    redis_db.r = socket
    try:
        yield
    finally:
        redis_db.r = saved


# ── lifecycle_loop: the crash that tore down live sessions ──────────────────


async def test_lifecycle_loop_survives_maxmemory_on_conversation_missing():
    """conversation missing → create_new rollover → pointer write OOMs → loop must live."""
    host = _Host(
        _MaxMemorySocket(),
        lifecycle_conversations={'conv-1': None},
        wait_returns=[False, True],  # first poll runs, second wakes for shutdown
        current_conversation_id='conv-1',
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.lifecycle_loop(), timeout=5)

    # The rollover path ran and the session stayed alive: no exception escaped.
    assert 'set_in_progress_conversation_id' in host.storage_calls


async def test_lifecycle_loop_survives_maxmemory_on_stale_rollover():
    """Stale in_progress conversation → process_and_create_new → OOMing pointer write.

    This is the prod crash shape: five minutes of recorded audio, the lifecycle
    rollover finalizes the old conversation and opens a new one, and the new
    pointer write raises out of the lifetime task.
    """
    host = _Host(
        _MaxMemorySocket(),
        lifecycle_conversations={'conv-1': _stale_empty_conversation()},
        wait_returns=[False, True],
        current_conversation_id='conv-1',
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.lifecycle_loop(), timeout=5)

    assert 'set_in_progress_conversation_id' in host.storage_calls
    assert 'delete_empty_recording_conversation' in host.storage_calls


async def test_lifecycle_loop_survives_maxmemory_on_terminal_status():
    """Completed status → rollover → OOMing pointer write; loop must live."""
    terminal = {'id': 'conv-1', 'status': 'completed', 'finished_at': datetime.now(timezone.utc)}
    host = _Host(
        _MaxMemorySocket(),
        lifecycle_conversations={'conv-1': terminal},
        wait_returns=[False, True],
        current_conversation_id='conv-1',
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.lifecycle_loop(), timeout=5)

    assert 'set_in_progress_conversation_id' in host.storage_calls


async def test_lifecycle_loop_survives_maxmemory_during_desktop_meeting_write():
    """Desktop source with an overlapping meeting → meeting pointer write OOMs too."""
    host = _Host(
        _MaxMemorySocket(),
        lifecycle_conversations={'conv-1': _stale_empty_conversation()},
        meetings=[_overlapping_meeting()],
        source='desktop',
        wait_returns=[False, True],
        current_conversation_id='conv-1',
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.lifecycle_loop(), timeout=5)

    assert 'set_conversation_meeting_id' in host.storage_calls
    assert 'set_in_progress_conversation_id' in host.storage_calls


async def test_lifecycle_loop_healthy_redis_still_writes_pointer():
    """Control: with a healthy Redis the pointer write lands."""
    socket = _RecordingSocket()
    host = _Host(
        socket,
        lifecycle_conversations={'conv-1': _stale_empty_conversation()},
        wait_returns=[False, True],
        current_conversation_id='conv-1',
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.lifecycle_loop(), timeout=5)

    assert any(key.startswith('users:uid-1:in_progress_memory_id') for key in socket.store)


async def test_lifecycle_loop_multiple_rollovers_survive_persistent_maxmemory():
    """Maxmemory persists across rollovers — the loop keeps serving transcript flow."""
    host = _Host(
        _MaxMemorySocket(),
        lifecycle_conversations={'conv-1': _stale_empty_conversation()},
        wait_returns=[False, False, False, True],
        current_conversation_id='conv-1',
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.lifecycle_loop(), timeout=5)

    # Repeated rollovers, each hitting the OOMing write; loop alive throughout.
    assert host.storage_calls.count('set_in_progress_conversation_id') >= 2


async def test_lifecycle_loop_records_capacity_full_fallback_telemetry(monkeypatch: pytest.MonkeyPatch):
    """The skip is observable: each surviving write records a capacity_full fallback."""
    recorded: List[Dict[str, Any]] = []

    def _record_fallback(**kwargs: Any) -> None:
        recorded.append(kwargs)

    monkeypatch.setattr('utils.observability.fallback.record_fallback', _record_fallback)
    host = _Host(
        _MaxMemorySocket(),
        lifecycle_conversations={'conv-1': _stale_empty_conversation()},
        wait_returns=[False, True],
        current_conversation_id='conv-1',
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.lifecycle_loop(), timeout=5)

    assert recorded, 'the degraded write must be visible to fallback telemetry'
    assert all(entry['reason'] == 'capacity_full' for entry in recorded)


async def test_lifecycle_loop_recovers_pointer_once_capacity_restored():
    """Recovery without a session restart: once Redis accepts writes again the
    next rollover's pointer lands — the session that survived the incident is
    the session that resumes correct caching."""
    healthy = _RecordingSocket()
    host = _Host(
        _MaxMemorySocket(),
        lifecycle_conversations={'conv-1': _stale_empty_conversation()},
        wait_returns=[False, False, True],
        current_conversation_id='conv-1',
        recover_socket=healthy,
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.lifecycle_loop(), timeout=5)

    assert host.storage_calls.count('set_in_progress_conversation_id') >= 2
    assert any(key.startswith('users:uid-1:in_progress_memory_id') for key in healthy.store)


# ── prepare(): the WebSocket bootstrap that surfaced the ASGI traceback ─────


async def test_prepare_bootstrap_survives_maxmemory():
    """No existing conversation → create_new inside prepare() → the raise used
    to escape the WebSocket adapter as ``Exception in ASGI application``."""
    host = _Host(_MaxMemorySocket(), retrieve_in_progress=None)

    controller = LiveConversationController(host)
    result = await asyncio.wait_for(controller.prepare(), timeout=5)

    assert result is None
    assert 'set_in_progress_conversation_id' in host.storage_calls
    assert host.sent_events, 'the conversation session event must still reach the client'


async def test_prepare_stale_pointer_rolls_over_under_maxmemory():
    """Stale in-progress pointer → process_and_create_new → OOMing write inside
    prepare(); the socket must survive and still report the finalized id."""
    stale = {
        'id': 'conv-old',
        'source': 'omi',
        'finished_at': datetime.now(timezone.utc) - timedelta(seconds=600),
    }
    host = _Host(_MaxMemorySocket(), retrieve_in_progress=stale)

    controller = LiveConversationController(host)
    result = await asyncio.wait_for(controller.prepare(), timeout=5)

    assert result == 'conv-old'
    assert 'set_in_progress_conversation_id' in host.storage_calls


async def test_prepare_attach_existing_never_writes_pointer():
    """Control: attaching to a fresh in-progress conversation takes the binding
    path — no pointer write is needed, and none may crash."""
    fresh = {
        'id': 'conv-1',
        'source': 'omi',
        'finished_at': datetime.now(timezone.utc),
    }
    host = _Host(_MaxMemorySocket(), retrieve_in_progress=fresh)

    controller = LiveConversationController(host)
    result = await asyncio.wait_for(controller.prepare(), timeout=5)

    assert result is None
    assert 'set_in_progress_conversation_id' not in host.storage_calls
    assert host.sent_events


async def test_prepare_multi_channel_bootstrap_survives_maxmemory():
    """Phone-call sockets bootstrap a conversation inside prepare() directly."""
    host = _Host(_MaxMemorySocket(), is_multi_channel=True)

    controller = LiveConversationController(host)
    result = await asyncio.wait_for(controller.prepare(), timeout=5)

    assert result is None
    assert 'set_in_progress_conversation_id' in host.storage_calls


# ── create_new_in_progress_conversation: reconnect branches ─────────────────


async def test_create_new_survives_maxmemory_and_emits_session_event():
    """The fresh-create path must not raise; the client-visible conversation
    session event must still be sent."""
    host = _Host(_MaxMemorySocket())
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.create_new_in_progress_conversation(), timeout=5)

    assert 'set_in_progress_conversation_id' in host.storage_calls
    assert host.sent_events, 'the conversation session event must still reach the client'


async def test_create_new_survives_maxmemory_on_client_reconnect_resume():
    """Client-supplied conversation id probing an in-progress row resumes it —
    and the resume branch re-writes the pointer, which must not raise either."""
    host = _Host(
        _MaxMemorySocket(),
        client_probe_conversations={'conv-1': _fresh_conversation()},
        client_conversation_id='conv-1',
    )
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.create_new_in_progress_conversation(), timeout=5)

    assert 'set_in_progress_conversation_id' in host.storage_calls
    assert host.sent_events


async def test_create_new_survives_maxmemory_on_desktop_meeting_write():
    host = _Host(_MaxMemorySocket(), meetings=[_overlapping_meeting()], source='desktop')
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.create_new_in_progress_conversation(), timeout=5)

    assert 'set_conversation_meeting_id' in host.storage_calls


async def test_create_new_healthy_control_writes_both_pointers():
    socket = _RecordingSocket()
    host = _Host(socket, meetings=[_overlapping_meeting()], source='desktop')
    controller = LiveConversationController(host)

    await asyncio.wait_for(controller.create_new_in_progress_conversation(), timeout=5)

    pointer_keys = [key for key in socket.store if key.startswith('users:uid-1:in_progress_memory_id')]
    assert len(pointer_keys) == 1
    assert socket.ttls[pointer_keys[0]] == 300
    meeting_keys = [key for key in socket.store if key.endswith(':meeting_id')]
    assert len(meeting_keys) == 1
    assert socket.store[meeting_keys[0]] == 'meeting-9'.encode()
    assert socket.ttls[meeting_keys[0]] == 86400


# ── degradation semantics: what the skip costs ─────────────────────────────


async def test_skipped_pointer_degrades_to_firestore_fallback_on_read():
    """The pointer's absence is the degraded mode readers already handle:
    get_in_progress_conversation_id returns '' and the caller falls back to
    the Firestore in-progress query."""
    with _swap_redis_socket(_MaxMemorySocket()):
        redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')  # must not raise
        assert redis_db.get_in_progress_conversation_id('uid-1') == ''


def test_healthy_pointer_read_returns_conversation_id():
    socket = _RecordingSocket()
    with _swap_redis_socket(socket):
        redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')
        assert redis_db.get_in_progress_conversation_id('uid-1') == 'conv-1'


def test_expire_oom_also_fails_open():
    """Maxmemory denies EXPIRE just as readily as SET: the second command of
    the pointer write must not raise either (partial write: key present, no
    TTL — the degraded state, honestly asserted)."""
    socket = _ExpireOnlyOOMSocket()
    with _swap_redis_socket(socket):
        redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')
        assert socket.store.get('users:uid-1:in_progress_memory_id') is not None


def test_real_redis_oom_exception_class_fails_open():
    """The name-match containment must hold for redis-py's own
    OutOfMemoryError — the class prod actually raises — not just the local
    shape-alike."""
    real_oom = redis_db.redis.exceptions.OutOfMemoryError

    class _ProdOOMSocket(_RecordingSocket):
        def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
            raise real_oom("command not allowed when used memory > 'maxmemory'.")

    with _swap_redis_socket(_ProdOOMSocket()):
        redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')  # must not raise


def test_fail_open_logs_warning_not_error(caplog: pytest.LogCaptureFixture):
    """Severity contract: a skipped best-effort pointer is a WARNING, not the
    ERROR line the prod sensor was paging on."""
    with caplog.at_level(logging.DEBUG, logger='database.redis_db'):
        with _swap_redis_socket(_MaxMemorySocket()):
            redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')
    skipped = [r for r in caplog.records if 'capacity_full' in r.getMessage()]
    assert skipped and skipped[0].levelno == logging.WARNING
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_geo_and_name_caches_share_the_fail_open_contract():
    """Family guard: the #13401 members and the two listen pointers are one
    contract now — a capacity-full Redis skips all of them."""
    for writer in (
        lambda: redis_db.cache_user_name('uid-1', 'Ada'),
        lambda: redis_db.cache_user_geolocation('uid-1', {'latitude': 1.0, 'longitude': 2.0}),
        lambda: redis_db.set_in_progress_conversation_id('uid-1', 'conv-1'),
        lambda: redis_db.set_conversation_meeting_id('conv-1', 'meeting-9'),
    ):
        with _swap_redis_socket(_MaxMemorySocket()):
            writer()  # must not raise for any family member


# ── read-side fallback paths used when the pointer is skipped ───────────────


def test_retrieve_in_progress_conversation_falls_back_to_firestore(monkeypatch: pytest.MonkeyPatch):
    """The reader that makes skipping safe: empty Redis pointer → Firestore query."""
    from utils.conversations import process_conversation as pc

    def _empty_pointer(uid: str) -> str:
        return ''

    def _firestore_in_progress(uid: str):
        return {'id': 'conv-fs', 'status': 'in_progress', 'finished_at': datetime.now(timezone.utc)}

    monkeypatch.setattr(pc.redis_db, 'get_in_progress_conversation_id', _empty_pointer)
    monkeypatch.setattr(pc.conversations_db, 'get_conversation', lambda *a, **k: None)
    monkeypatch.setattr(pc.conversations_db, 'get_in_progress_conversation', _firestore_in_progress)

    assert (pc.retrieve_in_progress_conversation('uid-1') or {}).get('id') == 'conv-fs'


def test_retrieve_in_progress_conversation_prefers_pointer_when_present(
    monkeypatch: pytest.MonkeyPatch,
):
    from utils.conversations import process_conversation as pc

    def _pointer(uid: str) -> str:
        return 'conv-redis'

    def _pointer_conversation(uid: str, conversation_id: str, **kwargs: Any):
        return {'id': 'conv-redis', 'status': 'in_progress', 'finished_at': datetime.now(timezone.utc)}

    monkeypatch.setattr(pc.redis_db, 'get_in_progress_conversation_id', _pointer)
    monkeypatch.setattr(pc.conversations_db, 'get_conversation', _pointer_conversation)
    called = {'firestore': False}

    def _firestore_in_progress(uid: str):
        called['firestore'] = True
        return None

    monkeypatch.setattr(pc.conversations_db, 'get_in_progress_conversation', _firestore_in_progress)

    assert (pc.retrieve_in_progress_conversation('uid-1') or {}).get('id') == 'conv-redis'


def test_meeting_context_reader_survives_raising_redis():
    """The meeting-pointer reader degrades on its own: a Redis that raises is
    caught inside _meeting_context_from_redis_mapping and enrichment falls
    through to the calendar-overlap path."""
    from models.conversation import Conversation
    from models.conversation_enums import ConversationSource, ConversationStatus
    from models.structured import Structured  # type: ignore[reportAttributeAccessIssue]
    from utils.conversations import process_conversation as pc

    class _RaisingGetSocket(_MaxMemorySocket):
        def get(self, key: str) -> Optional[bytes]:
            raise OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")

    conversation = Conversation(
        id='conv-1',
        created_at=datetime.now(timezone.utc),
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        structured=Structured(),
        language='en',
        transcript_segments=[],
        photos=[],
        status=ConversationStatus.in_progress,
        source=ConversationSource.desktop,
    )
    with _swap_redis_socket(_RaisingGetSocket()):
        assert pc._meeting_context_from_redis_mapping('uid-1', conversation) is None


# ── supervisor classification: why the raise was fatal ──────────────────────


async def test_supervisor_classifies_task_exception_as_crash():
    """Documents the kill mechanism this fix removes from the equation: any
    lifetime-task exception is a supervisor ``crash`` and tears the session
    down. With the boundary fixed, the lifecycle task no longer raises on
    Redis capacity."""
    from utils.async_tasks import supervise_tasks

    async def _boom() -> None:
        raise OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")

    receive_task = asyncio.ensure_future(asyncio.sleep(3600))
    bg_task = asyncio.ensure_future(_boom())
    try:
        result = await asyncio.wait_for(
            supervise_tasks(receive_task=receive_task, bg_tasks=[bg_task], label='listen'),
            timeout=5,
        )
        assert result.reason == 'crash'
        assert result.task_name is not None
    finally:
        receive_task.cancel()
        bg_task.cancel()


async def test_crashed_lifetime_task_takes_down_sibling_tasks():
    """The other half of the blast radius: a crashed lifetime task cancels its
    siblings — the transcript stream, heartbeat — which is why the pointer
    write's raise killed users' live sessions rather than just a pointer."""
    from utils.async_tasks import supervise_tasks

    sibling_finished = asyncio.Event()

    async def _boom() -> None:
        raise OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")

    async def _sibling() -> None:
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            sibling_finished.set()
            raise

    receive_task = asyncio.ensure_future(asyncio.sleep(3600))
    bg_task = asyncio.ensure_future(_boom())
    sibling = asyncio.ensure_future(_sibling())
    try:
        await asyncio.wait_for(
            supervise_tasks(receive_task=receive_task, bg_tasks=[bg_task, sibling], label='listen'),
            timeout=5,
        )
    finally:
        receive_task.cancel()
        bg_task.cancel()
        sibling.cancel()
        await asyncio.sleep(0)
    assert (
        sibling_finished.is_set()
    ), 'a crashed lifetime task must cancel siblings (documents the pre-fix blast radius)'
