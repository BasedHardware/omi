"""Behavioral contract for the stranded-BYOK finalization job abandonment sweep.

Production defect: a ``requires_byok`` job is executable only inside a live
pusher session that presents the user's request-scoped keys.  Both BYOK
transitions delete ``reconcile_after_at`` on purpose, so the row is invisible to
the credential-free replay query, and the Cloud Tasks worker separately refuses
``requires_byok`` jobs.  Once the session ends nothing owns the row: it sits in
``queued`` forever and the conversation it binds can sit on ``processing``
forever with it.

These tests pin the disposition contract:

* the sweep is disposition and visibility only -- it never replays a BYOK
  finalization and never substitutes Omi platform credentials,
* ``blocked_byok``, fresh, live-leased, and unknown-age rows are never
  terminalized,
* an unownable row reaches exactly one honest terminal through a
  generation/ownership fence, with its own ``byok_session_abandoned`` code,
* the bound conversation is closed only when it is still ``processing`` and
  still bound to this exact job (an already-finalized conversation leaves an
  orphan job row that only needs its own terminal),
* projection shard deltas stay correct, since the projection is the metric
  source of truth, and
* work is bounded per invocation and eventually complete through a persisted,
  rotated CAS cursor.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

from database import conversation_finalization_jobs as jobs
from services import conversation_finalization as service

_NOW = datetime(2026, 8, 25, tzinfo=timezone.utc)
_ABANDONED_AFTER = timedelta(days=7)
_STRANDED_AT = _NOW - timedelta(days=30)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Ref:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self.data = data

    def get(self, transaction=None):
        if transaction is not None:
            transaction.record_read()
        return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)


class _Collection:
    def __init__(self, refs: dict[str, _Ref] | None = None):
        self.refs = refs or {}

    def document(self, doc_id: str) -> _Ref:
        return self.refs.setdefault(doc_id, _Ref(doc_id, None))


class _OrderedTransaction:
    """Records writes and rejects a read issued after the first write."""

    def __init__(self):
        self.updates: list[tuple[_Ref, dict]] = []
        self.sets: list[tuple[_Ref, dict]] = []
        self.read_after_write = False

    def record_read(self) -> None:
        if self.updates or self.sets:
            self.read_after_write = True

    def update(self, ref, data):
        self.updates.append((ref, data))

    def set(self, ref, data, **_kwargs):
        self.sets.append((ref, data))


class _JobSnapshot:
    def __init__(self, job_id: str, data: dict):
        self.id = job_id
        self.exists = True
        self._data = dict(data)
        self.reference = SimpleNamespace(path=f'{jobs.FINALIZATION_JOBS_COLLECTION}/{job_id}')

    def to_dict(self) -> dict:
        return dict(self._data)


class _JobsQuery:
    """Fake jobs query: one equality filter plus cursor pagination."""

    def __init__(self, collection: '_JobsCollection'):
        self._collection = collection
        self._limit: int | None = None
        self._after: _JobSnapshot | None = None

    def limit(self, value: int) -> '_JobsQuery':
        self._collection.limit_calls.append(value)
        self._limit = value
        return self

    def start_after(self, snapshot) -> '_JobsQuery':
        self._collection.start_after_calls.append(snapshot)
        self._after = snapshot
        return self

    def order_by(self, *args, **kwargs):  # pragma: no cover - must never be needed
        self._collection.order_by_calls += 1
        return self

    def stream(self):
        rows = list(self._collection.snapshots)
        if self._after is not None:
            rows = rows[rows.index(self._after) + 1 :]
        if self._limit is not None:
            rows = rows[: self._limit]
        return rows


class _JobsCollection:
    def __init__(self, snapshots: list[_JobSnapshot]):
        self.snapshots = snapshots
        self.where_filters: list[Any] = []
        self.limit_calls: list[int] = []
        self.start_after_calls: list[Any] = []
        self.order_by_calls = 0

    def where(self, *args, filter=None, **kwargs) -> _JobsQuery:
        self.where_filters.append(filter)
        return _JobsQuery(self)


class _JobsClient:
    def __init__(self, snapshots: list[_JobSnapshot]):
        self.collection_obj = _JobsCollection(snapshots)
        self.collection_group_calls: list[str] = []
        self.document_paths: list[str] = []

    def collection(self, name: str) -> _JobsCollection:
        assert name == jobs.FINALIZATION_JOBS_COLLECTION
        return self.collection_obj

    def collection_group(self, name: str):  # pragma: no cover - must never be needed
        self.collection_group_calls.append(name)
        raise AssertionError('the byok abandonment sweep is a collection-scoped query')

    def document(self, path: str):
        self.document_paths.append(path)
        for snapshot in self.collection_obj.snapshots:
            if snapshot.reference.path == path:
                return SimpleNamespace(get=lambda snapshot=snapshot: snapshot)
        # A vanished cursor document wraps the sweep back to the top.
        return SimpleNamespace(get=lambda: SimpleNamespace(exists=False))


def _stranded_job(
    job_id: str = 'job-1',
    *,
    status: str = 'queued',
    requires_byok: bool = True,
    updated_at: datetime | None = _STRANDED_AT,
    lease_expires_at: datetime | None = None,
    **extra,
) -> dict:
    data: dict = {
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'finalization_revision': 2,
        'status': status,
        'requires_byok': requires_byok,
        'dispatch_generation': 1,
        'lease_epoch': 0,
        'created_at': _STRANDED_AT,
        'projection_generation': jobs.FINALIZATION_PROJECTION_GENERATION,
        'projection_shard': jobs._projection_shard(job_id),
    }
    if updated_at is not None:
        data['updated_at'] = updated_at
    if lease_expires_at is not None:
        data['lease_expires_at'] = lease_expires_at
    data.update(extra)
    return data


def _snapshot(job_id: str, **kwargs) -> _JobSnapshot:
    return _JobSnapshot(job_id, _stranded_job(job_id, **kwargs))


def _bound_conversation(data: dict | None = None) -> _Ref:
    return _Ref(
        'conversation-1',
        {
            'status': 'processing',
            'discarded': False,
            'finalization_job_id': 'job-1',
            'finalization_revision': 2,
            **(data or {}),
        },
    )


def _abandon(transaction, job_ref, conversation_ref, *, projection=None, status='queued', generation=1, epoch=0):
    return jobs._abandon_byok_finalization_job_txn(
        transaction,
        job_ref,
        status,
        generation,
        epoch,
        _NOW - _ABANDONED_AFTER,
        _NOW,
        (lambda _uid, _conversation_id: conversation_ref) if conversation_ref is not None else None,
        projection,
    )


# ---------------------------------------------------------------------------
# Candidate selection
# ---------------------------------------------------------------------------


def test_candidate_query_is_a_single_field_equality_on_requires_byok():
    """One equality filter rides Firestore's automatic single-field index: no
    composite index is registered or deployed for this sweep."""
    client = _JobsClient([_snapshot('job-1')])

    jobs.get_abandoned_byok_job_candidates(abandoned_after=_ABANDONED_AFTER, limit=1000, firestore_client=client)

    collection = client.collection_obj
    assert len(collection.where_filters) == 1
    assert collection.where_filters[0].field_path == 'requires_byok'
    assert collection.where_filters[0].op_string == '=='
    assert collection.where_filters[0].value is True
    assert collection.order_by_calls == 0
    # The page size is capped regardless of the caller's requested limit.
    assert collection.limit_calls == [100]


def test_candidates_exclude_every_row_that_still_has_an_owner():
    now_ish = datetime.now(timezone.utc)
    client = _JobsClient(
        [
            # Still legitimately waiting for a live session to present keys, and
            # already visible on the blocked_byok gauge.
            _snapshot('blocked', status='blocked_byok'),
            _snapshot('completed', status='completed'),
            _snapshot('dead-letter', status='dead_letter'),
            # A live worker still owns this lease.
            _snapshot('live-lease', status='leased', lease_expires_at=now_ish + timedelta(minutes=20)),
            # Inside the reconnect window.
            _snapshot('fresh', updated_at=now_ish),
            # Age cannot be established: skipped rather than terminalized.
            _JobSnapshot('ageless', {'status': 'queued', 'requires_byok': True}),
            _snapshot('stranded'),
            _snapshot('expired-lease', status='leased', lease_expires_at=now_ish - timedelta(days=1)),
        ]
    )

    sweep = jobs.get_abandoned_byok_job_candidates(abandoned_after=_ABANDONED_AFTER, firestore_client=client)

    assert [candidate['job_id'] for candidate in sweep['candidates']] == ['stranded', 'expired-lease']
    assert sweep['exhausted'] is True
    assert sweep['resume_after_path'] is None


def test_candidates_page_past_excluded_rows_to_reach_a_later_stranded_row():
    """Client-side exclusion happens after the page cap, so a stable prefix of
    terminal rows must not starve a later stranded row."""
    client = _JobsClient(
        [_snapshot(f'terminal-{index}', status='completed') for index in range(5)] + [_snapshot('stranded')]
    )

    sweep = jobs.get_abandoned_byok_job_candidates(abandoned_after=_ABANDONED_AFTER, limit=2, firestore_client=client)

    assert [candidate['job_id'] for candidate in sweep['candidates']] == ['stranded']
    assert client.collection_obj.start_after_calls  # paged with a cursor


def test_candidates_bound_total_scan_and_persist_progress():
    client = _JobsClient([_snapshot(f'terminal-{index}', status='completed') for index in range(30)])

    sweep = jobs.get_abandoned_byok_job_candidates(
        abandoned_after=_ABANDONED_AFTER, limit=5, max_scan=10, firestore_client=client
    )

    assert sweep['candidates'] == []
    assert sweep['exhausted'] is False
    # The cursor persists this invocation's bounded progress for the next sweep.
    assert sweep['resume_after_path'] == f'{jobs.FINALIZATION_JOBS_COLLECTION}/terminal-9'


def test_sweep_resumes_from_the_persisted_cursor_and_wraps_when_it_vanishes():
    snapshots = [_snapshot('early', status='completed'), _snapshot('stranded')]
    client = _JobsClient(snapshots)

    resumed = jobs.get_abandoned_byok_job_candidates(
        abandoned_after=_ABANDONED_AFTER,
        resume_after_path=f'{jobs.FINALIZATION_JOBS_COLLECTION}/early',
        firestore_client=client,
    )
    assert [candidate['job_id'] for candidate in resumed['candidates']] == ['stranded']

    wrapped = jobs.get_abandoned_byok_job_candidates(
        abandoned_after=_ABANDONED_AFTER,
        resume_after_path=f'{jobs.FINALIZATION_JOBS_COLLECTION}/deleted-row',
        firestore_client=client,
    )
    assert [candidate['job_id'] for candidate in wrapped['candidates']] == ['stranded']


def test_abandonment_delay_is_clamped_to_a_safe_floor_and_ceiling(monkeypatch):
    monkeypatch.delenv('LISTEN_FINALIZATION_BYOK_ABANDONED_SECONDS', raising=False)
    assert jobs.get_byok_abandoned_after() == timedelta(seconds=jobs.DEFAULT_BYOK_ABANDONED_AFTER_SECONDS)

    monkeypatch.setenv('LISTEN_FINALIZATION_BYOK_ABANDONED_SECONDS', '5')
    assert jobs.get_byok_abandoned_after() == timedelta(days=1)

    monkeypatch.setenv('LISTEN_FINALIZATION_BYOK_ABANDONED_SECONDS', str(10 * 365 * 86_400))
    assert jobs.get_byok_abandoned_after() == timedelta(days=90)

    monkeypatch.setenv('LISTEN_FINALIZATION_BYOK_ABANDONED_SECONDS', 'not-a-number')
    assert jobs.get_byok_abandoned_after() == timedelta(seconds=jobs.DEFAULT_BYOK_ABANDONED_AFTER_SECONDS)


# ---------------------------------------------------------------------------
# Terminal disposition
# ---------------------------------------------------------------------------


def test_stranded_job_and_its_processing_conversation_reach_one_atomic_terminal():
    transaction = _OrderedTransaction()
    job_ref = _Ref('job-1', _stranded_job())
    conversation_ref = _bound_conversation()
    projection = _Collection()

    disposition = _abandon(transaction, job_ref, conversation_ref, projection=projection)

    assert disposition == {'status': 'abandoned', 'conversation_outcome': 'closed'}
    job_update = transaction.updates[0][1]
    assert transaction.updates[0][0] is job_ref
    assert job_update['status'] == 'dead_letter'
    assert job_update['terminal_outcome'] == 'failure'
    # A distinct code: this job was never attempted, it was abandoned.
    assert job_update['last_failure_code'] == jobs.BYOK_ABANDONED_FAILURE_CODE
    assert job_update['finalization_outcome'] == jobs.BYOK_ABANDONED_FAILURE_CODE
    assert job_update['reconcile_after_at'] is jobs.firestore.DELETE_FIELD
    # Nothing was ever delivered to an external integration.
    assert job_update['fanout_status'] == 'fenced'
    # The customer is taken off `processing` in the same transaction, and the
    # recording stays retrievable and reprocessable rather than discarded.
    assert transaction.updates[1] == (conversation_ref, {'status': 'completed', 'finalization_status': 'dead_letter'})
    # Firestore requires every transactional read before the first write.
    assert transaction.read_after_write is False


def test_terminal_moves_the_projection_shard_deltas():
    projection = _Collection()
    transaction = _OrderedTransaction()

    _abandon(transaction, _Ref('job-1', _stranded_job()), _bound_conversation(), projection=projection)

    shard_ref, fields = transaction.sets[0]
    assert shard_ref.id == jobs._projection_shard_id(
        jobs.FINALIZATION_PROJECTION_GENERATION, jobs._projection_shard('job-1')
    )
    assert {name: value.value for name, value in fields.items() if hasattr(value, 'value')} == {
        'queued': -1,
        'dead_letter': 1,
        'failure': 1,
    }


def test_expired_lease_terminal_moves_the_leased_delta_not_the_queued_one():
    projection = _Collection()
    transaction = _OrderedTransaction()
    job = _stranded_job(status='leased', lease_expires_at=_NOW - timedelta(days=1))

    disposition = _abandon(
        transaction, _Ref('job-1', job), _bound_conversation(), projection=projection, status='leased'
    )

    assert disposition['status'] == 'abandoned'
    _shard_ref, fields = transaction.sets[0]
    assert {name: value.value for name, value in fields.items() if hasattr(value, 'value')} == {
        'leased': -1,
        'dead_letter': 1,
        'failure': 1,
    }


def test_already_finalized_conversation_leaves_only_the_orphan_job_row_to_close():
    """Many stranded rows bind a conversation the inline pusher lane finalized
    fine. That job row is orphaned bookkeeping: close it, touch nothing else."""
    transaction = _OrderedTransaction()
    conversation_ref = _bound_conversation({'status': 'completed'})

    disposition = _abandon(transaction, _Ref('job-1', _stranded_job()), conversation_ref)

    assert disposition == {'status': 'abandoned', 'conversation_outcome': 'already_terminal'}
    assert [ref for ref, _update in transaction.updates] == [transaction.updates[0][0]]
    assert conversation_ref not in [ref for ref, _update in transaction.updates]


def test_deferred_desktop_row_keeps_its_own_lane(monkeypatch):
    """A deferred row intentionally stays on `processing`, owned by its own lane."""
    transaction = _OrderedTransaction()
    conversation_ref = _bound_conversation({'deferred': True})

    disposition = _abandon(transaction, _Ref('job-1', _stranded_job()), conversation_ref)

    assert disposition == {'status': 'abandoned', 'conversation_outcome': 'deferred'}
    assert conversation_ref not in [ref for ref, _update in transaction.updates]


def test_conversation_bound_to_a_newer_generation_is_never_touched():
    transaction = _OrderedTransaction()
    conversation_ref = _bound_conversation({'finalization_job_id': 'job-2', 'finalization_revision': 3})

    disposition = _abandon(transaction, _Ref('job-1', _stranded_job()), conversation_ref)

    assert disposition == {'status': 'abandoned', 'conversation_outcome': 'unbound'}
    assert conversation_ref not in [ref for ref, _update in transaction.updates]


def test_a_live_session_that_came_back_fences_the_abandonment():
    """The scanned generation is the fence: a resumed or re-claimed job wins."""
    conversation_ref = _bound_conversation()

    resumed_lease = _OrderedTransaction()
    assert _abandon(
        resumed_lease,
        _Ref('job-1', _stranded_job(status='leased', lease_expires_at=_NOW + timedelta(minutes=20))),
        conversation_ref,
        status='leased',
    ) == {'status': 'fenced', 'conversation_outcome': 'none'}
    assert resumed_lease.updates == []

    reclaimed = _OrderedTransaction()
    assert _abandon(reclaimed, _Ref('job-1', _stranded_job(lease_epoch=4)), conversation_ref) == {
        'status': 'fenced',
        'conversation_outcome': 'none',
    }
    assert reclaimed.updates == []

    replayed = _OrderedTransaction()
    assert _abandon(replayed, _Ref('job-1', _stranded_job(dispatch_generation=7)), conversation_ref) == {
        'status': 'fenced',
        'conversation_outcome': 'none',
    }
    assert replayed.updates == []

    status_moved = _OrderedTransaction()
    assert _abandon(status_moved, _Ref('job-1', _stranded_job(status='leased')), conversation_ref)['status'] == 'fenced'
    assert status_moved.updates == []


def test_blocked_fresh_platform_and_missing_rows_are_never_terminalized():
    conversation_ref = _bound_conversation()

    for job in (
        # Still waiting for a live session to present keys.
        _stranded_job(status='blocked_byok'),
        # Platform-key job: owned by the Cloud Tasks worker and the reconciler.
        _stranded_job(requires_byok=False),
        # Inside the reconnect window.
        _stranded_job(updated_at=_NOW),
        # Terminal already.
        _stranded_job(status='dead_letter'),
    ):
        transaction = _OrderedTransaction()
        assert (
            _abandon(transaction, _Ref('job-1', job), conversation_ref, status=str(job['status']))['status'] == 'fenced'
        )
        assert transaction.updates == []
        assert transaction.sets == []

    missing = _OrderedTransaction()
    assert _abandon(missing, _Ref('job-1', None), conversation_ref) == {
        'status': 'missing',
        'conversation_outcome': 'none',
    }
    assert missing.updates == []


# ---------------------------------------------------------------------------
# Service sweep
# ---------------------------------------------------------------------------


def _install(monkeypatch, candidates, *, exhausted: bool = True, resume_after_path: str | None = None):
    monkeypatch.setenv('LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED', 'true')
    monkeypatch.setattr(service.jobs_db, 'get_byok_abandoned_after', lambda: _ABANDONED_AFTER)
    monkeypatch.setattr(
        service.jobs_db,
        'get_byok_abandonment_sweep_cursor',
        lambda **kwargs: {'resume_after_path': None, 'generation': 3},
    )
    advance = MagicMock(return_value=True)
    monkeypatch.setattr(service.jobs_db, 'advance_byok_abandonment_sweep_cursor', advance)
    monkeypatch.setattr(
        service.jobs_db,
        'get_abandoned_byok_job_candidates',
        lambda **kwargs: {
            'candidates': list(candidates),
            'resume_after_path': resume_after_path,
            'exhausted': exhausted,
        },
    )
    abandon = MagicMock(return_value={'status': 'abandoned', 'conversation_outcome': 'closed'})
    monkeypatch.setattr(service.jobs_db, 'abandon_byok_finalization_job', abandon)
    monkeypatch.setattr(service, '_record_byok_abandonment_journey', MagicMock())
    return advance, abandon


def _candidate(job_id: str = 'job-1', **extra) -> dict:
    return _stranded_job(job_id, **extra) | {'job_id': job_id}


def test_sweep_is_on_by_default(monkeypatch):
    """No environment can rehearse this sweep, so it ships on.

    dev holds zero BYOK jobs, so an off-by-default flag would defer the
    disposition of stranded rows indefinitely without buying any evidence. The
    bounded age is the safety control, not the switch.
    """
    _advance, abandon = _install(monkeypatch, [_candidate()])
    monkeypatch.delenv('LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED', raising=False)

    assert service.reconcile_abandoned_byok_finalization_jobs()['abandoned'] == 1
    abandon.assert_called_once()


def test_sweep_can_be_switched_off(monkeypatch):
    """The flag still exists to stop the sweep in an incident."""
    monkeypatch.setenv('LISTEN_FINALIZATION_BYOK_ABANDONMENT_ENABLED', 'false')
    query = MagicMock()
    monkeypatch.setattr(service.jobs_db, 'get_abandoned_byok_job_candidates', query)

    assert service.reconcile_abandoned_byok_finalization_jobs() == {
        'abandoned': 0,
        'conversations_closed': 0,
        'skipped': 0,
        'error': 0,
    }
    query.assert_not_called()


def test_default_abandonment_age_is_fourteen_days():
    assert jobs.DEFAULT_BYOK_ABANDONED_AFTER_SECONDS == 14 * 86_400


def test_enabled_sweep_terminalizes_through_the_scanned_generation_fence(monkeypatch):
    _advance, abandon = _install(monkeypatch, [_candidate(lease_epoch=2, dispatch_generation=4)])

    result = service.reconcile_abandoned_byok_finalization_jobs()

    assert result == {'abandoned': 1, 'conversations_closed': 1, 'skipped': 0, 'error': 0}
    abandon.assert_called_once_with(
        'job-1',
        expected_status='queued',
        expected_dispatch_generation=4,
        expected_lease_epoch=2,
        abandoned_after=_ABANDONED_AFTER,
        firestore_client=None,
    )


def test_orphan_bookkeeping_row_is_abandoned_without_a_conversation_close(monkeypatch):
    _advance, abandon = _install(monkeypatch, [_candidate()])
    abandon.return_value = {'status': 'abandoned', 'conversation_outcome': 'already_terminal'}

    result = service.reconcile_abandoned_byok_finalization_jobs()

    assert result == {'abandoned': 1, 'conversations_closed': 0, 'skipped': 0, 'error': 0}


def test_sweep_never_replays_a_byok_job_with_platform_credentials(monkeypatch):
    """The product rule: a blocked/stranded BYOK job is never finalized with Omi
    credentials. This sweep only disposes of the row."""
    _advance, _abandon = _install(monkeypatch, [_candidate()])
    replay = MagicMock()
    enqueue = MagicMock()
    claim = MagicMock()
    monkeypatch.setattr(service.jobs_db, 'claim_finalization_replay', replay)
    monkeypatch.setattr(service.jobs_db, 'claim_finalization_job', claim)
    monkeypatch.setattr(service, 'enqueue_listen_finalization_job', enqueue)

    service.reconcile_abandoned_byok_finalization_jobs()

    replay.assert_not_called()
    claim.assert_not_called()
    enqueue.assert_not_called()


def test_fence_loss_is_a_skip_not_an_error(monkeypatch):
    _advance, abandon = _install(monkeypatch, [_candidate()])
    abandon.return_value = {'status': 'fenced', 'conversation_outcome': 'none'}

    assert service.reconcile_abandoned_byok_finalization_jobs() == {
        'abandoned': 0,
        'conversations_closed': 0,
        'skipped': 1,
        'error': 0,
    }


def test_unexpected_per_row_exception_is_an_error_not_a_skip(monkeypatch):
    _advance, abandon = _install(monkeypatch, [_candidate()])
    abandon.side_effect = RuntimeError('firestore unavailable')

    assert service.reconcile_abandoned_byok_finalization_jobs() == {
        'abandoned': 0,
        'conversations_closed': 0,
        'skipped': 0,
        'error': 1,
    }


def test_query_failure_is_fail_closed(monkeypatch):
    _install(monkeypatch, [])
    monkeypatch.setattr(
        service.jobs_db,
        'get_abandoned_byok_job_candidates',
        MagicMock(side_effect=RuntimeError('query failed')),
    )

    assert service.reconcile_abandoned_byok_finalization_jobs() == {
        'abandoned': 0,
        'conversations_closed': 0,
        'skipped': 0,
        'error': 1,
    }


def test_sweep_advances_and_rotates_the_cursor_with_its_cas_generation(monkeypatch):
    advance, _abandon = _install(monkeypatch, [], exhausted=False, resume_after_path='jobs/last')
    service.reconcile_abandoned_byok_finalization_jobs()
    advance.assert_called_once_with(3, 'jobs/last', firestore_client=None)

    advance, _abandon = _install(monkeypatch, [], exhausted=True, resume_after_path='jobs/last')
    service.reconcile_abandoned_byok_finalization_jobs()
    # Exhausted: rotate the next sweep back to the top.
    advance.assert_called_once_with(3, None, firestore_client=None)


def test_outcomes_increment_the_privacy_safe_disposition_counter(monkeypatch):
    _advance, abandon = _install(monkeypatch, [_candidate()])
    labels = MagicMock()
    monkeypatch.setattr(service.LISTEN_FINALIZATION_BYOK_ABANDONMENTS_TOTAL, 'labels', labels)

    service.reconcile_abandoned_byok_finalization_jobs()
    assert labels.call_args_list[0].kwargs == {'outcome': 'abandoned_conversation_closed'}

    abandon.return_value = {'status': 'abandoned', 'conversation_outcome': 'missing'}
    labels.reset_mock()
    service.reconcile_abandoned_byok_finalization_jobs()
    assert labels.call_args_list[0].kwargs == {'outcome': 'abandoned_bookkeeping'}
