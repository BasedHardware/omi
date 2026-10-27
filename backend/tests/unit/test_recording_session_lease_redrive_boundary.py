"""The renewal redrive's cycle contract: ends, waits, wakes, and the fence.

Failure-Class: FC-failed-renewal-cadence-decays-live-fence (declared with the
cadence fix; see ``test_recording_session_lease_redrive.py`` for the damage
statement). This file pins the spawned cycle itself: what ends it, what it
waits, how a shutdown wake interacts with the attempt budget, what reaches the
persistence boundary, and — end to end over fake Firestore through the real
lifecycle owner — how the fence moves under enforce mode, a fully exhausted
budget, and the classified transients the write layer produces.

Guards:
- True, a contained raise, a shutdown wake, and full exhaustion each end the
  cycle with an exact call/wait schedule;
- the controller consumes the lifecycle classifier's verdict (False) and never
  sees raw provider shapes; a structural raise arrives from the persistence
  layer itself;
- a host without a ``wait`` seam (older test fakes) degrades to the contained
  crash log, never a task escape;
- enforce mode still raises through the first attempt and writes nothing;
- a budget exhausted against a dead data plane stops at exactly four attempts
  with the fence untouched;
- the spawned cycle renews the binding it was armed with; a mid-cycle rollover
  is picked up by the next cycle, never by the in-flight one.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import InvalidArgument, PermissionDenied, ServiceUnavailable

from database import recording_sessions
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from routers.listen.conversations import (
    RECORDING_SESSION_LEASE_RETRY_ATTEMPTS,
    RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS,
    LiveConversationController,
)
from utils.conversations import lifecycle as lifecycle_service

_LOGGER_NAME = 'routers.listen.conversations'
_DOC = Path(__file__).resolve().parents[2] / 'docs' / 'listen_pusher_pipeline.mdx'
_SOURCE = Path(__file__).resolve().parents[2] / 'routers' / 'listen' / 'conversations.py'
_RENEWAL = 'renew_live_recording_session_lease'


# ── Fixtures ─────────────────────────────────────────────────────────────────


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.value = start

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: Any) -> datetime:
        self.value = self.value + timedelta(**kwargs)
        return self.value


class _RedriveHost:
    """Records spawned tasks, persistence calls, and wait calls."""

    def __init__(self, results: list[Any], clock: _Clock, *, with_wait: bool = True) -> None:
        self.request = SimpleNamespace(uid='uid')
        self.state = SimpleNamespace(current_conversation_id='conversation')
        self.recording_session_id = 'session'
        self.clock = clock
        self._results = list(results)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.persistence = SimpleNamespace(call=self._call)
        self.spawned: list[asyncio.Task] = []
        self.waits: list[float] = []
        self.wait_returns: list[bool] = []
        if with_wait:
            self.wait = self._wait  # type: ignore[method-assign]

    async def _call(self, fn, *args, **kwargs):
        self.calls.append((fn.__name__, args))
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def spawn(self, coro, *, name: str):
        self.spawned.append(asyncio.create_task(coro, name=name))
        return self.spawned[-1]

    async def _wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        if self.wait_returns:
            return self.wait_returns.pop(0)
        return False

    def queue_result(self, result: Any) -> None:
        self._results.append(result)


def _clock_at() -> _Clock:
    return _Clock(datetime(2026, 10, 22, 15, tzinfo=timezone.utc))


def _blipped_host(blips: int, clock: _Clock | None = None) -> tuple[_RedriveHost, _Clock]:
    clock = clock or _clock_at()
    return _RedriveHost([False] * blips + [True], clock), clock


async def _drain(host: _RedriveHost) -> None:
    await asyncio.gather(*host.spawned)


def _controller(host: _RedriveHost) -> LiveConversationController:
    return LiveConversationController(host, clock=host.clock)


# ── Cycle ends and the exact wait schedule ───────────────────────────────────


async def test_failed_renewal_redrives_within_the_same_minute():
    host, _ = _blipped_host(blips=1)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_committed_renewal_ends_the_cycle_without_waits():
    host, _ = _blipped_host(blips=0)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == []
    assert len(host.calls) == 1


async def test_permanent_rejection_is_contained_and_consumes_no_waits(caplog):
    host = _RedriveHost([], _clock_at())
    host.queue_result(PermissionDenied('enforce mode refuses'))
    _controller(host).note_audio_activity()

    with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
        await _drain(host)

    assert host.waits == []
    crash_records = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert len(crash_records) == 1
    assert 'uid=uid' in crash_records[0].getMessage()
    assert 'session=session' in crash_records[0].getMessage()


async def test_structural_failure_mid_cycle_stops_the_schedule(caplog):
    host = _RedriveHost([], _clock_at())
    host.queue_result(False)
    host.queue_result(RuntimeError('persistence executor died'))
    _controller(host).note_audio_activity()

    with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
        await _drain(host)

    assert len(host.calls) == 2
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]
    crash_records = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert len(crash_records) == 1


async def test_redrive_waits_are_bounded_and_short():
    host, _ = _blipped_host(blips=RECORDING_SESSION_LEASE_RETRY_ATTEMPTS)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * RECORDING_SESSION_LEASE_RETRY_ATTEMPTS
    assert len(host.calls) == 1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS


async def test_every_wait_is_the_short_delay_never_the_full_minute():
    host, _ = _blipped_host(blips=RECORDING_SESSION_LEASE_RETRY_ATTEMPTS)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert set(host.waits) == {RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS}
    assert timedelta(minutes=1).total_seconds() not in host.waits


async def test_full_redrive_exhaustion_stops_without_one_more_renewal():
    host = _RedriveHost([False] * (1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS), _clock_at())
    _controller(host).note_audio_activity()
    await _drain(host)

    assert len(host.calls) == 1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS
    assert len(host.waits) == RECORDING_SESSION_LEASE_RETRY_ATTEMPTS


async def test_shutdown_wake_during_a_wait_ends_the_cycle():
    host, _ = _blipped_host(blips=2)
    host.wait_returns = [True]  # the first wait wakes for shutdown
    _controller(host).note_audio_activity()
    await _drain(host)

    assert len(host.calls) == 1
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_shutdown_wake_on_the_last_wait_skips_the_final_attempt():
    host, _ = _blipped_host(blips=RECORDING_SESSION_LEASE_RETRY_ATTEMPTS)
    host.wait_returns = [False, True]
    _controller(host).note_audio_activity()
    await _drain(host)

    assert len(host.calls) == 2
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * 2


async def test_shutdown_wake_false_runs_the_full_schedule():
    host, _ = _blipped_host(blips=1)
    host.wait_returns = [False]
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]
    assert len(host.calls) == 2


# ── The controller consumes the classifier's verdict ────────────────────────


async def test_classified_transient_false_redrives():
    host = _RedriveHost([False, True], _clock_at())
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_mixed_transient_shapes_share_one_schedule():
    host = _RedriveHost([False, False, True], _clock_at())
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * 2
    assert len(host.calls) == 3


async def test_redrive_records_no_fallback_degradation_event(caplog):
    """The redrive is controller-side bookkeeping, not a degraded write: the
    transient arm's no-``omi_fallback_total`` contract survives it."""
    host, _ = _blipped_host(blips=2)
    _controller(host).note_audio_activity()

    with caplog.at_level(logging.WARNING):
        await _drain(host)

    fallback_records = [r for r in caplog.records if 'fallback' in r.getMessage().lower()]
    assert fallback_records == []


async def test_host_without_wait_degrades_to_contained_crash_log(caplog):
    """An older test-fake host without a ``wait`` seam must not escape the
    spawned task: the structural containment logs and the cycle ends."""
    host = _RedriveHost([False, True], _clock_at(), with_wait=False)
    _controller(host).note_audio_activity()

    with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
        await _drain(host)

    crash_records = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert len(crash_records) == 1


async def test_host_without_wait_on_clean_renewal_needs_no_seam(caplog):
    host = _RedriveHost([True], _clock_at(), with_wait=False)
    _controller(host).note_audio_activity()

    with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
        await _drain(host)

    crash_records = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert crash_records == []
    assert len(host.calls) == 1


# ── Persistence-boundary call shape ──────────────────────────────────────────


async def test_redrive_calls_the_lifecycle_owner_positionally():
    host, _ = _blipped_host(blips=0)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.calls == [(_RENEWAL, ('uid', 'session', 'conversation'))]


async def test_redrive_passes_no_firestore_client_through_the_host():
    """The production host's persistence boundary owns the client injection;
    the controller passes none."""
    host, _ = _blipped_host(blips=0)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.calls[0][1] == ('uid', 'session', 'conversation')


async def test_redrive_reuses_the_armed_binding_mid_cycle():
    """A rollover landing inside an in-flight cycle does not redirect it: the
    cycle renews the binding it was armed with; the next cycle picks up the
    new one."""
    host, clock = _blipped_host(blips=1)
    _controller(host).note_audio_activity()
    in_flight = host.spawned[-1]

    host.state.current_conversation_id = 'conversation-two'
    host.recording_session_id = 'session-two'
    await _drain(host)

    assert host.calls[:2] == [(_RENEWAL, ('uid', 'session', 'conversation'))] * 2
    assert in_flight in host.spawned

    clock.advance(minutes=1)
    _controller(host).note_audio_activity()
    await _drain(host)
    assert host.calls[-1] == (_RENEWAL, ('uid', 'session-two', 'conversation-two'))
    assert len(host.calls) == 3  # two in the first cycle (False, True) + the second cycle's commit


async def test_every_cycle_passes_the_live_uid():
    host, clock = _blipped_host(blips=0)
    _controller(host).note_audio_activity()
    await _drain(host)

    host.request = SimpleNamespace(uid='uid-next')
    clock.advance(minutes=1)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.calls[-1] == (_RENEWAL, ('uid-next', 'session', 'conversation'))


# ── End to end: the real lifecycle boundary over fake Firestore ──────────────


@dataclass
class _Snapshot:
    data: dict[str, Any] | None

    @property
    def exists(self) -> bool:
        return self.data is not None

    def to_dict(self) -> dict[str, Any] | None:
        return copy.deepcopy(self.data)


@dataclass
class _DocumentRef:
    firestore: '_BlipFirestore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.firestore.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.firestore, self.path + (name,))


@dataclass
class _CollectionRef:
    firestore: '_BlipFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> '_DocumentRef':
        return _DocumentRef(self.firestore, self.path + (document_id,))


@dataclass
class _Transaction:
    firestore: '_BlipFirestore'

    def create(self, document: _DocumentRef, data: dict[str, Any]) -> None:
        if document.path in self.firestore.documents:
            raise RuntimeError('already exists')
        self.firestore.documents[document.path] = copy.deepcopy(data)

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.firestore.documents[document.path].update(copy.deepcopy(updates))


class _BlipFirestore:
    """Fake Firestore that rejects the renewal's first commits with a queued
    error, then serves the real document."""

    def __init__(self) -> None:
        self.documents: dict[tuple[str, ...], dict[str, Any]] = {}
        self.commit_errors: list[BaseException] = []
        self.transaction_opens = 0

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        self.transaction_opens += 1
        return _Transaction(self)


class _RenewalHost:
    """Drives the controller's real redrive task against the real lifecycle
    renewal over a fake Firestore, with an event-loop-free wait seam."""

    def __init__(self, store: _BlipFirestore, clock: _Clock) -> None:
        self.request = SimpleNamespace(uid='uid')
        self.state = SimpleNamespace(current_conversation_id='conversation')
        self.recording_session_id = 'session'
        self.clock = clock
        self.store = store
        self.waits: list[float] = []
        self.spawned: list[asyncio.Task] = []
        self.wait_returns: list[bool] = []
        self.persistence = SimpleNamespace(call=self._call)

    async def _call(self, fn, *args, **kwargs):
        kwargs.setdefault('firestore_client', self.store)
        return fn(*args, **kwargs)

    def spawn(self, coro, *, name: str):
        self.spawned.append(asyncio.create_task(coro, name=name))
        return self.spawned[-1]

    async def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        await asyncio.sleep(0)
        if self.wait_returns:
            return self.wait_returns.pop(0)
        return False


def _seed_session_row(store: _BlipFirestore, started_at: datetime) -> None:
    store.documents[('users', 'uid', 'recording_sessions', 'session')] = {
        'schema_version': recording_sessions.RECORDING_SESSION_SCHEMA_VERSION,
        'uid': 'uid',
        'recording_session_id': 'session',
        'conversation_id': 'conversation',
        'lifecycle_version': recording_sessions.LIFECYCLE_ENVELOPE_VERSION,
        'lifecycle_phase': 'in_progress',
        'lifecycle_sequence': 0,
        'created_at': started_at,
        'updated_at': started_at,
        'lease_expires_at': started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION,
    }


@pytest.fixture
def blip_store(monkeypatch):
    store = _BlipFirestore()
    _seed_session_row(store, datetime(2026, 10, 22, 15, tzinfo=timezone.utc))

    def transactional(func):
        def locked(transaction, *args, **kwargs):
            if store.commit_errors:
                raise store.commit_errors.pop(0)
            return func(transaction, *args, **kwargs)

        return locked

    monkeypatch.setattr(recording_sessions.firestore, 'transactional', transactional)

    def budget_retry(*a, **kw):
        return run_with_transaction_contention_retry(*a, sleep=lambda _delay: None, random_value=lambda: 0, **kw)

    monkeypatch.setattr(recording_sessions, 'run_with_transaction_contention_retry', budget_retry)
    monkeypatch.setattr(recording_sessions, '_now', lambda: datetime.now(timezone.utc))
    return store


async def test_redriven_renewal_advances_the_durable_fence(blip_store, monkeypatch):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    # Three retirements exhaust run_transactional's internal fresh-id restarts,
    # so the retirement surfaces at the lifecycle boundary as the classified
    # transient (False) — the exact decay signal the redrive exists for. The
    # cycle's second attempt then commits on a clean data plane.
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 3
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert blip_store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_converged_commit_advances_updated_at_too(blip_store, monkeypatch):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 3
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert blip_store.documents[path]['updated_at'] == clock.value


async def test_converged_cycle_used_exactly_two_boundary_attempts(blip_store, monkeypatch):
    """One attempt False through the classifier, one committed: the cycle does
    not over-try once the fence moved."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 3
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert host.store.transaction_opens == 4  # 3 internal restarts + the commit


async def test_converged_cycle_redrives_to_a_clean_no_op(blip_store, monkeypatch):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 3
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    path = ('users', 'uid', 'recording_sessions', 'session')
    first_commit = blip_store.documents[path]['lease_expires_at']
    # Deplete the fence to a minute of runway so the second cycle's renewal
    # has a real stamp to land (the runway skip leaves a still-healthy fence
    # untouched by design).
    blip_store.documents[path]['lease_expires_at'] = first_commit - timedelta(minutes=4)

    clock.advance(minutes=1)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert blip_store.documents[path]['lease_expires_at'] == (first_commit + timedelta(minutes=1))
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_availability_blip_converges_through_the_shared_classifier(blip_store, monkeypatch):
    """A data-plane 503 exhausts the write layer untouched, is classified by
    the shared transient test (log-only), and the cycle's redrive commits the
    fence on its last attempt."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [ServiceUnavailable('503: backend unavailable')] * 3
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert blip_store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * 3


async def test_enforce_mode_raise_escapes_the_spawned_task(blip_store, monkeypatch, caplog):
    """Enforce mode must observe the raise (fail closed): the redrive contains
    it as a logged crash — the session stays alive and the boundary's own
    enforce semantics were already exercised one level down."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    blip_store.commit_errors = [PermissionDenied('enforce refuses')]
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
        controller.note_audio_activity()
        await asyncio.gather(*host.spawned)

    crash_records = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert len(crash_records) == 1
    assert host.waits == []


async def test_enforce_mode_blip_writes_nothing(blip_store, monkeypatch):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    before = copy.deepcopy(blip_store.documents[('users', 'uid', 'recording_sessions', 'session')])
    blip_store.commit_errors = [PermissionDenied('enforce refuses')]
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert blip_store.documents[('users', 'uid', 'recording_sessions', 'session')] == before


async def test_enforce_mode_clean_renewal_still_advances(blip_store, monkeypatch):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert blip_store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert host.waits == []


async def test_exhausted_budget_reports_false_with_the_fence_untouched(blip_store, monkeypatch):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 12
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert blip_store.documents[path]['lease_expires_at'] == (
        datetime(2026, 10, 22, 15, tzinfo=timezone.utc) + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * RECORDING_SESSION_LEASE_RETRY_ATTEMPTS


async def test_exhausted_budget_makes_exactly_four_attempts(blip_store, monkeypatch):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 12
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    # Every attempt — the first and all three redrives — burned its three
    # internal fresh-id restarts against the 12 queued retirements: four
    # attempts, three transaction opens each.
    assert host.store.transaction_opens == (1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS) * 3


async def test_exhausted_budget_logs_transient_warnings_not_crashes(blip_store, monkeypatch, caplog):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 12
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    with caplog.at_level(logging.WARNING):
        controller.note_audio_activity()
        await asyncio.gather(*host.spawned)

    transient = [r for r in caplog.records if 'lease renewal contended' in r.getMessage()]
    crash = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert len(transient) == 1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS
    assert crash == []


async def test_exhausted_budget_next_minute_retries_fresh(blip_store, monkeypatch):
    """Exhaustion is per cycle: the next audio-activity minute arms a new
    four-attempt cycle from scratch."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 12
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    clock.advance(minutes=1)
    blip_store.commit_errors = []
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert blip_store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


async def test_idle_session_arms_nothing_without_audio_activity(blip_store):
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    host = _RenewalHost(blip_store, clock)
    host.state.current_conversation_id = None
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.sleep(0)

    assert host.spawned == []
    assert host.waits == []
    path = ('users', 'uid', 'recording_sessions', 'session')
    assert blip_store.documents[path]['lease_expires_at'] == (
        clock.value.replace(hour=15, minute=0) + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


async def test_committed_fence_is_in_the_future_after_convergence(blip_store, monkeypatch):
    """The property SERVER_RECOVERY admission actually checks
    (``lease_expires_at > now``) holds after a redriven convergence — the redriven
    commit is a real fence, not just a row update."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 3
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert blip_store.documents[path]['lease_expires_at'] > clock.value


async def test_two_clean_minutes_keep_advancing_the_fence(blip_store, monkeypatch):
    """Consecutive healthy minutes stay wait-free while the fence holds: a
    floor-depleted minute writes, the next minute verifies read-only, and the
    controller-side bookkeeping stays out of the healthy path entirely."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    # A fence at the floor makes the first clean minute a real write; the
    # runway skip then holds the fresh fence without a second lock.
    blip_store.documents[('users', 'uid', 'recording_sessions', 'session')]['lease_expires_at'] = blip_store.documents[
        ('users', 'uid', 'recording_sessions', 'session')
    ]['lease_expires_at'] - timedelta(minutes=4)
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    path = ('users', 'uid', 'recording_sessions', 'session')
    written_fence = blip_store.documents[path]['lease_expires_at']

    clock.advance(minutes=1)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    # The skip keeps the written fence: still a future fence, never decayed.
    assert blip_store.documents[path]['lease_expires_at'] == written_fence
    assert blip_store.documents[path]['lease_expires_at'] > clock.value
    assert host.waits == []


async def test_identity_refusal_false_costs_reads_only_then_converges(blip_store, monkeypatch):
    """The identity/phase fence's refusal False never writes; the redrive
    converges to the same refusal without corrupting the row."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    before = copy.deepcopy(blip_store.documents[('users', 'uid', 'recording_sessions', 'session')])
    host = _RenewalHost(blip_store, clock)
    host.recording_session_id = 'ghost'
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert blip_store.documents[('users', 'uid', 'recording_sessions', 'session')] == before
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * RECORDING_SESSION_LEASE_RETRY_ATTEMPTS


async def test_terminal_phase_refusal_false_converges_to_the_fence_refusal(blip_store, monkeypatch):
    """A completed session (another flow finished it) refuses every attempt —
    the redrive neither resurrects it nor errors; the row stays terminal."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    path = ('users', 'uid', 'recording_sessions', 'session')
    blip_store.documents[path]['lifecycle_phase'] = 'completed'
    before = copy.deepcopy(blip_store.documents[path])
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert blip_store.documents[path] == before
    assert blip_store.documents[path]['lifecycle_phase'] == 'completed'
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * RECORDING_SESSION_LEASE_RETRY_ATTEMPTS


async def test_wake_between_attempts_resumes_a_fresh_cycle_next_minute(blip_store, monkeypatch):
    """A shutdown wake ends the current cycle, but the next audio-activity
    minute arms a fresh one that commits — the wake is per-cycle, not a
    permanent mute."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 3
    host = _RenewalHost(blip_store, clock)
    host.wait_returns = [True]  # the first wait wakes for shutdown
    controller = LiveConversationController(host, clock=clock)

    path = ('users', 'uid', 'recording_sessions', 'session')
    controller.note_audio_activity()  # first cycle: False, then the wake ends it
    await asyncio.gather(*host.spawned)
    assert len(host.waits) == 1

    clock.advance(minutes=1)
    controller.note_audio_activity()  # fresh cycle: healthy commit
    await asyncio.gather(*host.spawned)
    assert blip_store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


async def test_enforce_mode_availability_blip_writes_nothing_and_crashes_once(blip_store, monkeypatch, caplog):
    """The availability set raises through enforce exactly like contention: the
    fail-closed row stays byte-identical and the containment logs once."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    path = ('users', 'uid', 'recording_sessions', 'session')
    before = copy.deepcopy(blip_store.documents[path])
    blip_store.commit_errors = [ServiceUnavailable('503: backend unavailable')]
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
        controller.note_audio_activity()
        await asyncio.gather(*host.spawned)

    assert blip_store.documents[path] == before
    crash_records = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert len(crash_records) == 1


async def test_exhausted_cycle_then_blipped_minute_then_clean_commit(blip_store, monkeypatch):
    """Three minutes of a degrading data plane: exhausted cycle, another
    exhausted cycle, then commit — every minute re-attempts from scratch, so
    recovery needs no reconnect."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * (
        12 * 2
    )  # two full exhausted cycles: 4 attempts x 3 internal restarts each
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)
    path = ('users', 'uid', 'recording_sessions', 'session')

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    assert blip_store.documents[path]['lease_expires_at'] == datetime(2026, 10, 22, 15, 5, tzinfo=timezone.utc)

    clock.advance(minutes=1)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    assert blip_store.documents[path]['lease_expires_at'] == datetime(2026, 10, 22, 15, 5, tzinfo=timezone.utc)

    clock.advance(minutes=1)
    blip_store.commit_errors = []
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    assert blip_store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


async def test_throttle_bounds_cycles_during_exhaustion(blip_store, monkeypatch):
    """Even a fully failing plane gets at most one cycle per audio minute:
    activity inside the in-flight cycle spawns nothing new."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    blip_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 24
    host = _RenewalHost(blip_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    in_flight = host.spawned[-1]
    clock.advance(seconds=30)
    controller.note_audio_activity()

    assert host.spawned == [in_flight]
    await asyncio.gather(*host.spawned)
    assert host.store.transaction_opens == (1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS) * 3


# ── Mode pins ────────────────────────────────────────────────────────────────


def test_shadow_mode_still_the_default():
    assert lifecycle_service.recording_session_mode() == 'dual_write'


# ── Source and doc contract pins ─────────────────────────────────────────────


def test_doc_pins_the_redrive_cadence():
    doc = _DOC.read_text(encoding='utf-8')
    assert 'The\ncontroller now redrives a failed renewal inside the same cycle: a 15-second\n`host.wait`' in doc


def test_doc_pins_the_redrive_attempt_budget():
    doc = _DOC.read_text(encoding='utf-8')
    assert 'at most\nthree redrive attempts, so the whole schedule stays inside one\nonce-per-minute window' in doc


def test_doc_pins_the_cycle_end_conditions():
    doc = _DOC.read_text(encoding='utf-8')
    assert (
        'A committed renewal (True), a raise contained with\n'
        '`recording session lease renewal redrive crashed`, and a shutdown wake\n'
        'between attempts each end the cycle'
    ) in doc


def test_doc_pins_the_unbounded_loop_bound():
    doc = _DOC.read_text(encoding='utf-8')
    assert (
        'a permanently\n'
        'unavailable data plane still costs at most four renewal attempts per\n'
        'audio-activity minute, never an unbounded loop'
    ) in doc


def test_doc_pins_audio_activity_as_the_only_trigger():
    doc = _DOC.read_text(encoding='utf-8')
    assert 'an idle session still\narms nothing at all — audio activity remains the only trigger' in doc


def test_source_spawns_the_redrive_coroutine():
    src = _SOURCE.read_text(encoding='utf-8')
    assert 'self._renew_recording_session_lease_with_redrive(' in src
    assert "name='recording_session_lease_renewal'" in src


def test_source_waits_through_the_host_shutdown_event():
    src = _SOURCE.read_text(encoding='utf-8')
    assert 'await self.host.wait(RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS)' in src


def test_source_contains_the_cycle_in_one_helper():
    src = _SOURCE.read_text(encoding='utf-8')
    assert 'async def _renew_recording_session_lease_with_redrive(' in src
    helper_count = src.count('_renew_recording_session_lease_with_redrive')
    assert helper_count == 2  # the definition and the single spawn call
