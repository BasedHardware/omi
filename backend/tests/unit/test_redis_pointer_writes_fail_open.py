"""Regression: Redis capacity must not kill live listen sessions via pointer writes.

Prod Redis Cloud ran at maxmemory for hours on 2026-09-09/10. Two best-effort
Redis pointer writes in the listen session path raised ``OutOfMemoryError``:

- ``set_in_progress_conversation_id`` — written by
  ``LiveConversationController.create_new_in_progress_conversation`` right
  AFTER the authoritative Firestore create of the in-progress conversation.
- ``set_conversation_meeting_id`` — desktop meeting attribution pointer,
  written in the same flow after the conversation exists.

The in-progress raise crashed the listen ``lifecycle`` lifetime task (the
WebSocketTaskSupervisor classifies any task exception as ``crash`` and tears
the whole session down) and, when it fired inside ``prepare()``, surfaced as
the ``Exception in ASGI application`` traceback. Sensor counts over one hour
(2026-09-10 05:00–06:00 UTC): ``BG task ws:*:lifecycle crashed:
OutOfMemoryError`` ×1043, ``Unhandled exception in WebSocket task
ws:*:lifecycle`` ×1043, ASGI traceback ×480 — a single Redis capacity
condition killing every live listen session at its 5-minute lifecycle
rollover.

Every reader of these keys already degrades when the key is absent:
``retrieve_in_progress_conversation`` falls back to the Firestore
``in_progress`` query, and the meeting mapping is an enrichment optimization
(``_meeting_context_from_redis_mapping``) whose absence falls through to the
calendar-overlap path. So the correct boundary behavior is the fail-open
contract ``_cache_set_fail_open`` established for the geo/name caches in
#13401: skip the write, record a ``capacity_full`` fallback, never raise.

Failure-Class: FC-post-commit-index-maintenance-terminal — containment at the
boundary, not at call sites.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

import database.redis_db as redis_db


class _FakeRedis:
    def __init__(self) -> None:
        self._store: Dict[str, Any] = {}
        self.expire_calls: List[tuple[str, int]] = []

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        # Real Redis returns bytes from GET; encode str writes so round-trips
        # exercise the production ``.decode()`` readers.
        self._store[key] = value.encode() if isinstance(value, str) else value

    def get(self, key: str) -> Optional[Any]:
        return self._store.get(key)

    def expire(self, key: str, ttl: int) -> None:
        self.expire_calls.append((key, ttl))

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def mget(self, keys: List[str]) -> List[Optional[Any]]:
        return [self._store.get(key) for key in keys]


class _MaxMemoryRedis(_FakeRedis):
    """SET raises exactly the way Redis Cloud does at maxmemory."""

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
        raise redis_db.redis.exceptions.OutOfMemoryError("command not allowed when used memory > 'maxmemory'.")


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedis:
    client = _FakeRedis()
    monkeypatch.setattr(redis_db, 'r', client)
    return client


@pytest.fixture
def maxmemory_redis(monkeypatch: pytest.MonkeyPatch) -> _MaxMemoryRedis:
    client = _MaxMemoryRedis()
    monkeypatch.setattr(redis_db, 'r', client)
    return client


# ── set_in_progress_conversation_id ─────────────────────────────────────────


def test_set_in_progress_conversation_id_round_trip(fake_redis: _FakeRedis) -> None:
    redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')
    assert fake_redis._store['users:uid-1:in_progress_memory_id'] == b'conv-1'
    assert redis_db.get_in_progress_conversation_id('uid-1') == 'conv-1'


def test_set_in_progress_conversation_id_applies_default_ttl(fake_redis: _FakeRedis) -> None:
    redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')
    assert fake_redis.expire_calls == [('users:uid-1:in_progress_memory_id', 300)]


def test_set_in_progress_conversation_id_applies_custom_ttl(fake_redis: _FakeRedis) -> None:
    redis_db.set_in_progress_conversation_id('uid-1', 'conv-1', ttl=90)
    assert fake_redis.expire_calls == [('users:uid-1:in_progress_memory_id', 90)]


def test_set_in_progress_conversation_id_fail_open_on_maxmemory(
    maxmemory_redis: _MaxMemoryRedis,
) -> None:
    """The lifecycle-crash regression: the pointer write must not raise."""
    redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')


def test_set_in_progress_conversation_id_fail_open_records_fallback(
    monkeypatch: pytest.MonkeyPatch,
    maxmemory_redis: _MaxMemoryRedis,
) -> None:
    recorded: list[dict[str, Any]] = []

    def _record_fallback(**kwargs: Any) -> None:
        recorded.append(kwargs)

    monkeypatch.setattr('utils.observability.fallback.record_fallback', _record_fallback)
    redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')
    assert len(recorded) == 1
    assert recorded[0]['reason'] == 'capacity_full'
    assert recorded[0]['to_mode'] == 'skip'


def test_set_in_progress_conversation_id_non_oom_error_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only capacity failures degrade; real faults stay loud."""

    class _ConnectionDropped(Exception):
        pass

    class _BrokenRedis(_FakeRedis):
        def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
            raise _ConnectionDropped('connection reset')

    monkeypatch.setattr(redis_db, 'r', _BrokenRedis())
    with pytest.raises(_ConnectionDropped):
        redis_db.set_in_progress_conversation_id('uid-1', 'conv-1')


def test_get_in_progress_conversation_id_absent_returns_empty(fake_redis: _FakeRedis) -> None:
    assert redis_db.get_in_progress_conversation_id('uid-1') == ''


def test_remove_in_progress_conversation_id_deletes(fake_redis: _FakeRedis) -> None:
    fake_redis._store['users:uid-1:in_progress_memory_id'] = 'conv-1'
    redis_db.remove_in_progress_conversation_id('uid-1')
    assert 'users:uid-1:in_progress_memory_id' not in fake_redis._store


# ── set_conversation_meeting_id ──────────────────────────────────────────────


def test_set_conversation_meeting_id_round_trip(fake_redis: _FakeRedis) -> None:
    redis_db.set_conversation_meeting_id('conv-1', 'meeting-9')
    assert fake_redis._store['conversation:conv-1:meeting_id'] == b'meeting-9'
    assert redis_db.get_conversation_meeting_id('conv-1') == 'meeting-9'


def test_set_conversation_meeting_id_applies_default_ttl(fake_redis: _FakeRedis) -> None:
    redis_db.set_conversation_meeting_id('conv-1', 'meeting-9')
    assert fake_redis.expire_calls == [('conversation:conv-1:meeting_id', 86400)]


def test_set_conversation_meeting_id_fail_open_on_maxmemory(
    maxmemory_redis: _MaxMemoryRedis,
) -> None:
    redis_db.set_conversation_meeting_id('conv-1', 'meeting-9')


def test_set_conversation_meeting_id_fail_open_records_fallback(
    monkeypatch: pytest.MonkeyPatch,
    maxmemory_redis: _MaxMemoryRedis,
) -> None:
    recorded: list[dict[str, Any]] = []

    def _record_fallback(**kwargs: Any) -> None:
        recorded.append(kwargs)

    monkeypatch.setattr('utils.observability.fallback.record_fallback', _record_fallback)
    redis_db.set_conversation_meeting_id('conv-1', 'meeting-9')
    assert len(recorded) == 1
    assert recorded[0]['reason'] == 'capacity_full'


def test_set_conversation_meeting_id_non_oom_error_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Timeout(Exception):
        pass

    class _BrokenRedis(_FakeRedis):
        def set(self, key: str, value: Any, ex: Optional[int] = None) -> None:
            raise _Timeout('redis timeout')

    monkeypatch.setattr(redis_db, 'r', _BrokenRedis())
    with pytest.raises(_Timeout):
        redis_db.set_conversation_meeting_id('conv-1', 'meeting-9')


def test_get_conversation_meeting_id_absent_returns_none(fake_redis: _FakeRedis) -> None:
    assert redis_db.get_conversation_meeting_id('conv-1') is None
