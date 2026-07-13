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
    forbidden = {'byok_keys', 'transcript', 'transcript_segments', 'authorization', 'raw_error'}
    assert forbidden.isdisjoint(job)
    assert transaction.updates[0][1]['status'] == 'processing'
    assert transaction.updates[0][1]['finalization_job_id'] == intent['job_id']


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
        _now(),
    )

    assert intent == {'job_id': job_id, 'status': 'queued', 'dispatch_generation': 1, 'requires_byok': False}
    assert transaction.sets == []
    assert transaction.updates == []


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
        _now(),
    )

    assert intent['status'] == 'blocked_byok'
    persisted = transaction.sets[0][1]
    assert persisted['requires_byok'] is True
    assert set(persisted).isdisjoint({'byok_keys', 'openai', 'anthropic', 'gemini', 'deepgram'})


def test_duplicate_task_delivery_claims_only_once_until_lease_expires():
    now = _now()
    ref = _Ref('job-1', {'status': 'queued', 'dispatch_generation': 2, 'attempt_count': 0})
    first = _Transaction()

    assert jobs._claim_finalization_job_txn(first, ref, 2, False, 1500, now) == 'claimed'
    claim_update = first.updates[0][1]
    assert claim_update['status'] == 'leased'
    assert claim_update['attempt_count'] == 1

    ref.data = ref.data | claim_update
    duplicate = _Transaction()
    assert jobs._claim_finalization_job_txn(duplicate, ref, 2, False, 1500, now + timedelta(seconds=1)) == 'leased'
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

    assert jobs._claim_finalization_job_txn(transaction, ref, 2, False, 1500, now) == 'claimed'
    assert transaction.updates[0][1]['attempt_count'] == 2


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

    assert status == 'identity_mismatch'
    assert transaction.updates == []


def test_completed_and_dead_letter_jobs_never_execute_again():
    for status in ('completed', 'dead_letter'):
        transaction = _Transaction()
        ref = _Ref('job-1', {'status': status, 'dispatch_generation': 1})
        assert jobs._claim_finalization_job_txn(transaction, ref, 1, False, 1500, _now()) == status
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


def test_final_attempt_sets_visible_dead_letter_instead_of_completed():
    transaction = _Transaction()
    ref = _Ref('job-1', {'status': 'leased', 'dispatch_generation': 3})

    assert jobs._mark_finalization_dead_letter_txn(transaction, ref, 3, 5, _now()) is True
    update = transaction.updates[0][1]
    assert update['status'] == 'dead_letter'
    assert update['task_retry_count'] == 5
    assert 'completed_at' not in update
