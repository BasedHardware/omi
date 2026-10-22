"""A failed lease renewal must redrive inside its minute, not decay the fence.

Failure-Class: FC-failed-renewal-cadence-decays-live-fence (new class declared
in this diff). The controller's ``note_audio_activity`` armed its once-per-minute
throttle BEFORE spawning the renewal and discarded the renewal's result, so a
renewal that reported False — the transient arm: a drained contention burst, a
retired transaction id, a data-plane blip; the write layer wrote nothing — had
no retry until the NEXT audio activity after the minute boundary. Each blipped
minute therefore decayed ``lease_expires_at`` for its full interval while audio
still flowed; five consecutive blipped minutes expire the fence entirely and
SERVER_RECOVERY admission
(``_has_active_recording_session_lease``: ``lease_expires_at > now``) stops
refusing, re-admitting and re-finalizing a conversation a live socket still
owns. The write-layer fixes (the shared contention budget, the retired-id
restart, the availability-transient classification) only made those failures
quiet — they did not shorten the decay. A committed renewal (True) is
accounted exactly as before, the cadence bound keeps a permanently unavailable
data plane from turning one audio frame into an unbounded loop, and a shutdown
wake during a redrive wait ends the cycle instead of writing into a draining
session.

Guards:
- a False renewal redrives on the short in-cycle cadence — the fence is
  re-driven within the same minute instead of waiting for the next audio
  activity after the minute boundary;
- the throttle still caps spawned cycles at one per minute of audio activity,
  including activity landing while an earlier cycle's redrive is in flight;
- the redrive stays inside the spawned task: a raise (enforce mode, structural
  failure) is contained and logged with the session identity, never kills the
  session, and never consumes the wait budget;
- the wait schedule is bounded (attempt budget, no sleep after the final
  attempt), every wait is the short redrive delay, and a shutdown wake ends the
  cycle without its remaining attempts;
- every classified transient (contention exhaustion, the retired-id envelope,
  an availability blip) redrives identically — the controller consumes the
  classifier's verdict, it does not re-derive it;
- end to end against the real lifecycle boundary over fake Firestore: expired-id
  rejections and availability blips classified by the shared transient test
  converge to a committed renewal that advances ``lease_expires_at`` by the full
  duration, a converged cycle is a clean no-op to redrive again, and an idle
  session cannot arm a cycle because audio activity is the only thing that does.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import InvalidArgument, PermissionDenied, ServiceUnavailable

from database import recording_sessions
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from routers.listen.conversations import (
    RECORDING_SESSION_LEASE_RENEW_INTERVAL,
    RECORDING_SESSION_LEASE_RETRY_ATTEMPTS,
    RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS,
    LiveConversationController,
)
from utils.conversations import lifecycle as lifecycle_service

_LOGGER_NAME = 'routers.listen.conversations'
_RENEWAL = 'renew_live_recording_session_lease'


# ── Fixtures: a controller host that records, not runs ───────────────────────


class _Clock:
    """Controllable wall clock for the controller's once-per-minute throttle."""

    def __init__(self, start: datetime) -> None:
        self.value = start

    def __call__(self) -> datetime:
        return self.value

    def advance(self, **kwargs: Any) -> datetime:
        self.value = self.value + timedelta(**kwargs)
        return self.value


class _RedriveHost:
    """Records spawned tasks, persistence calls, and wait calls."""

    def __init__(self, results: list[Any], clock: _Clock) -> None:
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

    async def _call(self, fn, *args, **kwargs):
        self.calls.append((fn.__name__, args))
        result = self._results.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    def spawn(self, coro, *, name: str):
        self.spawned.append(asyncio.create_task(coro, name=name))
        return self.spawned[-1]

    async def wait(self, seconds: float) -> bool:
        self.waits.append(seconds)
        if self.wait_returns:
            return self.wait_returns.pop(0)
        return False

    def queue_result(self, result: Any) -> None:
        """Queue the next persistence result (a renewal bool or a raise)."""
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


# ── Cadence constants: the contract the fence math hangs on ─────────────────


def test_retry_delay_is_fifteen_seconds():
    assert RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS == 15.0


def test_retry_attempt_budget_is_three():
    assert RECORDING_SESSION_LEASE_RETRY_ATTEMPTS == 3


def test_renew_interval_stays_one_minute():
    assert RECORDING_SESSION_LEASE_RENEW_INTERVAL == timedelta(minutes=1)


def test_lease_duration_stays_five_minutes():
    assert recording_sessions.RECORDING_SESSION_LEASE_DURATION == timedelta(minutes=5)


def test_redrive_cycle_fits_inside_one_renew_interval():
    """Four attempts spaced 15s apart fit inside the once-per-minute window, so
    a redriving cycle can never overlap the next audio-activity cycle."""
    span = RECORDING_SESSION_LEASE_RETRY_ATTEMPTS * RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS
    assert span < RECORDING_SESSION_LEASE_RENEW_INTERVAL.total_seconds()


def test_five_blipped_minutes_exactly_exhaust_the_fence():
    """The damage statement: five consecutive unredriven minutes equal the full
    lease duration — the re-admission boundary the redrive removes."""
    assert 5 * RECORDING_SESSION_LEASE_RENEW_INTERVAL == recording_sessions.RECORDING_SESSION_LEASE_DURATION


# ── Arming guards: audio activity is the only trigger ────────────────────────


async def test_first_activity_spawns_one_named_renewal_task():
    host, _ = _blipped_host(blips=0)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert [task.get_name() for task in host.spawned] == ['recording_session_lease_renewal']


async def test_missing_conversation_id_arms_nothing():
    host, _ = _blipped_host(blips=0)
    host.state.current_conversation_id = None
    _controller(host).note_audio_activity()
    await asyncio.sleep(0)

    assert host.spawned == []
    assert host.calls == []


async def test_missing_recording_session_arms_nothing():
    host, _ = _blipped_host(blips=0)
    host.recording_session_id = None
    _controller(host).note_audio_activity()
    await asyncio.sleep(0)

    assert host.spawned == []
    assert host.calls == []


async def test_empty_conversation_id_arms_nothing():
    host, _ = _blipped_host(blips=0)
    host.state.current_conversation_id = ''
    _controller(host).note_audio_activity()
    await asyncio.sleep(0)

    assert host.spawned == []


async def test_empty_recording_session_arms_nothing():
    host, _ = _blipped_host(blips=0)
    host.recording_session_id = ''
    _controller(host).note_audio_activity()
    await asyncio.sleep(0)

    assert host.spawned == []


async def test_activity_inside_the_interval_window_does_not_spawn():
    host, clock = _blipped_host(blips=0)
    controller = _controller(host)
    controller.note_audio_activity()
    clock.advance(seconds=59)
    controller.note_audio_activity()
    await _drain(host)

    assert len(host.spawned) == 1


async def test_activity_at_exactly_the_interval_boundary_spawns():
    host, clock = _blipped_host(blips=0)
    controller = _controller(host)
    controller.note_audio_activity()
    await _drain(host)
    clock.advance(minutes=1)
    controller.note_audio_activity()
    await _drain(host)

    assert len(host.spawned) == 2


async def test_second_cycle_passes_the_current_session_identity():
    """A rollover between cycles must be picked up: the second cycle renews the
    NEW conversation binding, not a stale first-cycle snapshot."""
    host, clock = _blipped_host(blips=0)
    controller = _controller(host)
    controller.note_audio_activity()
    await _drain(host)

    host.state.current_conversation_id = 'conversation-two'
    host.recording_session_id = 'session-two'
    clock.advance(minutes=1)
    controller.note_audio_activity()
    await _drain(host)

    assert host.calls[-1] == (_RENEWAL, ('uid', 'session-two', 'conversation-two'))


# ── Throttle discipline under an in-flight redrive ──────────────────────────


async def test_throttle_spawns_at_most_one_cycle_per_minute():
    host, clock = _blipped_host(blips=2)
    controller = _controller(host)
    controller.note_audio_activity()
    first_cycle = host.spawned[-1]

    clock.advance(seconds=30)
    controller.note_audio_activity()
    assert host.spawned == [first_cycle], 'in-flight redrive must not admit another cycle'

    clock.advance(seconds=31)
    controller.note_audio_activity()
    assert len(host.spawned) == 2, 'the minute boundary re-arms the cycle'
    await _drain(host)


async def test_inflight_redrive_wait_does_not_arm_a_second_cycle():
    """The redrive's 15s waits are inside the throttle window: activity during
    them is a no-op even though the first cycle is only sleeping."""
    host, clock = _blipped_host(blips=1)
    controller = _controller(host)
    controller.note_audio_activity()
    in_flight = host.spawned[-1]

    clock.advance(seconds=RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS)
    controller.note_audio_activity()

    assert host.spawned == [in_flight]
    await _drain(host)


async def test_second_cycle_starts_from_its_own_spawn_minute():
    """An arm inside the window is a free no-op that does NOT re-anchor the
    window: the next cycle opens one minute after the previous SPAWN, so a
    chatty session cannot push its fence renewals later and later."""
    host, clock = _blipped_host(blips=0)
    controller = _controller(host)
    controller.note_audio_activity()
    await _drain(host)

    clock.advance(seconds=45)
    controller.note_audio_activity()  # inside the window: consumed, no spawn, no re-anchor
    clock.advance(seconds=16)  # 61s after the first spawn
    controller.note_audio_activity()

    assert len(host.spawned) == 2, 'the window opens from the first spawn, not the in-window arm'
    await _drain(host)


# ── Cycle ends: success, containment, bounded waits, shutdown wake ───────────


async def test_failed_renewal_redrives_within_the_same_minute():
    """A False (transient) renewal is re-driven inside the cycle on the short
    cadence — not deferred to the next audio activity after the minute
    boundary, which is the fence decay the write layer could not fix."""
    host, _ = _blipped_host(blips=1)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_committed_renewal_ends_the_cycle_without_waits():
    """The healthy path keeps the old shape: one spawned renewal, no waits."""
    host, _ = _blipped_host(blips=0)
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == []
    assert len(host.calls) == 1


async def test_permanent_rejection_is_contained_and_consumes_no_waits(caplog):
    """A raise through the renewal (enforce mode, or any structural failure)
    must be contained inside the spawned task: logged once with the session
    identity, no wait schedule consumed, no escape to the task supervisor."""
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
    """A raise on a LATER attempt ends the cycle: no further waits, no further
    renewals after the crash — the schedule is not resumed. (The controller
    sees the classifier's verdict, so a structural raise arrives exactly this
    way: the persistence layer itself raising beneath the boundary.)"""
    host = _RedriveHost([], _clock_at())
    host.queue_result(False)
    host.queue_result(RuntimeError('persistence executor died'))
    controller = _controller(host)
    controller.note_audio_activity()

    with caplog.at_level(logging.ERROR, logger=_LOGGER_NAME):
        await _drain(host)

    assert len(host.calls) == 2
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]
    crash_records = [r for r in caplog.records if 'redrive crashed' in r.getMessage()]
    assert len(crash_records) == 1


async def test_redrive_waits_are_bounded_and_short():
    """The wait schedule is exactly the attempt budget's short delays — never
    the full minute, and never a sleep after the final attempt."""
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
    assert RECORDING_SESSION_LEASE_RENEW_INTERVAL.total_seconds() not in host.waits


async def test_full_redrive_exhaustion_stops_without_one_more_renewal():
    """The attempt budget is final: exactly four renewals for a session that
    stays down — the bound that keeps a dead data plane from looping."""
    host = _RedriveHost([False] * (1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS), _clock_at())
    _controller(host).note_audio_activity()
    await _drain(host)

    assert len(host.calls) == 1 + RECORDING_SESSION_LEASE_RETRY_ATTEMPTS
    assert len(host.waits) == RECORDING_SESSION_LEASE_RETRY_ATTEMPTS


async def test_shutdown_wake_during_a_wait_ends_the_cycle():
    """A shutdown wake between attempts means teardown began: the cycle ends
    without writing one more lease renewal into a draining session."""
    host, _ = _blipped_host(blips=2)
    host.wait_returns = [True]  # the first wait wakes for shutdown
    _controller(host).note_audio_activity()
    await _drain(host)

    assert len(host.calls) == 1
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_shutdown_wake_on_the_last_wait_skips_the_final_attempt():
    """A wake on the LAST inter-attempt wait skips the final attempt: the
    redrive never writes into a session that already began shutting down, and
    the next audio activity starts a fresh cycle. Two committed False-shaped
    attempts before the wake show the schedule itself stays intact."""
    host, _ = _blipped_host(blips=RECORDING_SESSION_LEASE_RETRY_ATTEMPTS)
    host.wait_returns = [False, True]
    _controller(host).note_audio_activity()
    await _drain(host)

    assert len(host.calls) == 2
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * 2


# ── Every classified transient redrives identically ─────────────────────────
#
# The controller consumes the lifecycle classifier's verdict — it never sees a
# raw provider exception. These queue the verdict (False) each shape produces
# after the write layer and classifier run, so what is pinned here is the
# controller's own contract: every False is the decay signal, whatever shape
# produced it.


async def test_classified_transient_false_redrives():
    host = _RedriveHost([False, True], _clock_at())
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_mixed_transient_shapes_share_one_schedule():
    """Two classified transients, then commit: one bounded schedule across the
    shapes — the controller never re-classifies."""
    host = _RedriveHost([False, False, True], _clock_at())
    _controller(host).note_audio_activity()
    await _drain(host)

    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * 2
    assert len(host.calls) == 3


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
    firestore: '_ExpiredIdFirestore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.firestore.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.firestore, self.path + (name,))


@dataclass
class _CollectionRef:
    firestore: '_ExpiredIdFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.firestore, self.path + (document_id,))


@dataclass
class _Transaction:
    firestore: '_ExpiredIdFirestore'

    def create(self, document: _DocumentRef, data: dict[str, Any]) -> None:
        if document.path in self.firestore.documents:
            raise RuntimeError('already exists')
        self.firestore.documents[document.path] = copy.deepcopy(data)

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.firestore.documents[document.path].update(copy.deepcopy(updates))


class _ExpiredIdFirestore:
    """Fake Firestore that rejects the renewal's first commits with a queued
    error, then serves the real document."""

    def __init__(self) -> None:
        self.documents: dict[tuple[str, ...], dict[str, Any]] = {}
        self.commit_errors: list[BaseException] = []

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        return _Transaction(self)


class _RenewalHost:
    """Drives the controller's real redrive task against the real lifecycle
    renewal over a fake Firestore, with an event-loop-free wait seam."""

    def __init__(self, store: _ExpiredIdFirestore, clock: _Clock) -> None:
        self.request = SimpleNamespace(uid='uid')
        self.state = SimpleNamespace(current_conversation_id='conversation')
        self.recording_session_id = 'session'
        self.clock = clock
        self.store = store
        self.waits: list[float] = []
        self.spawned: list[asyncio.Task] = []
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
        return False


def _seed_session_row(store: _ExpiredIdFirestore, started_at: datetime) -> None:
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
def expired_id_store(monkeypatch):
    store = _ExpiredIdFirestore()
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


async def test_redriven_renewal_advances_the_durable_fence(expired_id_store, monkeypatch):
    """Expired-id rejections inside the cycle converge to a committed renewal
    that moves ``lease_expires_at`` by the full duration — before the fix the
    whole False cycle decayed the fence for the rest of the minute."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    # Three retirements exhaust run_transactional's internal fresh-id restarts,
    # so the retirement surfaces at the lifecycle boundary as the classified
    # transient (False) — the exact decay signal the redrive exists for. The
    # cycle's second attempt then commits on a clean data plane.
    expired_id_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 3
    host = _RenewalHost(expired_id_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert expired_id_store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_converged_cycle_redrives_to_a_clean_no_op(expired_id_store, monkeypatch):
    """A second cycle over an already-committed fence renews again without
    waiting: idempotent per minute, never stuck because a fence moved once."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    expired_id_store.commit_errors = [InvalidArgument('400 The referenced transaction has expired')] * 3
    host = _RenewalHost(expired_id_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    path = ('users', 'uid', 'recording_sessions', 'session')
    first_commit = expired_id_store.documents[path]['lease_expires_at']

    clock.advance(minutes=1)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert expired_id_store.documents[path]['lease_expires_at'] == (first_commit + timedelta(minutes=1))
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS]


async def test_availability_blip_converges_through_the_shared_classifier(expired_id_store, monkeypatch):
    """A data-plane 503 exhausts the write layer untouched, is classified by
    the shared transient test (log-only, t171), and the cycle's redrive
    commits the fence on its last attempt (t177 cadence feeding on the t171
    classification)."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    expired_id_store.commit_errors = [ServiceUnavailable('503: backend unavailable')] * 3
    host = _RenewalHost(expired_id_store, clock)
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    path = ('users', 'uid', 'recording_sessions', 'session')
    assert expired_id_store.documents[path]['lease_expires_at'] == (
        clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert host.waits == [RECORDING_SESSION_LEASE_RETRY_DELAY_SECONDS] * 3


async def test_idle_session_arms_nothing_without_audio_activity(expired_id_store):
    """Audio activity is the only thing that arms a cycle: an idle session
    (or one before its conversation binding exists) spawns no renewals and its
    fence decays exactly as designed."""
    clock = _Clock(datetime(2026, 10, 22, 15, 30, tzinfo=timezone.utc))
    host = _RenewalHost(expired_id_store, clock)
    host.state.current_conversation_id = None
    controller = LiveConversationController(host, clock=clock)

    controller.note_audio_activity()
    await asyncio.sleep(0)

    assert host.spawned == []
    assert host.waits == []
    path = ('users', 'uid', 'recording_sessions', 'session')
    assert expired_id_store.documents[path]['lease_expires_at'] == (
        clock.value.replace(hour=15, minute=0) + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
