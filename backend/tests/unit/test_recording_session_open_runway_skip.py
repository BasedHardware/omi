"""A reconnect's session open must not re-stamp a fence its renewals still hold.

Failure-Class: FC-session-open-restamps-a-live-fence (new class declared in
this diff; the nearest existing class covers the neighbouring shape —
FC-lease-renewal-locks-the-document-it-only-reads is scoped to the lease
renewal's runway skip, and FC-renewal-lease-write-aborted-as-failed-write
covers contention classification at the renewal boundary — not the open,
whose reconnect-time re-stamp still took the session document's write lock to
rewrite the same value the session's own renewals had just stamped.)

Guards:
- an open that finds the matching, in-progress row behind a fence with more
  than ``RECORDING_SESSION_LEASE_RUNWAY_FLOOR`` of runway commits read-only:
  the stored fence and ``updated_at`` are untouched and the binding is
  returned exactly as before;
- a depleted fence (at or below the floor), a missing fence, and a malformed
  fence still re-stamp the full duration — the first open after a silence gap
  re-arms blackout immunity unchanged;
- mapping-conflict opens (a resumed pointer proposing a different
  conversation) keep the legacy compatibility routing and never write the
  fence;
- a non-``in_progress`` row (terminal or processing) is returned without a
  fence write;
- a brand-new session still creates its row with a full-duration fence;
- the conversation-side ``external_data`` marker keeps its atomic commit
  semantics in both arms: stamped when missing, untouched when already bound,
  and committed in the same transaction as the read-only fence skip;
- the read-only open survives a contended first read replayed on a fresh
  transaction and an expired-id commit restarted once, and still rides the
  shared bounded budget under its ``recording_session_open`` name;
- the lifecycle owner surfaces the read-only open to the WebSocket handshake
  with the same binding payload, and the skip never emits an
  ``omi_fallback_total`` degradation event;
- reconnect cadence is bounded in wall time: repeated opens inside the fence's
  runway write once at most, and a silent gap re-arms the fence on the first
  open that crosses the floor.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument

from database import conversation_finalization_jobs as jobs_db
from database import recording_sessions
from database.firestore_transaction_retry import run_with_transaction_contention_retry
from utils.conversations import lifecycle as lifecycle_service

_LOGGER_NAME = 'database.recording_sessions'
_LIFECYCLE_LOGGER_NAME = 'utils.conversations.lifecycle'
_EXPIRED_ID_MESSAGE = '400 The referenced transaction has expired or is no longer valid'
_SESSION_PATH = ('users', 'uid', 'recording_sessions', 'session')
_CONVERSATION_PATH = ('users', 'uid', 'conversations', 'conversation')


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
    store: '_OpenFirestore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.store.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.store, self.path + (name,))


@dataclass
class _CollectionRef:
    store: '_OpenFirestore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.store, self.path + (document_id,))


@dataclass
class _Transaction:
    store: '_OpenFirestore'

    def create(self, document: _DocumentRef, data: dict[str, Any]) -> None:
        self.store.writes.append({'kind': 'create', 'path': document.path, 'data': copy.deepcopy(data)})
        if document.path in self.store.documents:
            raise RuntimeError('already exists')
        self.store.documents[document.path] = copy.deepcopy(data)

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.store.writes.append({'kind': 'update', 'path': document.path, 'data': copy.deepcopy(updates)})
        self.store.documents[document.path].update(copy.deepcopy(updates))


@dataclass
class _OpenFirestore:
    """Fake Firestore tracking every attempted write so read-only commits are visible."""

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    read_errors: list[BaseException] = field(default_factory=list)
    commit_errors: list[BaseException] = field(default_factory=list)
    commits: list[_Transaction] = field(default_factory=list)
    transactions: list[_Transaction] = field(default_factory=list)
    writes: list[dict[str, Any]] = field(default_factory=list)
    budget_calls: list[dict[str, Any]] = field(default_factory=list)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction


def _seed_session(
    store: _OpenFirestore,
    *,
    conversation_id: str = 'conversation',
    phase: str = 'in_progress',
    remaining: timedelta | None = None,
    started_at: datetime | None = None,
    include_fence: bool = True,
) -> datetime:
    """Seed the session row; ``remaining`` pins the fence relative to the clock."""
    now = started_at or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    doc = {
        'schema_version': recording_sessions.RECORDING_SESSION_SCHEMA_VERSION,
        'uid': 'uid',
        'recording_session_id': 'session',
        'conversation_id': conversation_id,
        'lifecycle_version': recording_sessions.LIFECYCLE_ENVELOPE_VERSION,
        'lifecycle_phase': phase,
        'lifecycle_sequence': 0,
        'created_at': now,
        'updated_at': now,
    }
    if include_fence:
        if remaining is None:
            doc['lease_expires_at'] = now + recording_sessions.RECORDING_SESSION_LEASE_DURATION
        else:
            doc['lease_expires_at'] = now + remaining
    store.documents[_SESSION_PATH] = doc
    return now


@pytest.fixture
def open_store(monkeypatch):
    store = _OpenFirestore()

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


def _open(
    store: _OpenFirestore,
    proposed: str = 'conversation',
    **kwargs,
) -> dict[str, Any]:
    return recording_sessions.create_or_get_recording_session(
        'uid', 'session', proposed, firestore_client=store, **kwargs
    )


def _session_writes(store: _OpenFirestore) -> list[dict[str, Any]]:
    return [w for w in store.writes if w['path'] == _SESSION_PATH]


# ── The read-only open itself ────────────────────────────────────────────────


def test_open_behind_a_fresh_fence_commits_read_only(open_store):
    """Reconnecting inside the fence's runway re-verifies and writes nothing."""
    _seed_session(open_store)

    binding = _open(open_store)

    assert binding['recording_session_id'] == 'session'
    assert binding['conversation_id'] == 'conversation'
    assert binding['mapping_conflict'] is False
    assert _session_writes(open_store) == []
    assert len(open_store.commits) == 1


def test_read_only_open_leaves_fence_and_updated_at_untouched(open_store):
    started_at = _seed_session(open_store)

    _open(open_store)

    row = open_store.documents[_SESSION_PATH]
    assert row['lease_expires_at'] == started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    assert row['updated_at'] == started_at


@pytest.mark.parametrize(
    'remaining,renews',
    [
        (timedelta(minutes=5), False),
        (timedelta(minutes=4), False),
        (timedelta(minutes=2, seconds=1), False),
        (timedelta(minutes=2), True),
        (timedelta(minutes=1), True),
        (timedelta(seconds=30), True),
        (timedelta(seconds=0), True),
        (timedelta(minutes=-1), True),
    ],
    ids=[
        'full_runway_skips',
        'four_minutes_skips',
        'just_above_floor_skips',
        'exactly_floor_writes',
        'one_minute_writes',
        'thirty_seconds_writes',
        'expired_writes',
        'long_expired_writes',
    ],
)
def test_open_runway_boundary_is_exact(open_store, monkeypatch, remaining, renews):
    """Above the floor the open is a verified read; at or below it the fence moves."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=remaining, started_at=started_at)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)

    _open(open_store)

    session_writes = _session_writes(open_store)
    if renews:
        assert len(session_writes) == 1
        assert session_writes[0]['data']['lease_expires_at'] == (
            started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
        )
    else:
        assert session_writes == []


def test_missing_fence_still_writes_the_full_duration(open_store, monkeypatch):
    """A malformed row (no fence) must not be trusted; the open re-arms it."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, started_at=started_at, include_fence=False)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)

    _open(open_store)

    session_writes = _session_writes(open_store)
    assert len(session_writes) == 1
    assert session_writes[0]['data']['lease_expires_at'] == (
        started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_malformed_fence_still_writes_the_full_duration(open_store, monkeypatch):
    """A non-datetime fence is the same malformed shape as a missing one."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, started_at=started_at)
    open_store.documents[_SESSION_PATH]['lease_expires_at'] = 'not-a-timestamp'
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)

    _open(open_store)

    assert len(_session_writes(open_store)) == 1


def test_naive_stored_fence_skips_when_runway_sufficient(open_store, monkeypatch):
    """Firestore stores naive datetimes; the fence reads as UTC like the sweep."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(minutes=5), started_at=started_at)
    open_store.documents[_SESSION_PATH]['lease_expires_at'] = (started_at + timedelta(minutes=5)).replace(tzinfo=None)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)

    _open(open_store)

    assert _session_writes(open_store) == []


def test_skipped_open_still_verifies_through_the_transaction(open_store):
    """The verified read stays transactional — never a bare outside-budget get."""
    _seed_session(open_store)

    _open(open_store)

    assert len(open_store.transactions) == 1
    assert open_store.budget_calls[0]['operation_name'] == 'recording_session_open'


def test_skip_logs_one_info_line_and_no_error(open_store, caplog):
    """The no-op is observable at INFO and never as a warning or an error."""
    _seed_session(open_store)

    with caplog.at_level('INFO'):
        _open(open_store)

    lines = [record for record in caplog.records if record.name == _LOGGER_NAME]
    assert [record.levelname for record in lines] == ['INFO']
    assert 'nothing written' in lines[0].getMessage()
    assert all(record.levelname != 'ERROR' for record in caplog.records)


# ── Rows that must still write ──────────────────────────────────────────────


def test_first_open_creates_the_row_with_a_full_fence(open_store, monkeypatch):
    """A brand-new session is a create, never a skip."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)

    binding = _open(open_store)

    assert binding['mapping_conflict'] is False
    creates = [w for w in open_store.writes if w['kind'] == 'create' and w['path'] == _SESSION_PATH]
    assert len(creates) == 1
    assert creates[0]['data']['lease_expires_at'] == started_at + recording_sessions.RECORDING_SESSION_LEASE_DURATION


def test_depleted_fence_after_silence_re_stamps(open_store, monkeypatch):
    """The first open after a silent gap re-arms blackout immunity with a write."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(minutes=-5), started_at=started_at)
    gap_end = started_at + timedelta(minutes=30)
    monkeypatch.setattr(recording_sessions, '_now', lambda: gap_end)

    _open(open_store)

    session_writes = _session_writes(open_store)
    assert len(session_writes) == 1
    assert session_writes[0]['data']['lease_expires_at'] == (
        gap_end + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert open_store.documents[_SESSION_PATH]['updated_at'] == gap_end


def test_mapping_conflict_open_keeps_routing_without_a_fence_write(open_store):
    """A resumed pointer proposing another conversation must not touch the fence."""
    _seed_session(open_store, conversation_id='canonical')

    binding = _open(open_store, proposed='legacy-conversation')

    assert binding['mapping_conflict'] is True
    assert _session_writes(open_store) == []


@pytest.mark.parametrize('phase', ['processing', 'completed', 'failed', 'discarded'])
def test_non_in_progress_rows_are_returned_without_a_fence_write(open_store, phase):
    """Only a live in-progress row is behind a fence worth skipping."""
    _seed_session(open_store, phase=phase)

    binding = _open(open_store)

    assert binding['lifecycle_phase'] == phase
    assert _session_writes(open_store) == []


# ── Conversation marker atomicity ───────────────────────────────────────────


def test_read_only_open_still_stamps_a_missing_conversation_marker(open_store):
    """Recovery admission discovers the live lease through this marker."""
    _seed_session(open_store)
    open_store.documents[_CONVERSATION_PATH] = {'id': 'conversation', 'status': 'in_progress'}

    _open(open_store)

    marker_writes = [w for w in open_store.writes if w['path'] == _CONVERSATION_PATH]
    assert len(marker_writes) == 1
    assert marker_writes[0]['data']['external_data']['recording_session_id'] == 'session'
    assert _session_writes(open_store) == []
    assert len(open_store.commits) == 1


def test_bound_conversation_marker_is_not_rewritten(open_store):
    """A marker that already names the session stays untouched in the skip arm."""
    _seed_session(open_store)
    open_store.documents[_CONVERSATION_PATH] = {
        'id': 'conversation',
        'external_data': {'recording_session_id': 'session'},
    }

    _open(open_store)

    assert [w for w in open_store.writes if w['path'] == _CONVERSATION_PATH] == []


# ── Contention replay and expired-id restart ────────────────────────────────


def test_read_only_open_survives_a_contended_first_read(open_store):
    """A read-time abort replays on a fresh transaction and still skips."""
    _seed_session(open_store)
    open_store.read_errors.append(Aborted('read-time contention'))

    binding = _open(open_store)

    assert binding['conversation_id'] == 'conversation'
    assert _session_writes(open_store) == []
    assert len(open_store.commits) == 1


def test_read_only_open_survives_an_expired_id_commit(open_store):
    """A retired-id commit restarts once and skips without writing."""
    _seed_session(open_store)
    open_store.commit_errors.append(InvalidArgument(_EXPIRED_ID_MESSAGE))

    binding = _open(open_store)

    assert binding['conversation_id'] == 'conversation'
    assert _session_writes(open_store) == []
    assert len(open_store.commits) == 1


def test_depleted_open_after_a_drained_burst_still_writes(open_store, monkeypatch):
    """Contention replay on a fence that needs re-arming keeps the real write."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(seconds=30), started_at=started_at)
    open_store.read_errors.append(Aborted('read-time contention'))
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)

    _open(open_store)

    assert len(_session_writes(open_store)) == 1


# ── Lifecycle owner delivery ────────────────────────────────────────────────


def test_lifecycle_owner_delivers_the_read_only_binding(open_store):
    """The owner's open path returns the same binding payload on a skip."""
    _seed_session(open_store)

    binding = lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=open_store)

    assert binding['recording_session_id'] == 'session'
    assert binding['conversation_id'] == 'conversation'
    assert binding['lifecycle_phase'] == 'in_progress'
    assert binding['mapping_conflict'] is False
    assert _session_writes(open_store) == []


def test_lifecycle_owner_skip_never_degrades(open_store, caplog):
    """No ``omi_fallback_total`` event and no exception log on the skip arm."""
    _seed_session(open_store)

    with caplog.at_level('INFO'):
        binding = lifecycle_service.open_recording_session(
            'uid', 'session', 'conversation', firestore_client=open_store
        )

    assert binding is not None
    assert all(record.levelname != 'ERROR' for record in caplog.records)
    assert all('fallback' not in record.getMessage().lower() for record in caplog.records)


def test_owner_shadow_mode_still_skips_a_live_fence(open_store, monkeypatch):
    """The skip is mode-independent: shadow and enforce both re-verify read-only."""
    _seed_session(open_store)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')

    binding = lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=open_store)

    assert binding['conversation_id'] == 'conversation'
    assert _session_writes(open_store) == []


def test_snapshot_include_reads_the_row_once(open_store):
    """include_conversation_snapshot keeps its snapshot semantics on a skip."""
    _seed_session(open_store)
    open_store.documents[_CONVERSATION_PATH] = {'id': 'conversation', 'status': 'in_progress'}

    binding = _open(open_store, include_conversation_snapshot=True)

    assert binding['conversation_snapshot_known'] is True
    assert binding['conversation_snapshot']['id'] == 'conversation'
    assert _session_writes(open_store) == []


# ── Reconnect cadence ───────────────────────────────────────────────────────


def test_repeated_reconnects_re_stamp_only_when_the_fence_decays(open_store, monkeypatch):
    """Reconnects inside the runway skip; the decayed-fence minute re-stamps.

    Offsets 1 and 2 arrive while the original fence holds more than the floor,
    offset 3 lands exactly on the floor (fence written), and offset 4 rides
    the fence that write stamped — one write for a five-reconnect minute
    cadence, at the wall-clock boundary and nowhere else.
    """
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(minutes=5), started_at=started_at)

    for offset in range(1, 5):
        monkeypatch.setattr(recording_sessions, '_now', lambda offset=offset: started_at + timedelta(minutes=offset))
        binding = _open(open_store)
        assert binding['conversation_id'] == 'conversation'

    session_writes = _session_writes(open_store)
    assert len(session_writes) == 1
    assert session_writes[0]['data']['lease_expires_at'] == (
        started_at + timedelta(minutes=3) + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )
    assert len(open_store.commits) == 4


def test_silence_then_reconnect_re_stamps_once(open_store, monkeypatch):
    """A gap that crosses the floor re-arms the fence on the first open back."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(minutes=5), started_at=started_at)

    # reconnects at +1 and +2 minutes: both inside the runway, both read-only
    for offset in range(1, 3):
        monkeypatch.setattr(recording_sessions, '_now', lambda offset=offset: started_at + timedelta(minutes=offset))
        _open(open_store)
    assert _session_writes(open_store) == []

    # a 30-minute silence decays the fence; the next open re-stamps
    gap_end = started_at + timedelta(minutes=32)
    monkeypatch.setattr(recording_sessions, '_now', lambda: gap_end)
    _open(open_store)

    session_writes = _session_writes(open_store)
    assert len(session_writes) == 1
    assert session_writes[0]['data']['lease_expires_at'] == (
        gap_end + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


# ── Fail-open arms, contention shapes, and fence atomicity ──────────────────


def test_open_transient_blip_still_takes_the_shadow_legacy_route(open_store, monkeypatch):
    """The skip changes nothing about the open's own transient classification.

    A ServiceUnavailable on the open's first read is the bounded transient the
    lifecycle owner absorbs into the shadow legacy route — the runway skip
    lives below that boundary and must not have moved it.
    """
    from google.api_core.exceptions import ServiceUnavailable

    _seed_session(open_store)
    open_store.read_errors.append(ServiceUnavailable('data-plane blip'))
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')

    binding = lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=open_store)

    assert binding['conversation_id'] == 'conversation'
    assert binding['lifecycle_version'] is None
    assert open_store.writes == []


def test_owner_enforce_mode_still_skips_and_delivers_the_canonical_binding(open_store, monkeypatch):
    """Enforce mode raises on real failures but the skip is not a failure."""
    _seed_session(open_store)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')

    binding = lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=open_store)

    assert binding['conversation_id'] == 'conversation'
    assert binding['mapping_conflict'] is False
    assert _session_writes(open_store) == []


def test_exhausted_budget_on_a_skippable_row_raises_through_shadow(open_store, monkeypatch):
    """Contention that outlives the budget is still the classified transient.

    Five read-time aborts drain the shared budget; the owner's shadow arm
    keeps the legacy route with the contended WARNING, never a failed-write
    traceback, and the row is untouched.
    """
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    _seed_session(open_store)
    for _ in range(5):
        open_store.read_errors.append(Aborted('read-time contention'))
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')

    binding = lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=open_store)

    assert binding['lifecycle_version'] is None
    assert open_store.writes == []


def test_write_arm_tombstones_nothing_and_creates_no_duplicate(open_store):
    """The re-stamp arm only updates the fence fields, never recreates the row."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(seconds=30), started_at=started_at)

    _open(open_store)

    creates = [w for w in open_store.writes if w['kind'] == 'create']
    assert creates == []
    written = _session_writes(open_store)[0]['data']
    assert set(written) == {'lease_expires_at', 'updated_at'}
    assert open_store.documents[_SESSION_PATH]['lifecycle_phase'] == 'in_progress'
    assert open_store.documents[_SESSION_PATH]['lifecycle_sequence'] == 0


def test_write_arm_fence_and_marker_commit_in_one_transaction(open_store):
    """A re-stamping open that must bind a fresh marker commits both atomically."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(seconds=30), started_at=started_at)
    open_store.documents[_CONVERSATION_PATH] = {'id': 'conversation', 'status': 'in_progress'}

    _open(open_store)

    assert len(open_store.commits) == 1
    assert len(_session_writes(open_store)) == 1
    marker_writes = [w for w in open_store.writes if w['path'] == _CONVERSATION_PATH]
    assert len(marker_writes) == 1


def test_read_only_open_does_not_consume_the_fence(open_store, monkeypatch):
    """A skipped open leaves the fence at its original wall-clock expiry."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(minutes=4), started_at=started_at)

    # reconnects at +1 and +2 minutes: the first skips (runway 3m), the second
    # hits the floor and re-stamps — but the first skip never moved the fence,
    # which is why the second sees exactly the floor and not the floor plus a
    # re-stamp the skip would have caused had skips consumed wall clock.
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at + timedelta(minutes=1))
    _open(open_store)
    assert open_store.documents[_SESSION_PATH]['lease_expires_at'] == started_at + timedelta(minutes=4)

    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at + timedelta(minutes=2))
    _open(open_store)
    session_writes = _session_writes(open_store)
    assert len(session_writes) == 1
    assert session_writes[0]['data']['lease_expires_at'] == (
        started_at + timedelta(minutes=2) + recording_sessions.RECORDING_SESSION_LEASE_DURATION
    )


def test_skip_info_names_session_and_proposed_route(open_store, caplog):
    """The INFO line identifies the session and the proposed conversation."""
    _seed_session(open_store)

    with caplog.at_level('INFO'):
        _open(open_store)

    line = [r for r in caplog.records if r.name == _LOGGER_NAME][0]
    assert 'session=session' in line.getMessage()
    assert 'proposed=conversation' in line.getMessage()
    assert 'runway_s=' in line.getMessage()


def test_identity_mismatch_open_raises_before_any_write(open_store):
    """A cross-uid row collision keeps its hard failure and writes nothing."""
    _seed_session(open_store)
    open_store.documents[_SESSION_PATH]['uid'] = 'other-user'

    with pytest.raises(ValueError):
        _open(open_store)

    assert open_store.writes == []
    assert open_store.commits == []


def test_mapping_conflict_open_does_not_rewind_the_canonical_fence(open_store):
    """A conflict open neither writes the fence nor rewrites the binding."""
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, conversation_id='canonical', remaining=timedelta(seconds=30), started_at=started_at)

    binding = _open(open_store, proposed='legacy-conversation')

    assert binding['mapping_conflict'] is True
    assert binding['conversation_id'] == 'canonical'
    assert _session_writes(open_store) == []


def test_snapshot_open_after_the_skip_reports_known_true(open_store):
    """A skipped open with a snapshot request never reports an unknown row."""
    _seed_session(open_store)
    open_store.documents[_CONVERSATION_PATH] = {'id': 'conversation', 'status': 'in_progress'}

    binding = _open(open_store, include_conversation_snapshot=True)

    assert binding['conversation_snapshot_known'] is True
    assert _session_writes(open_store) == []


def test_processing_phase_row_open_is_read_only_but_conflict_free(open_store):
    """A processing-phase row: no fence write, binding still returned cleanly."""
    _seed_session(open_store, phase='processing')

    binding = _open(open_store)

    assert binding['lifecycle_phase'] == 'processing'
    assert binding['mapping_conflict'] is False
    assert _session_writes(open_store) == []


def test_commit_side_blip_on_a_skip_open_classifies_as_transient(open_store, monkeypatch):
    """A commit-time Aborted after a read-only body replays on a fresh transaction.

    The SDK replays a commit abort on the same (often retired) id; the shared
    budget replays it on fresh transactions, and the read-only body is free
    to replay — the skip lands on the retry without writing anything.
    """
    _seed_session(open_store)
    open_store.commit_errors.append(Aborted('commit-time contention'))
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'shadow')

    binding = lifecycle_service.open_recording_session('uid', 'session', 'conversation', firestore_client=open_store)

    assert binding['conversation_id'] == 'conversation'
    assert _session_writes(open_store) == []
    assert len(open_store.commits) == 1


def test_recovery_sweep_still_sees_the_skipped_fence_as_live(open_store, monkeypatch):
    """The read-only open must not shorten the protection the sweep reads.

    The sweep's admission reads the session fence through the conversation's
    ``external_data`` marker in its own transaction; the skipped open keeps
    that fence (wall clock, untouched) and the marker binding it, so the same
    read the sweep performs over the same store still reports the session as
    live one minute after a skipped reconnect.
    """
    started_at = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
    _seed_session(open_store, remaining=timedelta(minutes=4), started_at=started_at)
    open_store.documents[_CONVERSATION_PATH] = {'id': 'conversation', 'status': 'in_progress'}
    monkeypatch.setattr(recording_sessions, '_now', lambda: started_at)
    _open(open_store)

    probe_at = started_at + timedelta(minutes=1)
    marker_writes = [w for w in open_store.writes if w['path'] == _CONVERSATION_PATH]
    assert len(marker_writes) == 1
    conversation = dict(open_store.documents[_CONVERSATION_PATH])
    conversation['external_data'] = marker_writes[0]['data']['external_data']
    assert (
        jobs_db._has_active_recording_session_lease(
            open_store.transaction(),
            open_store.collection('users').document('uid').collection('recording_sessions'),
            'uid',
            'conversation',
            conversation,
            probe_at,
        )
        is True
    )
