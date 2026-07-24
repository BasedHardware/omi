"""Behavioral contract tests for the durable listen finalization job state machine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from google.api_core.exceptions import Aborted

from database import conversation_finalization_jobs as jobs
from database import firestore_transaction_retry


class _PhotoCollection:
    def __init__(self, has_photo: bool):
        self.has_photo = has_photo

    def limit(self, count: int):
        assert count == 1
        return self

    def stream(self, transaction=None):
        del transaction
        return iter([SimpleNamespace()] if self.has_photo else [])


class _Ref:
    def __init__(self, doc_id: str, data: dict | None, *, has_legacy_photo: bool = False):
        self.id = doc_id
        self.data = data
        self.has_legacy_photo = has_legacy_photo

    def get(self, transaction=None):
        del transaction
        return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

    def to_dict(self):
        return self.data

    def collection(self, name: str):
        assert name == 'photos'
        return _PhotoCollection(self.has_legacy_photo)


class _Collection:
    def __init__(self, refs: dict[str, _Ref]):
        self.refs = refs

    def document(self, doc_id: str):
        return self.refs.setdefault(doc_id, _Ref(doc_id, None))


class _Transaction:
    def __init__(self):
        self.updates: list[tuple[_Ref, dict]] = []
        self.sets: list[tuple[_Ref, dict]] = []

    def update(self, ref, data):
        self.updates.append((ref, data))

    def set(self, ref, data):
        self.sets.append((ref, data))


def _now() -> datetime:
    return datetime(2026, 7, 13, tzinfo=timezone.utc)


def _conversation(data: dict | None = None, *, has_legacy_photo: bool = False) -> _Ref:
    return _Ref(
        'conversation-1',
        {
            'status': 'in_progress',
            'transcript_segments': [{'text': 'persisted'}],
            **(data or {}),
        },
        has_legacy_photo=has_legacy_photo,
    )


def _completed_finalization_conversation(job_id: str = 'job-1', revision: int = 1, data: dict | None = None) -> _Ref:
    return _conversation(
        {
            'status': 'completed',
            'discarded': False,
            'finalization_job_id': job_id,
            'finalization_revision': revision,
            **(data or {}),
        }
    )


def _admit_finalization(_conversation_data: dict) -> jobs.FinalizationAdmission:
    return {
        'accepted': True,
        'terminal': False,
        'reason': 'accepted',
        'fanout_key': 'fanout-key',
    }


def test_intent_persists_outbox_before_any_live_handoff_and_omits_byok_material():
    transaction = _Transaction()
    conversation_ref = _conversation()
    collection = _Collection({})

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        'uid-1',
        'conversation-1',
        False,
        _admit_finalization,
        _now(),
    )

    assert intent['status'] == 'queued'
    assert intent['job_id']
    assert len(transaction.sets) == 1
    job = transaction.sets[0][1]
    assert job['uid'] == 'uid-1'
    assert job['conversation_id'] == 'conversation-1'
    assert job['dispatch_generation'] == 1
    assert job['status'] == 'queued'
    assert job['fanout_key'] == 'fanout-key'
    assert job['fanout_status'] == 'pending'
    forbidden = {'byok_keys', 'transcript', 'transcript_segments', 'authorization', 'raw_error'}
    assert forbidden.isdisjoint(job)
    assert transaction.updates[0][1]['status'] == 'processing'
    assert transaction.updates[0][1]['finalization_job_id'] == intent['job_id']


def test_rest_intent_persists_its_force_mode_and_calendar_context_atomically():
    transaction = _Transaction()
    conversation_ref = _conversation()
    collection = _Collection({})

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        'uid-1',
        'conversation-1',
        False,
        _admit_finalization,
        _now(),
        force_process=True,
        extra_updates={'external_data': {'calendar_meeting_context': {'event_id': 'event-1'}}},
    )

    assert transaction.sets[0][1]['force_process'] is True
    assert transaction.updates == [
        (
            conversation_ref,
            {
                'external_data': {'calendar_meeting_context': {'event_id': 'event-1'}},
                'status': 'processing',
                'finalization_job_id': intent['job_id'],
                'finalization_revision': 1,
                'finalization_status': 'queued',
            },
        )
    ]


def test_create_or_get_intent_retries_read_contention_with_a_fresh_transaction(monkeypatch):
    """Concurrent REST finalizers must recover a read-time Firestore abort."""

    conversation_ref = _conversation()
    jobs_collection = _Collection({})
    transactions: list[_Transaction] = []

    class _Client:
        def transaction(self):
            transaction = _Transaction()
            transactions.append(transaction)
            return transaction

        def collection(self, name: str):
            assert name == jobs.FINALIZATION_JOBS_COLLECTION
            return jobs_collection

    transactional_calls = 0

    def transaction_wrapper(function):
        def invoke(transaction, *args, **kwargs):
            nonlocal transactional_calls
            transactional_calls += 1
            if transactional_calls == 1:
                raise Aborted('read contention')
            return function(transaction, *args, **kwargs)

        return invoke

    def fast_contention_retry(transaction_factory, operation, **kwargs):
        return firestore_transaction_retry.run_with_transaction_contention_retry(
            transaction_factory,
            operation,
            **kwargs,
            sleep=lambda _delay: None,
            random_value=lambda: 0.0,
        )

    monkeypatch.setattr(jobs, '_conversation_ref', lambda *_args: conversation_ref)
    monkeypatch.setattr(jobs.firestore, 'transactional', transaction_wrapper)
    monkeypatch.setattr(jobs, 'run_with_transaction_contention_retry', fast_contention_retry)

    intent = jobs.create_or_get_finalization_intent(
        'uid-1',
        'conversation-1',
        requires_byok=False,
        finalization_admission=_admit_finalization,
        firestore_client=_Client(),
    )

    assert transactional_calls == 2
    assert len(transactions) == 2
    assert transactions[0] is not transactions[1]
    assert intent['status'] == 'queued'
    assert len(transactions[1].sets) == 1


def test_photo_only_conversation_with_durable_content_marker_is_admitted():
    transaction = _Transaction()
    conversation_ref = _conversation({'transcript_segments': [], 'has_content': True})
    collection = _Collection({})

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        'uid-1',
        'conversation-1',
        False,
        _admit_finalization,
        _now(),
    )

    assert intent['status'] == 'queued'
    assert len(transaction.sets) == 1
    assert transaction.updates[0][1]['status'] == 'processing'


def test_legacy_photo_only_conversation_is_admitted_from_its_child_document():
    transaction = _Transaction()
    conversation_ref = _conversation({'transcript_segments': [], 'has_content': False}, has_legacy_photo=True)
    collection = _Collection({})

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        'uid-1',
        'conversation-1',
        False,
        _admit_finalization,
        _now(),
    )

    assert intent['status'] == 'queued'
    assert transaction.updates[0][1]['status'] == 'processing'


def test_duplicate_reconnect_reuses_the_same_outbox_job():
    job_id = 'job-1'
    transaction = _Transaction()
    conversation_ref = _conversation(
        {'status': 'processing', 'finalization_job_id': job_id, 'finalization_revision': 1}
    )
    collection = _Collection(
        {
            job_id: _Ref(
                job_id,
                {'status': 'queued', 'dispatch_generation': 1, 'requires_byok': False},
            )
        }
    )

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        'uid-1',
        'conversation-1',
        False,
        _admit_finalization,
        _now(),
    )

    assert intent == {
        'job_id': job_id,
        'status': 'queued',
        'dispatch_generation': 1,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }
    assert transaction.sets == []
    assert transaction.updates == []


def test_duplicate_finalization_intent_keeps_the_same_processing_admission():
    """Characterize #2d67863cad: a disconnect/reconnect never starts a second job.

    The first finalization transaction already moved the conversation to
    ``processing``.  A later finalizer must reuse that durable identity without
    another conversation write, so a future service migration cannot re-open
    the disconnect race while rearranging the handoff.
    """
    job_id = 'job-1'
    transaction = _Transaction()
    conversation_ref = _conversation(
        {
            'status': 'processing',
            'finalization_job_id': job_id,
            'finalization_revision': 1,
        }
    )
    collection = _Collection(
        {
            job_id: _Ref(
                job_id,
                {
                    'status': 'queued',
                    'dispatch_generation': 1,
                    'requires_byok': False,
                },
            )
        }
    )

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        'uid-1',
        'conversation-1',
        False,
        _admit_finalization,
        _now(),
    )

    assert intent['job_id'] == job_id
    assert intent['dispatch_generation'] == 1
    assert transaction.updates == []
    assert transaction.sets == []


def test_byok_job_is_explicitly_blocked_without_persisting_a_key():
    transaction = _Transaction()
    collection = _Collection({})

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        _conversation(),
        collection,
        'uid-1',
        'conversation-1',
        True,
        _admit_finalization,
        _now(),
    )

    assert intent['status'] == 'blocked_byok'
    persisted = transaction.sets[0][1]
    assert persisted['requires_byok'] is True
    assert set(persisted).isdisjoint({'byok_keys', 'openai', 'anthropic', 'gemini', 'deepgram'})


def test_atomic_admission_rejects_terminal_snapshot_before_any_outbox_write():
    transaction = _Transaction()
    conversation_ref = _conversation({'status': 'failed'})
    collection = _Collection({})

    def terminal(_conversation_data: dict) -> jobs.FinalizationAdmission:
        return {'accepted': False, 'terminal': True, 'reason': 'terminal', 'fanout_key': None}

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        collection,
        'uid-1',
        'conversation-1',
        False,
        terminal,
        _now(),
    )

    assert intent['status'] == 'terminal'
    assert transaction.sets == []
    assert transaction.updates == []


def test_duplicate_task_delivery_claims_only_once_until_lease_expires():
    now = _now()
    ref = _Ref('job-1', {'status': 'queued', 'dispatch_generation': 2, 'attempt_count': 0})
    first = _Transaction()

    claim = jobs._claim_finalization_job_txn(first, ref, 2, False, 1500, now)
    assert claim == {'status': 'claimed', 'lease_epoch': 1, 'attempt_count': 1, 'created_at': None}
    claim_update = first.updates[0][1]
    assert claim_update['status'] == 'leased'
    assert claim_update['attempt_count'] == 1

    ref.data = ref.data | claim_update
    duplicate = _Transaction()
    assert jobs._claim_finalization_job_txn(duplicate, ref, 2, False, 1500, now + timedelta(seconds=1)) == {
        'status': 'leased',
        'lease_epoch': None,
        'attempt_count': 0,
        'created_at': None,
    }
    assert duplicate.updates == []


def test_expired_worker_lease_can_be_safely_reclaimed():
    now = _now()
    ref = _Ref(
        'job-1',
        {
            'status': 'leased',
            'dispatch_generation': 2,
            'attempt_count': 1,
            'lease_expires_at': now - timedelta(seconds=1),
        },
    )
    transaction = _Transaction()

    claim = jobs._claim_finalization_job_txn(transaction, ref, 2, False, 1500, now)
    assert claim == {'status': 'claimed', 'lease_epoch': 1, 'attempt_count': 2, 'created_at': None}
    assert transaction.updates[0][1]['attempt_count'] == 2
    assert transaction.updates[0][1]['lease_epoch'] == 1


def test_finalization_completion_requires_durable_fanout_completion():
    now = _now()
    ref = _Ref(
        'job-1',
        {
            'status': 'leased',
            'dispatch_generation': 1,
            'lease_epoch': 4,
            'fanout_status': 'pending',
            'uid': 'uid-1',
            'conversation_id': 'conversation-1',
            'finalization_revision': 1,
        },
    )

    blocked = _Transaction()
    assert jobs._mark_finalization_completed_txn(blocked, ref, 1, 4, now) is False
    assert blocked.updates == []

    fanout = _Transaction()
    conversation_ref = _completed_finalization_conversation()
    claim = jobs._claim_finalization_fanout_txn(fanout, ref, 1, 4, now, lambda *_: conversation_ref)
    assert claim == {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization:1'}
    ref.data = ref.data | fanout.updates[0][1]

    completed_fanout = _Transaction()
    assert jobs._mark_finalization_fanout_completed_txn(completed_fanout, ref, 1, 4, now) is True
    ref.data = ref.data | completed_fanout.updates[0][1]

    completed = _Transaction()
    assert jobs._mark_finalization_completed_txn(completed, ref, 1, 4, now) is True


def test_fanout_claim_terminally_fences_a_discard_that_wins_before_its_transaction():
    """A processor may finish while a disconnect discard wins the fanout race.

    Firestore retries this transaction if the conversation changes after its
    read. This fixture represents the retried transaction snapshot after that
    discard, which must both reject integrations and close the job rather than
    make it retryable or eligible for a dead letter.
    """
    now = _now()
    ref = _Ref(
        'job-1',
        {
            'status': 'leased',
            'dispatch_generation': 1,
            'lease_epoch': 4,
            'fanout_status': 'pending',
            'uid': 'uid-1',
            'conversation_id': 'conversation-1',
            'finalization_revision': 1,
        },
    )
    discarded_conversation = _completed_finalization_conversation(data={'discarded': True})
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        1,
        4,
        now,
        lambda *_: discarded_conversation,
    )

    assert claim == {'status': 'fenced', 'fanout_key': 'conversation:conversation-1:finalization:1'}
    assert transaction.updates == [(ref, jobs._fenced_finalization_update(now))]


def test_fanout_claim_terminally_fences_a_superseded_finalization_binding():
    now = _now()
    ref = _Ref(
        'job-1',
        {
            'status': 'leased',
            'dispatch_generation': 1,
            'lease_epoch': 4,
            'fanout_status': 'pending',
            'uid': 'uid-1',
            'conversation_id': 'conversation-1',
            'finalization_revision': 1,
        },
    )
    newer_conversation = _completed_finalization_conversation(job_id='job-2', revision=2)
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        1,
        4,
        now,
        lambda *_: newer_conversation,
    )

    assert claim == {'status': 'fenced', 'fanout_key': 'conversation:conversation-1:finalization:1'}
    assert transaction.updates == [(ref, jobs._fenced_finalization_update(now))]


def test_fenced_finalization_is_a_terminal_no_fanout_outcome():
    now = _now()
    ref = _Ref(
        'job-1',
        {
            'status': 'leased',
            'dispatch_generation': 1,
            'lease_epoch': 4,
            'fanout_status': 'pending',
        },
    )

    transaction = _Transaction()
    assert jobs._mark_finalization_fenced_txn(transaction, ref, 1, 4, now) is True
    update = transaction.updates[0][1]
    assert update['status'] == 'completed'
    assert update['finalization_outcome'] == 'fenced'
    assert update['fanout_status'] == 'fenced'


def test_completed_fenced_job_replays_as_a_fenced_result():
    ref = _Ref(
        'job-1',
        {
            'status': 'completed',
            'finalization_outcome': 'fenced',
            'dispatch_generation': 1,
        },
    )

    claim = jobs._claim_finalization_job_txn(_Transaction(), ref, 1, False, 1500, _now())

    assert claim == {'status': 'fenced', 'lease_epoch': None, 'attempt_count': 0, 'created_at': None}


def test_live_pusher_claim_cannot_use_another_conversations_job():
    transaction = _Transaction()
    ref = _Ref(
        'job-1',
        {
            'status': 'queued',
            'dispatch_generation': 1,
            'uid': 'owner-uid',
            'conversation_id': 'owner-conversation',
        },
    )

    status = jobs._claim_finalization_job_txn(
        transaction,
        ref,
        1,
        False,
        1500,
        _now(),
        expected_uid='other-uid',
        expected_conversation_id='other-conversation',
    )

    assert status == {'status': 'identity_mismatch', 'lease_epoch': None, 'attempt_count': 0, 'created_at': None}
    assert transaction.updates == []


def test_completed_and_dead_letter_jobs_never_execute_again():
    for status in ('completed', 'dead_letter'):
        transaction = _Transaction()
        ref = _Ref('job-1', {'status': status, 'dispatch_generation': 1})
        assert jobs._claim_finalization_job_txn(transaction, ref, 1, False, 1500, _now()) == {
            'status': status,
            'lease_epoch': None,
            'attempt_count': 0,
            'created_at': None,
        }
        assert transaction.updates == []


def test_reconciler_replaces_stale_generation_after_worker_crash():
    now = _now()
    transaction = _Transaction()
    ref = _Ref(
        'job-1',
        {
            'status': 'leased',
            'dispatch_generation': 4,
            'requires_byok': False,
            'lease_expires_at': now - timedelta(seconds=1),
        },
    )

    intent = jobs._claim_finalization_replay_txn(transaction, ref, timedelta(minutes=5), now)

    assert intent['status'] == 'queued'
    assert intent['dispatch_generation'] == 5
    assert transaction.updates[0][1]['dispatch_generation'] == 5


def test_expired_lease_reclaim_fences_a_stale_worker_terminal_write():
    now = _now()
    ref = _Ref(
        'job-1',
        {
            'status': 'leased',
            'dispatch_generation': 3,
            'lease_epoch': 4,
            'lease_expires_at': now - timedelta(seconds=1),
            'fanout_status': 'completed',
        },
    )

    reclaim = _Transaction()
    new_claim = jobs._claim_finalization_job_txn(reclaim, ref, 3, False, 1500, now)
    assert new_claim == {'status': 'claimed', 'lease_epoch': 5, 'attempt_count': 1, 'created_at': None}
    ref.data = ref.data | reclaim.updates[0][1]

    stale_completion = _Transaction()
    assert jobs._mark_finalization_completed_txn(stale_completion, ref, 3, 4, now) is False
    assert stale_completion.updates == []

    current_completion = _Transaction()
    assert jobs._mark_finalization_completed_txn(current_completion, ref, 3, 5, now) is True


def test_final_attempt_sets_visible_dead_letter_instead_of_completed():
    transaction = _Transaction()
    ref = _Ref('job-1', {'status': 'leased', 'dispatch_generation': 3, 'lease_epoch': 1})

    assert jobs._mark_finalization_dead_letter_txn(transaction, ref, 3, 1, 5, _now()) is True
    update = transaction.updates[0][1]
    assert update['status'] == 'dead_letter'
    assert update['task_retry_count'] == 5
    assert 'completed_at' not in update


def test_final_attempt_atomically_closes_its_bound_processing_conversation():
    transaction = _Transaction()
    job_ref = _Ref(
        'job-1',
        {
            'status': 'leased',
            'uid': 'uid-1',
            'conversation_id': 'conversation-1',
            'finalization_revision': 3,
            'dispatch_generation': 3,
            'lease_epoch': 1,
        },
    )
    conversation_ref = _conversation(
        {
            'status': 'processing',
            'discarded': False,
            'finalization_job_id': 'job-1',
            'finalization_revision': 3,
        }
    )

    assert (
        jobs._mark_finalization_dead_letter_txn(
            transaction,
            job_ref,
            3,
            1,
            5,
            _now(),
            lambda uid, conversation_id: conversation_ref,
        )
        is True
    )

    assert transaction.updates == [
        (
            job_ref,
            {
                'status': 'dead_letter',
                'updated_at': _now(),
                'terminal_at': _now(),
                'lease_expires_at': _now(),
                'reconcile_after_at': jobs.firestore.DELETE_FIELD,
                'task_retry_count': 5,
                'last_failure_code': 'final_attempt_failed',
            },
        ),
        (
            conversation_ref,
            {
                'status': 'failed',
                'discarded': True,
                'finalization_status': 'dead_letter',
            },
        ),
    ]


class _BoundedReplayCollection:
    def __init__(self):
        self.where_calls: list[tuple[str, str]] = []
        self.limit_value: int | None = None
        self.refs = [
            _Ref('queued-job', {'status': 'queued'}),
            _Ref('terminal-job', {'status': 'completed'}),
        ]

    def where(self, field, operator, _value):
        self.where_calls.append((field, operator))
        return self

    def limit(self, value):
        self.limit_value = value
        return self

    def stream(self):
        return self.refs[: self.limit_value]


def test_replay_candidates_use_a_server_side_bounded_due_query():
    collection = _BoundedReplayCollection()
    client = SimpleNamespace(collection=lambda _name: collection)

    candidates = jobs.get_finalization_replay_candidates(limit=1000, firestore_client=client)

    assert collection.where_calls == [('reconcile_after_at', '<=')]
    assert collection.limit_value == 100
    assert candidates == [{'status': 'queued', 'job_id': 'queued-job'}]


# ---------------------------------------------------------------------------
# Stale bare-processing orphan recovery (#10461 revision): authoritative
# server-owned admission fence, bounded cursor pagination, and legacy migration.
# ---------------------------------------------------------------------------


class _OrphanSnapshot:
    def __init__(self, uid: str, conversation_id: str, data: dict):
        self.id = conversation_id
        self._data = dict(data)
        self.reference = SimpleNamespace(path=f'users/{uid}/conversations/{conversation_id}')

    def to_dict(self) -> dict:
        return dict(self._data)


def _processing_snapshot(
    uid: str,
    conversation_id: str,
    *,
    admitted_at: datetime | None,
    deferred: bool = False,
    finalization_job_id: str | None = None,
    created_at: datetime | None = None,
) -> _OrphanSnapshot:
    data: dict = {'status': 'processing', 'created_at': created_at or admitted_at}
    if admitted_at is not None:
        data['processing_admitted_at'] = admitted_at
    if deferred:
        data['deferred'] = True
    if finalization_job_id:
        data['finalization_job_id'] = finalization_job_id
    return _OrphanSnapshot(uid, conversation_id, data)


class _OrphanQuery:
    """Fake collection-group query: single equality + cursor pagination."""

    def __init__(self, snapshots: list[_OrphanSnapshot]):
        self._all = snapshots
        self.where_count = 0
        self.where_filters: list[Any] = []
        self.order_by_count = 0
        self.limit_calls: list[int] = []
        self.start_after_calls: list[_OrphanSnapshot] = []
        self._limit: int | None = None
        self._after: _OrphanSnapshot | None = None

    def where(self, *args, filter=None, **kwargs):
        self.where_count += 1
        self.where_filters.append(filter)
        return self

    def order_by(self, *args, **kwargs):
        self.order_by_count += 1
        return self

    def limit(self, value: int):
        self.limit_calls.append(value)
        self._limit = value
        return self

    def start_after(self, snapshot):
        self.start_after_calls.append(snapshot)
        self._after = snapshot
        return self

    def stream(self):
        rows = self._all
        if self._after is not None:
            idx = rows.index(self._after)
            rows = rows[idx + 1 :]
        if self._limit is not None:
            rows = rows[: self._limit]
        return list(rows)


class _OrphanClient:
    def __init__(self, snapshots: list[_OrphanSnapshot]):
        self._snapshots = snapshots
        self.queries: list[_OrphanQuery] = []
        self.collection_group_calls: list[str] = []
        self.collection_calls: list[str] = []

    def collection_group(self, name: str) -> _OrphanQuery:
        self.collection_group_calls.append(name)
        query = _OrphanQuery(self._snapshots)
        self.queries.append(query)
        return query

    def collection(self, name: str):
        self.collection_calls.append(name)
        raise AssertionError('stale orphan sweep must not use a collection-scoped query')


def test_stale_orphan_query_is_a_single_field_collection_group_equality():
    """A single-equality collection-group query rides Firestore's automatic
    single-field index: no composite index, no collection-scoped entry."""
    now = _now()
    client = _OrphanClient([_processing_snapshot('uid', 'eligible', admitted_at=now - timedelta(hours=1))])

    jobs.get_stale_processing_orphan_candidates(stale_after=timedelta(seconds=900), firestore_client=client)

    assert client.collection_group_calls == ['conversations']
    assert client.collection_calls == []
    assert len(client.queries) >= 1
    assert all(query.where_count == 1 for query in client.queries)
    assert all(query.order_by_count == 0 for query in client.queries)


def test_orphan_stale_after_is_clamped_to_a_safe_floor_and_ceiling(monkeypatch):
    """The recovery window is bounded so an operator cannot defer recovery
    unbounded nor tighten it below any plausible live synchronous run."""
    assert jobs.get_stale_processing_orphan_after() == timedelta(seconds=900)
    monkeypatch.setenv('LISTEN_FINALIZATION_ORPHAN_STALE_SECONDS', '10')
    assert jobs.get_stale_processing_orphan_after() == timedelta(seconds=300)
    monkeypatch.setenv('LISTEN_FINALIZATION_ORPHAN_STALE_SECONDS', '9999999')
    assert jobs.get_stale_processing_orphan_after() == timedelta(seconds=86_400)
    monkeypatch.setenv('LISTEN_FINALIZATION_ORPHAN_STALE_SECONDS', 'not-a-number')
    assert jobs.get_stale_processing_orphan_after() == timedelta(seconds=900)


def test_stale_orphan_age_authority_is_processing_admitted_at_not_created_at(monkeypatch):
    """Only the server-owned admission stamp bounds age; caller-controlled
    created_at is never the authority, and legacy rows migrate rather than
    complete."""
    now = _now()
    monkeypatch.setattr(jobs, '_now', lambda: now)
    stale_after = timedelta(seconds=900)
    snapshots = [
        # Fresh admission, ancient caller-controlled created_at: must NOT act.
        _processing_snapshot(
            'uid',
            'fresh-admit-old-create',
            admitted_at=now - timedelta(seconds=10),
            created_at=now - timedelta(days=30),
        ),
        # Aged admission, fresh created_at: the genuine orphan — must act.
        _processing_snapshot(
            'uid',
            'aged-admit-fresh-create',
            admitted_at=now - timedelta(seconds=1000),
            created_at=now - timedelta(seconds=5),
        ),
        # Legacy row with no admission stamp: migrate, never complete on sight.
        _processing_snapshot('uid', 'legacy-no-admit', admitted_at=None, created_at=now - timedelta(days=30)),
    ]
    client = _OrphanClient(snapshots)

    candidates = jobs.get_stale_processing_orphan_candidates(stale_after=stale_after, firestore_client=client)

    by_id = {candidate['conversation_id']: candidate for candidate in candidates}
    assert 'fresh-admit-old-create' not in by_id
    eligible = by_id['aged-admit-fresh-create']
    assert eligible['legacy'] is False
    assert eligible['processing_admitted_at'] == now - timedelta(seconds=1000)
    legacy = by_id['legacy-no-admit']
    assert legacy['legacy'] is True
    assert legacy['processing_admitted_at'] is None


def test_stale_orphan_candidates_exclude_deferred_and_durable_job_rows():
    now = _now()
    aged = now - timedelta(seconds=1000)
    snapshots = [
        _processing_snapshot('uid', 'deferred', admitted_at=aged, deferred=True),
        _processing_snapshot('uid', 'durable', admitted_at=aged, finalization_job_id='job-x'),
        _processing_snapshot('uid', 'orphan', admitted_at=aged),
    ]
    client = _OrphanClient(snapshots)

    candidates = jobs.get_stale_processing_orphan_candidates(
        stale_after=timedelta(seconds=900), firestore_client=client
    )

    assert [candidate['conversation_id'] for candidate in candidates] == ['orphan']


def test_stale_orphan_candidates_page_past_excluded_rows_to_reach_a_later_orphan():
    """A stable first page of excluded rows cannot hide a later eligible orphan."""
    now = _now()
    aged = now - timedelta(seconds=1000)
    snapshots = [_processing_snapshot('uid', f'deferred-{i}', admitted_at=aged, deferred=True) for i in range(120)]
    snapshots.append(_processing_snapshot('uid', 'later-orphan', admitted_at=aged))
    client = _OrphanClient(snapshots)

    candidates = jobs.get_stale_processing_orphan_candidates(
        stale_after=timedelta(seconds=900), firestore_client=client
    )

    assert [candidate['conversation_id'] for candidate in candidates] == ['later-orphan']
    # The first page was entirely excluded, so at least two query pages were issued.
    assert len(client.queries) >= 2
    assert client.queries[1].start_after_calls


def test_stale_orphan_candidates_bound_total_scan():
    """The per-sweep scan bound prevents an unbounded walk under backlog."""
    now = _now()
    aged = now - timedelta(seconds=1000)
    snapshots = [_processing_snapshot('uid', f'deferred-{i}', admitted_at=aged, deferred=True) for i in range(50)]
    snapshots.append(_processing_snapshot('uid', 'later-orphan', admitted_at=aged))

    bounded = _OrphanClient(snapshots)
    candidates = jobs.get_stale_processing_orphan_candidates(
        stale_after=timedelta(seconds=900), max_scan=10, firestore_client=bounded
    )
    # The bound stops scanning before the orphan at index 50 is reached.
    assert candidates == []

    unbounded = _OrphanClient(snapshots)
    recovered = jobs.get_stale_processing_orphan_candidates(
        stale_after=timedelta(seconds=900), max_scan=10_000, firestore_client=unbounded
    )
    # The same population recovers the orphan once the bound is lifted.
    assert [candidate['conversation_id'] for candidate in recovered] == ['later-orphan']


def test_stamp_processing_admission_if_absent_only_stamps_a_legacy_processing_row():
    transaction = _Transaction()
    now = _now()
    legacy = _Ref('legacy', {'status': 'processing', 'created_at': now - timedelta(days=1)})

    stamped = jobs._stamp_processing_admission_if_absent_txn(transaction, legacy, now)

    assert stamped is True
    assert transaction.updates == [(legacy, {'processing_admitted_at': now})]


def test_stamp_processing_admission_if_absent_is_idempotent_and_fences_non_processing():
    transaction = _Transaction()
    now = _now()
    already = _Ref('already', {'status': 'processing', 'processing_admitted_at': now - timedelta(hours=2)})
    terminal = _Ref('terminal', {'status': 'completed'})

    assert jobs._stamp_processing_admission_if_absent_txn(transaction, already, now) is False
    assert jobs._stamp_processing_admission_if_absent_txn(transaction, terminal, now) is False
    assert transaction.updates == []
