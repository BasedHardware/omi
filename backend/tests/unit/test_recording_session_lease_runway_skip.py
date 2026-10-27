"""A redundant lease renewal must not lock the document it only reads.

Failure-Class: FC-lease-renewal-locks-the-document-it-only-reads
(new class declared in this diff; the nearest existing classes cover the
neighbouring shapes — FC-renewal-lease-write-aborted-as-failed-write covers
the contention/retry layer added 2026-10-16, FC-retired-transaction-treated-as-
fatal covers the expired-id commit, and FC-expired-transaction-id-kills-single-
minted-transactional-writer covers the users-transaction family — none of them
covers the self-inflicted write volume: the renewal itself re-stamped its own
five-minute fence every renewal minute, so roughly four of every five renewal
transactions took a read+write lock on the session document only to rewrite
the value the previous renewal had just written.)

Guards:
- a renewal whose fence still has more than
  ``RECORDING_SESSION_LEASE_RUNWAY_FLOOR`` of runway commits read-only: True,
  no ``transaction.update``, fence and ``updated_at`` untouched;
- the skip is read-through-the-transaction (never a bare get), survives the
  expired-transaction restart, and still runs on the named contention budget;
- the boundary is exact: a fence at or below the floor writes the full
  duration again, so blackout immunity and the wall-clock semantics the
  recovery sweep reads are unchanged;
- a steady 25-minute recording converges from one fence write per minute to
  one per floor+interval minutes while every cycle still reports True;
- the skip logs INFO with the remaining runway and never a WARNING/ERROR or
  ``omi_fallback_total`` degradation event;
- the recovery sweep's in-transaction lease guard keeps refusing while the
  skipped-to fence is unexpired, and admits again once wall-clock time decays
  it — the guard reads the fence, never the renewal's write history;
- enforce mode keeps raising real failures and treats the skip as success.
"""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument, PermissionDenied

from database import conversation_finalization_jobs as jobs_db
from database import recording_sessions
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from routers.listen.conversations import LiveConversationController
from utils.conversations import lifecycle as lifecycle_service

_LOGGER_NAME = 'database.recording_sessions'
_LIFECYCLE_LOGGER_NAME = 'utils.conversations.lifecycle'
_EXPIRED_ID_MESSAGE = '400 The referenced transaction has expired or is no longer valid'
_SESSION_PATH = ('users', 'uid', 'recording_sessions', 'session')


# ── Fake Firestore ───────────────────────────────────────────────────────────


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
    store: '_RunwayFirestore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.store.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.store, self.path + (name,))


@dataclass
class _CollectionRef:
    store: '_RunwayFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.store, self.path + (document_id,))


@dataclass
class _Transaction:
    store: '_RunwayFirestore'

    def create(self, document: _DocumentRef, data: dict[str, Any]) -> None:
        self.store.updates.append({'path': document.path, 'data': copy.deepcopy(data)})
        if document.path in self.store.documents:
            raise RuntimeError('already exists')
        self.store.documents[document.path] = copy.deepcopy(data)

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.store.updates.append({'path': document.path, 'data': copy.deepcopy(updates)})
        self.store.documents[document.path].update(copy.deepcopy(updates))


@dataclass
class _RunwayFirestore:
    """Fake Firestore tracking every write so read-only commits are visible."""

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[BaseException] = field(default_factory=list)
    commit_errors: list[BaseException] = field(default_factory=list)
    commits: list[_Transaction] = field(default_factory=list)
    transactions: list[_Transaction] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    budget_calls: list[dict[str, Any]] = field(default_factory=list)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction


def _seed_session(
    store: _RunwayFirestore,
    *,
    started_at: datetime | None = None,
    remaining: timedelta | None = None,
    phase: str = 'in_progress',
    conversation_id: str = 'conversation',
) -> datetime:
    """Seed the session row; ``remaining`` pins the fence relative to the clock."""
    now = started_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if remaining is None:
        lease_expires_at = now + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    else:
        lease_expires_at = now + remaining
    store.documents[_SESSION_PATH] = {
        'schema_version': recording_sessions.RECORDING_SESSION_SCHEMA_VERSION,
        'uid': 'uid',
        'recording_session_id': 'session',
        'conversation_id': conversation_id,
        'lifecycle_version': recording_sessions.LIFECYCLE_ENVELOPE_VERSION,
        'lifecycle_phase': phase,
        'lifecycle_sequence': 0,
        'created_at': now,
        'updated_at': now,
        'lease_expires_at': lease_expires_at,
    }
    return now


@pytest.fixture
def runway_store(monkeypatch):
    store = _RunwayFirestore()

    def transactional(func):
        def locked(transaction, *args, **kwargs):
            if store.read_errors:
                raise store.read_errors.pop(0)
            result = func(transaction, *args, **kwargs)
            if store.commit_errors:
                raise store.commit_errors.pop(0)
            store.commits.append(transaction)
            return result

        return locked

    monkeypatch.setattr(recording_sessions.firestore, 'transactional', transactional)

    def budget_retry(*a, **kw):
        store.budget_calls.append({'operation_name': kw.get('operation_name')})
        return run_with_transaction_contention_retry(*a, sleep=lambda _delay: None, random_value=lambda: 0, **kw)

    monkeypatch.setattr(recording_sessions, 'run_with_transaction_contention_retry', budget_retry)
    return store


# ── The skip itself ──────────────────────────────────────────────────────────


def test_fresh_fence_skips_the_write_and_reports_true(runway_store):
    """A fence the previous renewal just stamped is read-only re-verified."""
    _seed_session(runway_store)

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    assert runway_store.updates == []
    assert len(runway_store.commits) == 1


def test_skip_leaves_the_fence_and_updated_at_untouched(runway_store):
    started_at = _seed_session(runway_store)

    recording_sessions.renew_recording_session_lease('uid', 'session', 'conversation', firestore_client=runway_store)

    assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert runway_store.documents[_SESSION_PATH]['updated_at'] == started_at


def test_skip_still_reads_through_the_transaction(runway_store):
    """The runway read must stay transactional — never a bare outside-budget get."""
    _seed_session(runway_store)

    recording_sessions.renew_recording_session_lease('uid', 'session', 'conversation', firestore_client=runway_store)

    assert len(runway_store.transactions) == 1
    assert runway_store.budget_calls[0]['operation_name'] == 'recording_session_lease_renewal'


@pytest.mark.parametrize(
    'remaining,renews',
    [
        (timedelta(minutes=5), True),
        (timedelta(minutes=4), True),
        (timedelta(minutes=2, seconds=1), True),
        (timedelta(minutes=2), False),
        (timedelta(minutes=1), False),
        (timedelta(seconds=30), False),
        (timedelta(seconds=0), False),
        (timedelta(minutes=-1), False),
    ],
    ids=[
        'full_runway_skips',
        'four_minutes_skips',
        'just_above_floor_skips',
        'exactly_floor_writes',
        'one_minute_writes',
        'thirty_seconds_write',
        'expired_writes',
        'long_expired_writes',
    ],
)
def test_runway_floor_boundary_is_exact(runway_store, monkeypatch, remaining, renews):
    """Above the floor the write is redundant; at or below it the fence moves."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at, remaining=remaining)
    before = runway_store.documents[_SESSION_PATH]['lease_expires_at']

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    wrote = runway_store.updates != []
    assert wrote is (not renews)
    if renews:
        assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == before
    else:
        assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == (
            started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
        )


def test_skipped_renewal_after_a_contended_first_read(runway_store):
    """Contention replay lands on the read-only skip without writing."""
    _seed_session(runway_store)
    runway_store.read_errors = [Aborted('contention')]

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    assert runway_store.updates == []
    assert len(runway_store.commits) == 1


def test_skip_survives_the_expired_transaction_restart(runway_store):
    """A retired id on a skip's commit restarts and skips again — still no write."""
    from google.api_core.exceptions import InvalidArgument

    _seed_session(runway_store)
    runway_store.commit_errors = [InvalidArgument(_EXPIRED_ID_MESSAGE)]

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    assert runway_store.updates == []
    assert len(runway_store.commits) == 1
    assert len(runway_store.transactions) == 2


def test_blackout_minute_between_skips_writes_the_full_duration(runway_store, monkeypatch):
    """After a silent stretch the next renewal re-stamps from that instant."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at)

    # Skips hold the fence at started_at + 5m for two renewal minutes (runway
    # 4m and 3m both stay above the floor)...
    for offset in (1, 2):
        monkeypatch.setattr(recording_sessions, '_now', lambda offset=offset: started_at + timedelta(minutes=offset))
        assert (
            recording_sessions.renew_recording_session_lease(
                'uid', 'session', 'conversation', firestore_client=runway_store
            )
            is True
        )
    assert runway_store.updates == []

    # ...then wall-clock decay leaves 30s of runway and one write covers the
    # whole blackout with the full duration from *that* instant.
    blackout_end = started_at + timedelta(minutes=4, seconds=30)
    monkeypatch.setattr(recording_sessions, '_now', lambda: blackout_end)
    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    assert len(runway_store.updates) == 1
    assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        blackout_end + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_long_gap_writes_from_the_renewal_instant_not_elapsed_plus_duration(runway_store, monkeypatch):
    """A 40-minute gap must not leave the fence 40 minutes behind wall clock."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at, remaining=timedelta(seconds=0))
    gap_end = started_at + timedelta(minutes=40)
    monkeypatch.setattr(recording_sessions, '_now', lambda: gap_end)

    recording_sessions.renew_recording_session_lease('uid', 'session', 'conversation', firestore_client=runway_store)

    assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        gap_end + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_malformed_fence_writes_the_full_duration(runway_store, monkeypatch):
    """A fence the helper cannot read is treated as depleted: stamp it fresh."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at)
    runway_store.documents[_SESSION_PATH]['lease_expires_at'] = 'corrupt'

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    assert len(runway_store.updates) == 1
    assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_naive_stored_fence_skips_when_runway_sufficient(runway_store, monkeypatch):
    """Firestore stores naive datetimes; the skip must read them as UTC."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at)
    runway_store.documents[_SESSION_PATH]['lease_expires_at'] = started_at + timedelta(minutes=4)

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    assert runway_store.updates == []


# ── The write path keeps its refusals ────────────────────────────────────────


def test_depleted_fence_still_writes_the_full_duration(runway_store, monkeypatch):
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at, remaining=timedelta(minutes=1))

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    assert len(runway_store.updates) == 1
    assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert runway_store.documents[_SESSION_PATH]['updated_at'] == started_at


def test_phase_refusal_precedes_the_runway_skip(runway_store, monkeypatch):
    """A terminal phase refuses before the runway check can call it redundant."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at, phase='completed')

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is False
    assert runway_store.updates == []
    assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_depleted_terminal_refusal_still_refuses(runway_store, monkeypatch):
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at, remaining=timedelta(minutes=1), phase='completed')

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is False
    assert runway_store.updates == []


def test_identity_mismatch_refuses_under_full_runway(runway_store):
    _seed_session(runway_store)

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'other-conversation', firestore_client=runway_store
    )

    assert renewed is False
    assert runway_store.updates == []


def test_missing_session_stays_a_clean_no_op(runway_store):
    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'ghost', 'conversation', firestore_client=runway_store
    )

    assert renewed is False
    assert runway_store.updates == []
    assert ('users', 'uid', 'recording_sessions', 'ghost') not in runway_store.documents


# ── Observability ────────────────────────────────────────────────────────────


def test_skip_logs_info_with_runway_and_no_error(runway_store, monkeypatch, caplog):
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at)

    with caplog.at_level(logging.INFO):
        recording_sessions.renew_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=runway_store
        )

    skip_records = [record for record in caplog.records if record.name == _LOGGER_NAME]
    assert len(skip_records) == 1
    assert skip_records[0].levelname == 'INFO'
    assert 'nothing written' in skip_records[0].getMessage()
    assert 'runway_s=300' in skip_records[0].getMessage()


def test_skip_never_logs_warning_or_error(caplog, runway_store):
    _seed_session(runway_store)

    with caplog.at_level(logging.WARNING):
        recording_sessions.renew_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=runway_store
        )

    loud = [
        record for record in caplog.records if record.name == _LOGGER_NAME and record.levelname in {'WARNING', 'ERROR'}
    ]
    assert loud == []


def test_write_logs_no_runway_line(runway_store, monkeypatch, caplog):
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at, remaining=timedelta(minutes=1))

    with caplog.at_level(logging.INFO):
        recording_sessions.renew_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=runway_store
        )

    assert [record for record in caplog.records if 'runway' in record.getMessage()] == []


def test_runway_helper_rejects_a_missing_or_malformed_fence():
    assert recording_sessions._remaining_lease_runway({}, datetime.now(timezone.utc)) is None
    assert recording_sessions._remaining_lease_runway({'lease_expires_at': 'soon'}, datetime.now(timezone.utc)) is None


def test_runway_helper_positive_and_negative_deltas():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    future = recording_sessions._remaining_lease_runway({'lease_expires_at': now + timedelta(minutes=3)}, now)
    past = recording_sessions._remaining_lease_runway({'lease_expires_at': now - timedelta(minutes=3)}, now)
    assert future == timedelta(minutes=3)
    assert past == timedelta(minutes=-3)


def test_runway_helper_matches_its_transaction_body_contract():
    """The helper and the skip branch must agree on the exact floor compare."""
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    floor = recording_sessions.RECORDING_SESSION_LEASE_RUNWAY_FLOOR
    at_floor = recording_sessions._remaining_lease_runway({'lease_expires_at': now + floor}, now)
    assert at_floor is not None
    assert at_floor == floor
    # The branch writes on `> floor` being False, so exactly-at-floor writes.
    assert (at_floor > floor) is False


def test_runway_helper_normalizes_a_naive_stored_fence():
    now = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    runway = recording_sessions._remaining_lease_runway({'lease_expires_at': now.replace(tzinfo=None)}, now)
    assert runway == timedelta(seconds=0)


# ── The lifecycle boundary observes the skip as success ──────────────────────


def test_lifecycle_owner_propagates_the_skip_as_true(runway_store, caplog):
    """The boundary reports the skip as success: no traceback, no fallback."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(runway_store, started_at=started_at)

    renewed = lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    failed = [
        record for record in caplog.records if record.name == _LIFECYCLE_LOGGER_NAME and record.levelname == 'ERROR'
    ]
    assert failed == []


def test_lifecycle_owner_absorbs_a_real_failure_around_a_skip(runway_store, monkeypatch, caplog):
    """A genuine provider failure still lands in the failed-write arm, while
    the skip classification never widened it."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at)
    runway_store.read_errors = [PermissionDenied('permission denied on row')]

    with caplog.at_level(logging.ERROR, logger=_LIFECYCLE_LOGGER_NAME):
        refused = lifecycle_service.renew_live_recording_session_lease(
            'uid', 'session', 'conversation', firestore_client=runway_store
        )

    assert refused is False
    failed = [record for record in caplog.records if 'lease renewal failed' in record.getMessage()]
    assert len(failed) == 1


def test_skip_emits_no_omi_fallback_degradation_event(runway_store, monkeypatch):
    """The skip is success, never a degradation: record_fallback stays cold."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at)
    fallbacks: list[dict[str, Any]] = []
    monkeypatch.setattr(lifecycle_service, 'record_fallback', lambda **kw: fallbacks.append(kw))

    lifecycle_service.renew_live_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert fallbacks == []


# ── Steady-state convergence through the real controller ─────────────────────


class _Clock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def advance(self, **kwargs: Any) -> None:
        self.value = self.value + timedelta(**kwargs)


class _RunwayHost:
    """Drives the controller's real renewal task against the real adapter."""

    def __init__(self, store: _RunwayFirestore, clock: _Clock) -> None:
        self.request = SimpleNamespace(uid='uid')
        self.state = SimpleNamespace(current_conversation_id='conversation')
        self.recording_session_id = 'session'
        self.clock = clock
        self.store = store
        self.spawned: list[asyncio.Task] = []
        self.spawn_names: list[str] = []
        self.persistence = SimpleNamespace(call=self._call)

    async def _call(self, fn, *args, **kwargs):
        kwargs.setdefault('firestore_client', self.store)
        return fn(*args, **kwargs)

    def spawn(self, coro, *, name: str):
        self.spawn_names.append(name)
        self.spawned.append(asyncio.create_task(coro, name=name))
        return self.spawned[-1]


async def _run_minutes(controller: LiveConversationController, host: _RunwayHost, minutes: int) -> None:
    for _ in range(minutes):
        controller.note_audio_activity()
        await asyncio.gather(*host.spawned)
        host.spawned.clear()
        host.clock.advance(minutes=1)


@pytest.mark.asyncio
async def test_twenty_five_minute_recording_writes_once_per_floor_plus_interval(runway_store, monkeypatch):
    """Steady state: the fence write lands once per floor+interval, not per minute."""
    clock = _Clock(datetime(2026, 10, 27, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation', firestore_client=runway_store)
    runway_store.updates.clear()
    host = _RunwayHost(runway_store, clock)
    controller = LiveConversationController(host, clock=lambda: clock.value)

    await _run_minutes(controller, host, 25)

    # Writes land every floor+interval minutes (3, 6, ... 24) once the initial
    # full-duration fence decays to the floor — 8 writes instead of 25.
    assert len(runway_store.updates) == 8
    final_fence = runway_store.documents[_SESSION_PATH]['lease_expires_at']
    assert final_fence > clock.value


@pytest.mark.asyncio
async def test_every_skip_cycle_still_reports_true_without_redrive_waits(runway_store, monkeypatch):
    """A skipped renewal is success: the redrive schedule never arms."""
    clock = _Clock(datetime(2026, 10, 27, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    waits: list[float] = []

    async def wait(seconds: float) -> bool:
        waits.append(seconds)
        await asyncio.sleep(0)
        return False

    recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation', firestore_client=runway_store)
    runway_store.updates.clear()
    host = _RunwayHost(runway_store, clock)
    host.wait = wait  # type: ignore[method-assign]
    controller = LiveConversationController(host, clock=lambda: clock.value)

    await _run_minutes(controller, host, 4)

    assert host.spawn_names == ['recording_session_lease_renewal'] * 4
    assert waits == []
    # One write on the boundary minute (runway exactly at the floor), the
    # rest skipped — the redrive schedule stayed silent throughout.
    assert len(runway_store.updates) == 1


@pytest.mark.asyncio
async def test_transient_then_skip_converges_without_spurious_redrive(runway_store, monkeypatch):
    """After a redriven write the next cycle's skip must not re-arm waits."""
    clock = _Clock(datetime(2026, 10, 27, 12, tzinfo=timezone.utc))
    monkeypatch.setattr(recording_sessions, '_now', lambda: clock.value)
    waits: list[float] = []

    async def wait(seconds: float) -> bool:
        waits.append(seconds)
        await asyncio.sleep(0)
        return False

    recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation', firestore_client=runway_store)
    runway_store.updates.clear()
    runway_store.commit_errors = [InvalidArgument(_EXPIRED_ID_MESSAGE)]
    host = _RunwayHost(runway_store, clock)
    host.wait = wait  # type: ignore[method-assign]
    controller = LiveConversationController(host, clock=lambda: clock.value)

    # Cycle 1: the expired-id commit restarts, then writes the full duration
    # against the fresh-open fence (runway 5m > floor at the write instant).
    # No False ever surfaced, so the redrive schedule never armed.
    runway_store.documents[_SESSION_PATH]['lease_expires_at'] = clock.value - timedelta(minutes=4)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    host.spawned.clear()
    first_fence = runway_store.documents[_SESSION_PATH]['lease_expires_at']
    assert first_fence == clock.value + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    assert waits == []

    # Cycles 2-3: full runway after the write — pure skips, still no waits.
    clock.advance(minutes=1)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)
    host.spawned.clear()
    clock.advance(minutes=1)
    controller.note_audio_activity()
    await asyncio.gather(*host.spawned)

    assert waits == []
    assert len(runway_store.updates) == 1  # the transient-recovered write only


# ── The recovery sweep reads the fence, not the write history ────────────────


def _conversation_with_marker(recording_session_id: str) -> dict[str, Any]:
    return {'status': 'in_progress', 'external_data': {'recording_session_id': recording_session_id}}


def test_sweep_guard_still_refused_while_the_skipped_fence_holds(runway_store):
    _seed_session(runway_store)
    collection = runway_store.collection('users').document('uid').collection('recording_sessions')

    guarded = jobs_db._has_active_recording_session_lease(
        None,
        collection,
        'uid',
        'conversation',
        _conversation_with_marker('session'),
        datetime.now(timezone.utc),
    )

    assert guarded is True


def test_sweep_guard_admits_once_wall_clock_decays_the_fence(runway_store, monkeypatch):
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(runway_store, started_at=started_at)
    collection = runway_store.collection('users').document('uid').collection('recording_sessions')
    now = started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION + timedelta(seconds=1)

    guarded = jobs_db._has_active_recording_session_lease(
        None,
        collection,
        'uid',
        'conversation',
        _conversation_with_marker('session'),
        now,
    )

    assert guarded is False


def test_sweep_guard_refuses_again_after_the_post_blackout_write(runway_store, monkeypatch):
    """Skips never consume the fence: one write after a gap re-arms the guard."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at, remaining=timedelta(seconds=0))
    collection = runway_store.collection('users').document('uid').collection('recording_sessions')
    conversation = _conversation_with_marker('session')

    expired = jobs_db._has_active_recording_session_lease(
        None, collection, 'uid', 'conversation', conversation, started_at + timedelta(seconds=1)
    )
    recording_sessions.renew_recording_session_lease('uid', 'session', 'conversation', firestore_client=runway_store)
    guarded = jobs_db._has_active_recording_session_lease(
        None, collection, 'uid', 'conversation', conversation, started_at + timedelta(seconds=1)
    )

    assert expired is False
    assert guarded is True


# ── Enforce mode and budget pins ─────────────────────────────────────────────


def test_enforce_mode_skips_read_only_and_still_writes_depleted(runway_store, monkeypatch):
    """Enforce gates failure propagation, not the runway skip itself."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)

    _seed_session(runway_store, started_at=started_at)
    skipped = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )
    _seed_session(runway_store, started_at=started_at, remaining=timedelta(minutes=1))
    written = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert skipped is True
    assert written is True
    assert len(runway_store.updates) == 1


def test_skip_and_write_share_one_budget_attempt_shape(runway_store, monkeypatch):
    """The skip never widens the attempt budget: one clean open, one commit."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at)

    recording_sessions.renew_recording_session_lease('uid', 'session', 'conversation', firestore_client=runway_store)

    assert len(runway_store.budget_calls) == 1
    assert len(runway_store.transactions) == 1
    assert len(runway_store.commits) == 1


def test_depleted_write_rides_the_write_side_budget_shape(runway_store, monkeypatch):
    """A depleted fence keeps the legacy commit contract: one open, one
    transaction update, one commit."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _seed_session(runway_store, started_at=started_at, remaining=timedelta(seconds=30))

    recording_sessions.renew_recording_session_lease('uid', 'session', 'conversation', firestore_client=runway_store)

    assert len(runway_store.budget_calls) == 1
    assert len(runway_store.transactions) == 1
    assert len(runway_store.updates) == 1
    assert len(runway_store.commits) == 1


def test_open_then_first_renewal_minute_skips(runway_store, monkeypatch):
    """The open just wrote a full-duration fence; the first renewal minute
    after it must verify read-only, not stamp again."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    recording_sessions.create_or_get_recording_session('uid', 'session', 'conversation', firestore_client=runway_store)
    runway_store.updates.clear()

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'session', 'conversation', firestore_client=runway_store
    )

    assert renewed is True
    assert runway_store.updates == []
    assert runway_store.documents[_SESSION_PATH]['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
