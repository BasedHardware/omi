"""Behavioral contract tests for the durable listen finalization job state machine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from database import conversation_finalization_jobs as jobs


class _Ref:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self.data = data

    def get(self, transaction=None):
        del transaction
        return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

    def to_dict(self):
        return self.data


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


def _conversation(data: dict | None = None) -> _Ref:
    return _Ref(
        'conversation-1',
        {
            'status': 'in_progress',
            'transcript_segments': [{'text': 'persisted'}],
            **(data or {}),
        },
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
    assert claim == {'status': 'claimed', 'lease_epoch': 1, 'attempt_count': 1}
    claim_update = first.updates[0][1]
    assert claim_update['status'] == 'leased'
    assert claim_update['attempt_count'] == 1

    ref.data = ref.data | claim_update
    duplicate = _Transaction()
    assert jobs._claim_finalization_job_txn(duplicate, ref, 2, False, 1500, now + timedelta(seconds=1)) == {
        'status': 'leased',
        'lease_epoch': None,
        'attempt_count': 0,
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
    assert claim == {'status': 'claimed', 'lease_epoch': 1, 'attempt_count': 2}
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

    assert claim == {'status': 'fenced', 'lease_epoch': None, 'attempt_count': 0}


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

    assert status == {'status': 'identity_mismatch', 'lease_epoch': None, 'attempt_count': 0}
    assert transaction.updates == []


def test_completed_and_dead_letter_jobs_never_execute_again():
    for status in ('completed', 'dead_letter'):
        transaction = _Transaction()
        ref = _Ref('job-1', {'status': status, 'dispatch_generation': 1})
        assert jobs._claim_finalization_job_txn(transaction, ref, 1, False, 1500, _now()) == {
            'status': status,
            'lease_epoch': None,
            'attempt_count': 0,
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
    assert new_claim == {'status': 'claimed', 'lease_epoch': 5, 'attempt_count': 1}
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
