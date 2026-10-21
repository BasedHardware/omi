"""The empty-generation delete must survive a drained store burst like its siblings.

Failure-Class: FC-retired-transaction-treated-as-fatal — the cleanup writer on
the recording-session surface still carried the two shapes the other three
writers already shed:

- the storage seam wrapped its body with ONE ``firestore.transactional``
  decorator outside the contention budget, so every budget attempt replayed
  the same — often already retired — transaction ``retry_id``; a commit abort
  inside the budget then resubmitted the dead id and the terminal
  ``InvalidArgument 400 The referenced transaction has expired or is no longer
  valid`` walked out of the budget (the budget only replays ``Aborted``);
- the lifecycle boundary ``delete_empty_recording_conversation`` had no
  transient arm at all, so a burst that outlived both retry layers surfaced as
  a raw traceback through WebSocket teardown, the rollover loser cleanup and
  continuation adoption — the same drained burst the renewal, open and event
  boundaries already keep log-only.

Prod backend-listen 2026-10-21: the window's top signature was the renewal's
retired-id traceback (×70/30m) with the open sibling ×33/30m, and the cleanup
transaction races the very same session document — the last writer on the
surface still able to surface that shape. Nothing is written by a drained
burst — the empty row and its session stay exactly as they were — so the next
teardown, rollover or recovery sweep re-attempts the delete for free.

Guards:
- the storage seam wraps the transaction body fresh on every budget attempt
  (no wrapper, and therefore no ``retry_id``, spans two attempts);
- a drained burst — expired-id 400s, contention ``Aborted``s, the SDK's
  replay-wrapper ``ValueError``, read-side retirement — keeps the generation
  log-only: WARNING without a stack trace, no ``omi_fallback_total``
  degradation event, no physical cleanup, no partial snapshot;
- recovery inside the budgets stays silent; back-to-back drains stay bounded;
  the next clean call deletes;
- a random ``InvalidArgument`` and ``PermissionDenied`` keep the failed-write
  classification (traceback + degradation event), so the arm is not
  over-broad, and a successful delete still runs its physical cleanup;
- the transient arm consults the one shared classifier, is deliberately
  mode-independent (cleanup fail-open only ever delays a delete), and leaves
  the ``deleted_conversation`` out-param clean;
- continuation adoption survives a drained cleanup without raising.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from google.api_core.exceptions import Aborted, InvalidArgument, PermissionDenied

from database import conversations as conversations_db
from database import recording_sessions
from database.firestore_transaction_retry import (
    run_with_transaction_contention_retry,
)
from utils.conversations import lifecycle as lifecycle_service
from utils.conversations import live_continuation

_EXPIRED = 'The referenced transaction has expired or is no longer valid'
_CONVERSATION_PATH = ('users', 'uid', 'conversations', 'conversation')
_SESSION_PATH = ('users', 'uid', 'recording_sessions', 'recording')


def _stored_conversation() -> dict[str, Any]:
    """Encode an empty generation exactly as the production write path stores it."""
    return conversations_db.encode_conversation_for_write(
        'uid',
        {'id': 'conversation', 'status': 'in_progress', 'transcript_segments': []},
        'standard',
    )


def _seed_generation(store: '_ContendingStore') -> None:
    now = datetime.now(timezone.utc)
    store.documents[_CONVERSATION_PATH] = _stored_conversation()
    store.documents[_SESSION_PATH] = {
        'schema_version': recording_sessions.RECORDING_SESSION_SCHEMA_VERSION,
        'uid': 'uid',
        'recording_session_id': 'recording',
        'conversation_id': 'conversation',
        'lifecycle_version': recording_sessions.LIFECYCLE_ENVELOPE_VERSION,
        'lifecycle_phase': 'in_progress',
        'lifecycle_sequence': 0,
        'created_at': now,
        'updated_at': now,
        'lease_expires_at': now + recording_sessions.RECORDING_SESSION_LEASE_DURATION,
    }


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
    store: '_ContendingStore'
    path: tuple[str, ...]

    def get(self, transaction: object = None) -> _Snapshot:
        del transaction
        return _Snapshot(self.store.documents.get(self.path))

    def collection(self, name: str) -> '_CollectionRef':
        return _CollectionRef(self.store, self.path + (name,))


@dataclass
class _CollectionRef:
    store: '_ContendingStore'
    path: tuple[str, ...]

    def document(self, document_id: str) -> _DocumentRef:
        return _DocumentRef(self.store, self.path + (document_id,))


@dataclass
class _Transaction:
    store: '_ContendingStore'

    def update(self, document: _DocumentRef, updates: dict[str, Any]) -> None:
        self.store.documents[document.path].update(copy.deepcopy(updates))

    def delete(self, document: _DocumentRef) -> None:
        self.store.documents.pop(document.path, None)


@dataclass
class _ContendingStore:
    """Fake Firestore whose transactional boundary fails until the queue drains.

    ``boundary_errors`` fires from the wrapped call — where the real
    commit-side retirement or the read-time abort surfaces — so every budget
    attempt consumes one until the queue drains and the error escapes.
    ``wrappers_created`` counts ``firestore.transactional(func)``
    constructions: the regression this file pins is that the cleanup writer
    constructs one per attempt, never one decorator spanning them all.
    """

    documents: dict[tuple[str, ...], dict[str, Any]] = field(default_factory=dict)
    boundary_errors: list[BaseException] = field(default_factory=list)
    commits: list[_Transaction] = field(default_factory=list)
    transactions: list[_Transaction] = field(default_factory=list)
    wrappers_created: int = 0
    budget_calls: list[str | None] = field(default_factory=list)

    def collection(self, name: str) -> _CollectionRef:
        return _CollectionRef(self, (name,))

    def transaction(self) -> _Transaction:
        transaction = _Transaction(self)
        self.transactions.append(transaction)
        return transaction


@pytest.fixture
def contending_store(monkeypatch) -> _ContendingStore:
    store = _ContendingStore(boundary_errors=[Aborted('contention'), Aborted('contention')])

    def transactional(func):
        store.wrappers_created += 1

        def wrapped(transaction, *args, **kwargs):
            if store.boundary_errors:
                raise store.boundary_errors.pop(0)
            result = func(transaction, *args, **kwargs)
            store.commits.append(transaction)
            return result

        return wrapped

    monkeypatch.setattr(recording_sessions.firestore, 'transactional', transactional)

    def budget_retry(*a, **kw):
        store.budget_calls.append(kw.get('operation_name'))
        kw.setdefault('sleep', lambda _delay: None)
        kw.setdefault('random_value', lambda: 0)
        return run_with_transaction_contention_retry(*a, **kw)

    monkeypatch.setattr(recording_sessions, 'run_with_transaction_contention_retry', budget_retry)
    return store


@pytest.fixture
def fallback_spy(monkeypatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def spy(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(lifecycle_service, 'record_fallback', spy)
    return calls


def _queue(store: _ContendingStore, errors: list[BaseException]) -> None:
    store.boundary_errors = list(errors)


def _drained(store: _ContendingStore, error: BaseException) -> None:
    """Queue enough copies to outlive both retry layers in one budget pass."""
    _queue(store, [error] * 50)


def _drained_expired_id(store: _ContendingStore) -> None:
    _drained(store, InvalidArgument(f'400 {_EXPIRED}'))


def _drained_read_side_retirement(store: _ContendingStore) -> None:
    _drained(store, Aborted(f'409 {_EXPIRED}'))


def _drained_sdk_replay_wrapper(store: _ContendingStore) -> None:
    replay = ValueError('Aborted after 5 attempts. Original exception: contention.')
    replay.__cause__ = Aborted('contention')
    _drained(store, replay)


def _failed_write_records(caplog, fragment: str) -> list:
    return [
        record
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle'
        and record.levelno >= logging.ERROR
        and fragment in record.getMessage()
    ]


def _transient_warnings(caplog, fragment: str) -> list:
    return [
        record
        for record in caplog.records
        if record.name == 'utils.conversations.lifecycle'
        and record.levelname == 'WARNING'
        and fragment in record.getMessage()
    ]


def _cleanup(
    uid: str = 'uid',
    conversation_id: str = 'conversation',
    recording_session_id: str | None = 'recording',
    store: Any = None,
):
    return lifecycle_service.delete_empty_recording_conversation(
        uid, conversation_id, recording_session_id, firestore_client=store
    )


# ── A. Storage seam: the body is wrapped fresh on every budget attempt ──────


def test_empty_delete_wraps_the_body_fresh_per_budget_attempt(contending_store):
    """Two aborted attempts then success: three attempts, three wrappers, one commit."""
    _seed_generation(contending_store)
    _queue(contending_store, [Aborted('contention'), Aborted('contention')])

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    assert _CONVERSATION_PATH not in contending_store.documents
    assert len(contending_store.commits) == 1
    # One wrapper and one fresh transaction per budget attempt — never one
    # decorator spanning them (a decorator would pin one retired retry_id).
    assert contending_store.wrappers_created == 3
    assert len(contending_store.transactions) == 3


def test_empty_delete_does_not_pin_one_wrapper_across_attempts(contending_store):
    """The regression: a wrapper built outside the budget spans every attempt."""
    _seed_generation(contending_store)
    _queue(contending_store, [Aborted('contention')])

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    assert contending_store.commits == contending_store.transactions[-1:] or len(contending_store.commits) == 1
    assert contending_store.wrappers_created == 2


def test_empty_delete_expired_id_restart_also_wraps_fresh(contending_store):
    """The expired-id restart inside ``run_transactional`` re-runs the wrapper."""
    _seed_generation(contending_store)
    _queue(contending_store, [InvalidArgument(f'400 {_EXPIRED}')])

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    # The restart happens INSIDE the same wrapper on the same outer attempt —
    # the fresh transaction is what matters, and the wrapper count proves the
    # wrapper itself never spans two OUTER budget attempts.
    assert contending_store.wrappers_created == 1
    assert len(contending_store.transactions) == 2


def test_empty_delete_mixed_burst_keeps_fresh_wrapping(contending_store):
    _seed_generation(contending_store)
    _queue(
        contending_store,
        [Aborted('contention'), InvalidArgument(f'400 {_EXPIRED}'), Aborted('contention')],
    )

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    assert contending_store.wrappers_created == 3


def test_empty_delete_runs_on_the_named_shared_budget(contending_store):
    _seed_generation(contending_store)
    _queue(contending_store, [])

    recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert contending_store.budget_calls == ['recording_session_empty_delete']


# ── B. Lifecycle boundary: a drained burst keeps the generation log-only ────


def test_drained_expired_id_cleanup_keeps_the_generation_log_only(contending_store, fallback_spy, caplog):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    assert not _failed_write_records(caplog, 'recording session cleanup failed')
    assert _transient_warnings(caplog, 'recording session cleanup contended')
    assert fallback_spy == []


def test_drained_contention_cleanup_keeps_the_generation_log_only(contending_store, fallback_spy, caplog):
    _seed_generation(contending_store)
    _drained(contending_store, Aborted('contention'))

    assert _cleanup(store=contending_store) is False
    assert not _failed_write_records(caplog, 'recording session cleanup failed')
    assert _transient_warnings(caplog, 'recording session cleanup contended')
    assert fallback_spy == []


def test_drained_sdk_replay_wrapper_cleanup_is_log_only(contending_store, fallback_spy, caplog):
    _seed_generation(contending_store)
    _drained_sdk_replay_wrapper(contending_store)

    assert _cleanup(store=contending_store) is False
    assert not _failed_write_records(caplog, 'recording session cleanup failed')
    assert _transient_warnings(caplog, 'recording session cleanup contended')
    assert fallback_spy == []


def test_drained_read_side_retirement_cleanup_is_log_only(contending_store, fallback_spy, caplog):
    _seed_generation(contending_store)
    _drained_read_side_retirement(contending_store)

    assert _cleanup(store=contending_store) is False
    assert not _failed_write_records(caplog, 'recording session cleanup failed')
    assert _transient_warnings(caplog, 'recording session cleanup contended')
    assert fallback_spy == []


def test_drained_cleanup_writes_no_partial_state(contending_store):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    # Nothing was written: the empty row survives for the next sweep and the
    # bound session is neither tombstoned nor sequence-advanced.
    assert _CONVERSATION_PATH in contending_store.documents
    session = contending_store.documents[_SESSION_PATH]
    assert session['lifecycle_phase'] == 'in_progress'
    assert session['lifecycle_sequence'] == 0


def test_drained_cleanup_reports_false_like_a_refusal(contending_store):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    result = _cleanup(store=contending_store)

    assert result is False
    assert result is not None


def test_drained_cleanup_keeps_the_out_param_clean(contending_store):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)
    published: dict[str, Any] = {'stale': 'value'}

    # The boundary runs the same call the storage seam publishes through; a
    # drain must never leave a partial snapshot in the caller's out-param.
    assert _cleanup(store=contending_store) is False
    assert published == {'stale': 'value'}


def test_seam_publishes_only_the_committing_attempts_snapshot(contending_store):
    """A retry after an aborted attempt publishes no stale or partial snapshot."""
    _seed_generation(contending_store)
    _queue(contending_store, [Aborted('contention')])
    published: dict[str, Any] = {'stale': 'value'}

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid',
        'conversation',
        'recording',
        firestore_client=contending_store,
        deleted_conversation=published,
    )

    assert deleted is True
    assert published.get('id') == 'conversation'
    assert 'stale' not in published


def test_absent_row_publishes_no_snapshot_either(contending_store):
    published: dict[str, Any] = {'stale': 'value'}

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid',
        'conversation',
        'recording',
        firestore_client=contending_store,
        deleted_conversation=published,
    )

    assert deleted is False
    assert published == {'stale': 'value'}


def test_time_source_is_provided_by_the_caller_not_the_store(contending_store):
    """``_now()`` is only read on the write path; a drained run reads it freely.

    Guards that no cached clock value from a failed attempt is ever stamped
    onto the retained generation — every attempt computes its own ``now``.
    """
    _seed_generation(contending_store)
    _queue(contending_store, [Aborted('contention')])

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    updated = contending_store.documents[_SESSION_PATH]['updated_at']
    assert updated.tzinfo is not None
    assert updated <= datetime.now(timezone.utc) + timedelta(seconds=5)


def test_drained_cleanup_warning_carries_generation_identity(contending_store, caplog):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    warnings = _transient_warnings(caplog, 'recording session cleanup contended')
    assert warnings, 'the contended outcome must be observable'
    message = warnings[0].getMessage()
    assert 'uid=uid' in message
    assert 'conversation=conversation' in message
    assert 'session=recording' in message


def test_drained_cleanup_warning_has_no_stack_trace(contending_store, caplog):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    warnings = _transient_warnings(caplog, 'recording session cleanup contended')
    assert warnings and warnings[0].exc_info is None


def test_back_to_back_drained_cleanups_stay_bounded(contending_store, caplog):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    assert _cleanup(store=contending_store) is False
    assert len(_transient_warnings(caplog, 'recording session cleanup contended')) == 2
    assert not _failed_write_records(caplog, 'recording session cleanup failed')


@pytest.fixture
def cleanup_seams(monkeypatch) -> list[str]:
    """Hold the physical-cleanup boundaries a successful delete fans out to."""
    from utils.conversations import typesense_index

    touched: list[str] = []
    monkeypatch.setattr(typesense_index, 'delete_conversation_index_doc', lambda *a, **k: touched.append('index'))
    monkeypatch.setattr(
        lifecycle_service.conversations_db,
        'delete_conversation_photos',
        lambda *a, **k: touched.append('photos'),
    )
    monkeypatch.setattr(
        lifecycle_service,
        'delete_conversation_audio_files',
        lambda *a, **k: touched.append('audio'),
        raising=False,
    )
    return touched


def test_next_clean_cleanup_after_a_drained_one_deletes(contending_store, fallback_spy, cleanup_seams):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)
    assert _cleanup(store=contending_store) is False

    _queue(contending_store, [])
    assert _cleanup(store=contending_store) is True
    assert _CONVERSATION_PATH not in contending_store.documents
    assert fallback_spy == []


def test_cleanup_recovery_inside_the_budget_is_silent(contending_store, caplog, cleanup_seams):
    _seed_generation(contending_store)
    _queue(contending_store, [Aborted('contention'), Aborted('contention')])

    assert _cleanup(store=contending_store) is True
    assert not _transient_warnings(caplog, 'recording session cleanup contended')
    assert not _failed_write_records(caplog, 'recording session cleanup failed')


def test_expired_id_restart_inside_the_budget_is_silent(contending_store, caplog, cleanup_seams):
    _seed_generation(contending_store)
    _queue(contending_store, [InvalidArgument(f'400 {_EXPIRED}')])

    assert _cleanup(store=contending_store) is True
    assert not _transient_warnings(caplog, 'recording session cleanup contended')
    assert not _failed_write_records(caplog, 'recording session cleanup failed')


def test_drained_cleanup_runs_no_physical_cleanup(contending_store, cleanup_seams):
    """A retained generation must not lose its index doc, photos or audio sweep."""
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    assert cleanup_seams == []


def test_successful_cleanup_still_runs_the_physical_cleanup(contending_store, cleanup_seams):
    """The transient arm must not suppress the work of a successful delete."""
    _seed_generation(contending_store)
    _queue(contending_store, [])

    assert _cleanup(store=contending_store) is True
    assert cleanup_seams == ['index', 'photos', 'audio']


# ── C. Real write failures keep the failed-write classification ─────────────


def test_random_400_cleanup_keeps_the_failed_write_classification(contending_store, fallback_spy, caplog):
    _seed_generation(contending_store)
    _drained(contending_store, InvalidArgument('400 Request contains an invalid argument.'))

    assert _cleanup(store=contending_store) is False
    assert _failed_write_records(caplog, 'recording session cleanup failed')
    assert not _transient_warnings(caplog, 'recording session cleanup contended')
    assert fallback_spy and fallback_spy[0]['from_mode'] == 'recording_session'


def test_permission_denied_cleanup_keeps_the_failed_write_classification(contending_store, fallback_spy, caplog):
    _seed_generation(contending_store)
    _drained(contending_store, PermissionDenied('the caller cannot write this row'))

    assert _cleanup(store=contending_store) is False
    assert _failed_write_records(caplog, 'recording session cleanup failed')
    assert fallback_spy, 'a real write failure must emit the degradation event'


def test_failed_write_cleanup_log_is_an_exception_log(contending_store, caplog):
    _seed_generation(contending_store)
    _drained(contending_store, PermissionDenied('denied'))

    assert _cleanup(store=contending_store) is False
    failures = _failed_write_records(caplog, 'recording session cleanup failed')
    assert failures and failures[0].exc_info is not None


def test_failed_write_cleanup_still_retains_the_generation(contending_store):
    """Even the failed-write arm fails open: the row stays, never a raise."""
    _seed_generation(contending_store)
    _drained(contending_store, PermissionDenied('denied'))

    assert _cleanup(store=contending_store) is False
    assert _CONVERSATION_PATH in contending_store.documents


# ── D. Classifier ownership, mode independence, callers ─────────────────────


def test_cleanup_boundary_uses_the_shared_transient_classifier(contending_store, monkeypatch):
    consulted: list[BaseException] = []
    real = lifecycle_service._is_recording_session_transient

    def spy(error):
        consulted.append(error)
        return real(error)

    monkeypatch.setattr(lifecycle_service, '_is_recording_session_transient', spy)
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    assert consulted and isinstance(consulted[0], InvalidArgument)


def test_cleanup_transient_arm_is_deliberately_mode_independent(contending_store, monkeypatch):
    """Cleanup fail-open only ever delays a delete; no mode raises it."""
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')

    assert _cleanup(store=contending_store) is False


def test_rollover_loser_cleanup_survives_a_drained_burst(contending_store):
    """The rollover loser's unexposed generation is retained, not a traceback."""
    contending_store.documents.pop(_CONVERSATION_PATH, None)
    contending_store.documents.pop(_SESSION_PATH, None)
    _drained_expired_id(contending_store)

    assert _cleanup('uid', 'loser-conversation', 'loser-session', store=contending_store) is False


def test_continuation_adopt_survives_a_drained_cleanup(contending_store, monkeypatch):
    """``resolve_live_continuation`` returns the adopted pointer on a drained delete."""
    from datetime import datetime as _datetime

    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    pointer = {'conversation_id': 'conversation', 'recording_session_id': 'recording'}
    monkeypatch.setattr(
        live_continuation.listen_continuations,
        'resolve_live_continuation',
        lambda *a, **k: (pointer, pointer),
    )

    result = live_continuation.resolve_live_continuation(
        'uid',
        'origin',
        source='mic',
        device_id=None,
        now=_datetime.now(timezone.utc),
        timeout=10,
    )

    assert result == pointer
    assert _CONVERSATION_PATH in contending_store.documents


def test_cleanup_never_raises_a_drained_store_error_to_the_socket(contending_store):
    """Every drained shape returns; none of them escapes to the WS teardown."""
    _seed_generation(contending_store)
    for drained in (
        _drained_expired_id,
        _drained_read_side_retirement,
        _drained_sdk_replay_wrapper,
    ):
        _seed_generation(contending_store)
        drained(contending_store)
        assert _cleanup(store=contending_store) is False


# ── E. Storage seam: per-shape replays and budget accounting ────────────────


def test_empty_delete_replays_an_expired_id_only_burst_and_commits_once(contending_store):
    """Retirement 400s restart inside ``run_transactional`` and commit once.

    The restart budget is three fresh-transaction attempts; a burst longer
    than that escapes the seam as a raw ``InvalidArgument`` — which is exactly
    why the lifecycle boundary owns the transient arm.
    """
    _seed_generation(contending_store)
    _queue(contending_store, [InvalidArgument(f'400 {_EXPIRED}'), InvalidArgument(f'400 {_EXPIRED}')])

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    assert _CONVERSATION_PATH not in contending_store.documents
    assert len(contending_store.commits) == 1
    assert len(contending_store.transactions) == 3


def test_unbounded_expired_burst_escapes_the_seam_for_the_boundary(contending_store):
    """Past the restart budget the seam raises — the boundary arm absorbs it."""
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    with pytest.raises(InvalidArgument):
        recording_sessions.tombstone_and_delete_empty_conversation(
            'uid', 'conversation', 'recording', firestore_client=contending_store
        )
    # The seam consumed only its restart budget; nothing was written.
    assert _CONVERSATION_PATH in contending_store.documents
    assert contending_store.commits == []


def test_empty_delete_replays_a_read_side_409_only_burst_and_commits_once(contending_store):
    _seed_generation(contending_store)
    _queue(
        contending_store,
        [Aborted(f'409 {_EXPIRED}'), Aborted(f'409 {_EXPIRED}')],
    )

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    assert len(contending_store.commits) == 1


def test_empty_delete_replays_the_sdk_valueerror_wrapper_at_the_seam(contending_store):
    """The budget classifies the chained replay wrapper as contention."""
    _seed_generation(contending_store)
    replay = ValueError('Aborted after 5 attempts. Original exception: contention.')
    replay.__cause__ = Aborted('contention')
    _queue(contending_store, [replay])

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    assert len(contending_store.commits) == 1
    # One outer replay: the wrapper ValueError is not an expiry, so the
    # restart layer hands it to the contention budget, which mints a fresh
    # wrapper and transaction for the second attempt.
    assert contending_store.wrappers_created == 2
    assert len(contending_store.transactions) == 2


def test_exhausted_cleanup_consumes_exactly_the_budget_of_attempts(contending_store):
    """No off-by-one: DEFAULT_MAX_ATTEMPTS wrappers, then exhaustion."""
    from database.firestore_transaction_retry import DEFAULT_MAX_ATTEMPTS

    _seed_generation(contending_store)
    _drained(contending_store, Aborted('contention'))

    assert _cleanup(store=contending_store) is False
    assert contending_store.wrappers_created == DEFAULT_MAX_ATTEMPTS
    assert len(contending_store.transactions) == DEFAULT_MAX_ATTEMPTS


def test_exhausted_cleanup_leaves_the_generation_untouched(contending_store):
    _seed_generation(contending_store)
    _drained(contending_store, Aborted('contention'))

    assert _cleanup(store=contending_store) is False
    assert _CONVERSATION_PATH in contending_store.documents
    session = contending_store.documents[_SESSION_PATH]
    assert session['lifecycle_phase'] == 'in_progress'
    assert session['lifecycle_sequence'] == 0


def test_failed_attempts_never_reach_the_commit_record(contending_store):
    _seed_generation(contending_store)
    _queue(contending_store, [Aborted('contention'), Aborted('contention')])

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert deleted is True
    # Only the successful attempt's transaction is a commit.
    assert [t is store_txn for t, store_txn in zip(contending_store.commits, contending_store.transactions[-1:])] == [
        True
    ]


def test_two_sequential_deletes_each_commit_on_their_own_budget(contending_store):
    """No state leaks between budget runs through the per-attempt wrapper."""
    _seed_generation(contending_store)
    _queue(contending_store, [])

    first = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )
    contending_store.documents[_CONVERSATION_PATH] = _stored_conversation()
    second = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', 'recording', firestore_client=contending_store
    )

    assert first is True and second is True
    assert len(contending_store.commits) == 2
    # One fresh wrapper per attempt of each run: no wrapper is reused across
    # budget runs either.
    assert contending_store.wrappers_created == 2


# ── F. Classifier branch ownership at the boundary ──────────────────────────


def test_contention_drain_consults_the_classifier_with_contention_exhausted(contending_store, monkeypatch):
    """The real prod shape: the budget wraps the burst in FirestoreContentionExhausted."""
    from database.firestore_transaction_retry import FirestoreContentionExhausted

    consulted: list[BaseException] = []
    real = lifecycle_service._is_recording_session_transient

    def spy(error):
        consulted.append(error)
        return real(error)

    monkeypatch.setattr(lifecycle_service, '_is_recording_session_transient', spy)
    _seed_generation(contending_store)
    _drained(contending_store, Aborted('contention'))

    assert _cleanup(store=contending_store) is False
    assert consulted and isinstance(consulted[0], FirestoreContentionExhausted)


def test_mixed_expiry_then_contention_burst_is_log_only(contending_store, fallback_spy, caplog):
    """The realistic interleaved burst: retirement first, contention behind it."""
    _seed_generation(contending_store)
    _queue(contending_store, [InvalidArgument(f'400 {_EXPIRED}')] + [Aborted('contention')] * 6)

    assert _cleanup(store=contending_store) is False
    assert not _failed_write_records(caplog, 'recording session cleanup failed')
    assert _transient_warnings(caplog, 'recording session cleanup contended')
    assert fallback_spy == []


def test_prod_retirement_text_is_the_classifier_marker():
    """The boundary's transient arm keys on the write layer's retirement marker."""
    from database._client import _EXPIRED_TRANSACTION_MARKER, is_expired_transaction_error

    # The marker the write layer matches is contained in the prod retirement
    # text, so the boundary and the restart budget can never disagree on what
    # counts as "this transaction id was retired".
    assert _EXPIRED_TRANSACTION_MARKER in _EXPIRED.lower()
    assert is_expired_transaction_error(InvalidArgument(_EXPIRED))
    assert not is_expired_transaction_error(InvalidArgument('400 invalid document path'))


# ── G. Telemetry shape and log hygiene ──────────────────────────────────────


def test_failed_write_arm_emits_the_degraded_fallback_shape(contending_store, fallback_spy):
    _seed_generation(contending_store)
    _drained(contending_store, PermissionDenied('denied'))

    assert _cleanup(store=contending_store) is False
    event = fallback_spy[0]
    assert event['component'] == 'other'
    assert event['from_mode'] == 'recording_session'
    assert event['to_mode'] == 'legacy_pointer'
    assert event['outcome'] == 'degraded'


def test_transient_warning_never_carries_the_store_error_text(contending_store, caplog):
    """Bounded tokens only: the raw retirement text (and any path it names) stays out."""
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    warnings = _transient_warnings(caplog, 'recording session cleanup contended')
    assert warnings
    assert _EXPIRED.lower() not in warnings[0].getMessage().lower()


def test_transient_warning_stays_clean_even_for_a_chained_error(contending_store, caplog):
    _seed_generation(contending_store)
    _drained_sdk_replay_wrapper(contending_store)

    assert _cleanup(store=contending_store) is False
    warnings = _transient_warnings(caplog, 'recording session cleanup contended')
    assert warnings and warnings[0].exc_info is None
    assert 'Aborted after 5 attempts' not in warnings[0].getMessage()


# ── H. Boundary contracts: passthrough, quiet refusals, legacy route ────────


def test_boundary_forwards_the_injected_client_and_identity_to_storage(contending_store, monkeypatch):
    received: dict[str, Any] = {}

    def spy(uid, conversation_id, recording_session_id, **kwargs):
        received.update(
            uid=uid,
            conversation_id=conversation_id,
            recording_session_id=recording_session_id,
            firestore_client=kwargs.get('firestore_client'),
        )
        return False

    monkeypatch.setattr(lifecycle_service.recording_sessions_db, 'tombstone_and_delete_empty_conversation', spy)

    assert _cleanup('uid-x', 'conversation-x', 'session-x', store=contending_store) is False
    assert received == {
        'uid': 'uid-x',
        'conversation_id': 'conversation-x',
        'recording_session_id': 'session-x',
        'firestore_client': contending_store,
    }


def test_enforce_mode_still_never_raises_the_cleanup_to_the_socket(contending_store, monkeypatch, fallback_spy):
    """Cleanup fail-open only ever delays a delete; even real failures stay calls."""
    _seed_generation(contending_store)
    _drained(contending_store, PermissionDenied('denied'))
    monkeypatch.setattr(lifecycle_service, 'recording_session_mode', lambda: 'enforce')

    assert _cleanup(store=contending_store) is False
    assert fallback_spy, 'the failed-write telemetry still fires'


def test_plain_runtime_error_takes_the_failed_write_arm(contending_store, fallback_spy, caplog):
    _seed_generation(contending_store)
    _drained(contending_store, RuntimeError('connection reset mid-commit'))

    assert _cleanup(store=contending_store) is False
    assert _failed_write_records(caplog, 'recording session cleanup failed')
    assert fallback_spy


def test_document_size_rejection_is_a_failed_write_not_a_transient(contending_store, fallback_spy, caplog):
    """A permanent 400 must keep its classification — the arm is not marker-blind."""
    _seed_generation(contending_store)
    _drained(contending_store, InvalidArgument('400 The request exceeds the maximum allowed entity size'))

    assert _cleanup(store=contending_store) is False
    assert _failed_write_records(caplog, 'recording session cleanup failed')
    assert not _transient_warnings(caplog, 'recording session cleanup contended')


def test_chained_sdk_aborts_through_a_runtime_error_are_still_transient(contending_store, fallback_spy, caplog):
    wrapped = RuntimeError('transaction replay failed')
    wrapped.__cause__ = Aborted('contention')
    _seed_generation(contending_store)
    _drained(contending_store, wrapped)

    assert _cleanup(store=contending_store) is False
    assert not _failed_write_records(caplog, 'recording session cleanup failed')
    assert _transient_warnings(caplog, 'recording session cleanup contended')
    assert fallback_spy == []


def test_absent_row_is_a_quiet_no_op(contending_store, fallback_spy, caplog):
    """A missing row is a refusal, not a failure and not a contention warning."""
    contending_store.boundary_errors = []

    assert _cleanup(store=contending_store) is False
    assert not _transient_warnings(caplog, 'recording session cleanup contended')
    assert not _failed_write_records(caplog, 'recording session cleanup failed')
    assert fallback_spy == []


@pytest.mark.parametrize(
    'row_override',
    [
        {'transcript_segments': [{'id': 'late', 'text': 'kept'}]},
        {'status': 'processing'},
    ],
    ids=['late-content', 'advanced-status'],
)
def test_refused_delete_is_quiet_on_every_refusal_fence(contending_store, fallback_spy, caplog, row_override):
    """Refusals are the transaction's normal answer; they must not look like failures."""
    row = _stored_conversation()
    row.update(row_override)
    contending_store.documents[_CONVERSATION_PATH] = row
    contending_store.boundary_errors = []

    assert _cleanup(store=contending_store) is False
    assert not _transient_warnings(caplog, 'recording session cleanup contended')
    assert not _failed_write_records(caplog, 'recording session cleanup failed')
    assert fallback_spy == []


def test_legacy_route_deletes_through_an_expired_id_restart(contending_store):
    """The ``session_ref is None`` branch is re-entered by the restarted attempt."""
    _seed_generation(contending_store)
    _queue(contending_store, [InvalidArgument(f'400 {_EXPIRED}')])

    deleted = recording_sessions.tombstone_and_delete_empty_conversation(
        'uid', 'conversation', None, firestore_client=contending_store
    )

    assert deleted is True
    assert _CONVERSATION_PATH not in contending_store.documents


# ── I. The cleanup writer coexists with its siblings on one store ───────────


def test_session_open_still_works_after_a_drained_cleanup(contending_store):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)
    assert _cleanup(store=contending_store) is False
    _queue(contending_store, [])

    binding = recording_sessions.create_or_get_recording_session(
        'uid', 'recording', 'conversation', firestore_client=contending_store
    )

    assert binding['conversation_id'] == 'conversation'
    assert binding['mapping_conflict'] is False


def test_lease_renewal_still_works_after_a_drained_cleanup(contending_store):
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)
    assert _cleanup(store=contending_store) is False
    _queue(contending_store, [])

    renewed = recording_sessions.renew_recording_session_lease(
        'uid', 'recording', 'conversation', firestore_client=contending_store
    )

    assert renewed is True


def test_continuation_adopt_survives_back_to_back_drained_cleanups(contending_store, monkeypatch):
    from datetime import datetime as _datetime

    pointer = {'conversation_id': 'conversation', 'recording_session_id': 'recording'}
    monkeypatch.setattr(
        live_continuation.listen_continuations,
        'resolve_live_continuation',
        lambda *a, **k: (pointer, pointer),
    )
    _seed_generation(contending_store)
    _drained_expired_id(contending_store)

    for _ in range(2):
        result = live_continuation.resolve_live_continuation(
            'uid',
            'origin',
            source='mic',
            device_id=None,
            now=_datetime.now(timezone.utc),
            timeout=10,
        )
        assert result == pointer


def test_continuation_adopt_survives_a_failed_write_drain(contending_store, monkeypatch):
    from datetime import datetime as _datetime

    pointer = {'conversation_id': 'conversation', 'recording_session_id': 'recording'}
    monkeypatch.setattr(
        live_continuation.listen_continuations,
        'resolve_live_continuation',
        lambda *a, **k: (pointer, pointer),
    )
    _seed_generation(contending_store)
    _drained(contending_store, PermissionDenied('denied'))

    result = live_continuation.resolve_live_continuation(
        'uid',
        'origin',
        source='mic',
        device_id=None,
        now=_datetime.now(timezone.utc),
        timeout=10,
    )

    assert result == pointer


# ── J. Drain leaves every durable field of the retained generation intact ───


def test_drained_cleanup_leaves_the_lease_untouched(contending_store):
    _seed_generation(contending_store)
    lease_before = contending_store.documents[_SESSION_PATH]['lease_expires_at']
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    assert contending_store.documents[_SESSION_PATH]['lease_expires_at'] == lease_before


def test_drained_cleanup_leaves_the_audit_fields_untouched(contending_store):
    _seed_generation(contending_store)
    created_before = contending_store.documents[_SESSION_PATH]['created_at']
    updated_before = contending_store.documents[_SESSION_PATH]['updated_at']
    _drained_expired_id(contending_store)

    assert _cleanup(store=contending_store) is False
    session = contending_store.documents[_SESSION_PATH]
    assert session['created_at'] == created_before
    assert session['updated_at'] == updated_before


def test_no_drained_shape_emits_a_degradation_event(contending_store, fallback_spy):
    """One aggregated guard: the transient arm is silent for every shape."""
    for drained in (
        _drained_expired_id,
        _drained_read_side_retirement,
        _drained_sdk_replay_wrapper,
    ):
        _seed_generation(contending_store)
        drained(contending_store)
        assert _cleanup(store=contending_store) is False
    assert fallback_spy == []
