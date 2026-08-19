"""Behavioral tests for the content-free v2 finalization effect ledger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from database import conversation_finalization_effects as effect_store
from database import conversation_finalization_effect_store as effect_store_db
from database import conversation_finalization_jobs as jobs
from utils.conversations import lifecycle as lifecycle_service


class _PhotoCollection:
    def limit(self, count: int):
        assert count == 1
        return self

    def stream(self, transaction=None):
        del transaction
        return iter(())


class _Ref:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self.data = data

    def get(self, transaction=None):
        del transaction
        return SimpleNamespace(exists=self.data is not None, id=self.id, to_dict=lambda: self.data)

    def collection(self, name: str):
        assert name == 'photos'
        return _PhotoCollection()


class _Collection:
    def __init__(self, refs: dict[str, _Ref] | None = None):
        self.refs = refs or {}

    def document(self, doc_id: str):
        return self.refs.setdefault(doc_id, _Ref(doc_id, None))


class _Transaction:
    def __init__(self):
        self.updates: list[tuple[_Ref, dict]] = []
        self.sets: list[tuple[_Ref, dict]] = []

    def update(self, ref, data):
        self.updates.append((ref, data))

    def set(self, ref, data, **_kwargs):
        self.sets.append((ref, data))


class _ApplyingTransaction(_Transaction):
    def update(self, ref, data):
        super().update(ref, data)
        ref.data = dict(ref.data or {}) | data


class _UserRef:
    def __init__(self, conversations: _Collection):
        self.conversations = conversations

    def collection(self, name: str):
        assert name == 'conversations'
        return self.conversations


class _UsersCollection:
    def __init__(self, conversations: _Collection):
        self.conversations = conversations

    def document(self, _uid: str):
        return _UserRef(self.conversations)


class _Client:
    def __init__(self, job: _Ref, conversation: _Ref):
        self.jobs = _Collection({job.id: job})
        self.conversations = _Collection({conversation.id: conversation})
        self.projections = _Collection()
        self.transactions: list[_ApplyingTransaction] = []

    def transaction(self):
        transaction = _ApplyingTransaction()
        self.transactions.append(transaction)
        return transaction

    def collection(self, name: str):
        if name == jobs.FINALIZATION_JOBS_COLLECTION:
            return self.jobs
        if name == jobs.FINALIZATION_PROJECTION_COLLECTION:
            return self.projections
        assert name == 'users'
        return _UsersCollection(self.conversations)


def _now() -> datetime:
    return datetime(2026, 7, 26, tzinfo=timezone.utc)


def _apply_update(transaction: _Transaction, ref: _Ref) -> None:
    assert transaction.updates and transaction.updates[-1][0] is ref
    ref.data = dict(ref.data or {}) | transaction.updates[-1][1]


def _admit(_conversation: dict) -> jobs.FinalizationAdmission:
    return {
        'accepted': True,
        'terminal': False,
        'reason': 'accepted',
        'fanout_key': 'conversation:conversation-1:finalization:1',
    }


def _v2_job(
    *,
    completed_effects: list[str] | None = None,
    status: str = 'leased',
    dispatch_generation: int = 3,
    lease_epoch: int = 7,
    fanout_status: str = 'leased',
    fanout_lease_epoch: int = 7,
) -> dict:
    return {
        'status': status,
        'dispatch_generation': dispatch_generation,
        'lease_epoch': lease_epoch,
        'lease_expires_at': _now() + timedelta(minutes=10),
        'fanout_status': fanout_status,
        'fanout_lease_epoch': fanout_lease_epoch,
        'fanout_plan_version': jobs.FINALIZATION_FANOUT_PLAN_VERSION,
        'completed_effects': list(completed_effects or []),
        'uid': 'uid-1',
        'conversation_id': 'conversation-1',
        'finalization_revision': 1,
        'finalization_incarnation_id': 'incarnation-1',
        'finalization_vector_generation_id': 'generation-job-1',
        'finalization_effect_source_fingerprint': effect_store.finalization_effect_source_fingerprint(
            _completed_conversation().data or {}
        ),
        'requires_byok': False,
        'attempt_count': 1,
    }


def _completed_conversation() -> _Ref:
    return _Ref(
        'conversation-1',
        {
            'status': 'completed',
            'discarded': False,
            'finalization_job_id': 'job-1',
            'finalization_revision': 1,
            'finalization_incarnation_id': 'incarnation-1',
            'finalization_vector_generation_id': 'generation-job-1',
        },
    )


def _checkpoint(
    transaction: _Transaction,
    ref: _Ref,
    dispatch_generation: int,
    lease_epoch: int,
    effect: str,
    now: datetime,
    *,
    conversation_ref: _Ref | None = None,
) -> effect_store_db.FinalizationEffectBoundaryStatus:
    return effect_store_db._mark_finalization_effect_completed_txn(
        transaction,
        ref,
        dispatch_generation,
        lease_epoch,
        effect,
        now,
        lambda *_: conversation_ref or _completed_conversation(),
    )


@pytest.mark.parametrize('configured_mode', (None, '', 'standby', 'unexpected'))
def test_new_jobs_default_or_invalid_mode_stays_mixed_revision_safe(monkeypatch, configured_mode: str | None):
    if configured_mode is None:
        monkeypatch.delenv(jobs.FINALIZATION_EFFECT_PLAN_MODE_ENV, raising=False)
    else:
        monkeypatch.setenv(jobs.FINALIZATION_EFFECT_PLAN_MODE_ENV, configured_mode)
    transaction = _Transaction()

    jobs._create_or_get_finalization_intent_txn(
        transaction,
        _Ref('conversation-1', {'status': 'in_progress', 'transcript_segments': [{'text': 'persisted'}]}),
        _Collection(),
        'uid-1',
        'conversation-1',
        False,
        _admit,
        _now(),
    )

    assert jobs.finalization_effect_plan_mode() == 'standby'
    persisted = transaction.sets[0][1]
    assert persisted['schema_version'] == 1
    assert {
        'fanout_plan_version',
        'completed_effects',
        'finalization_incarnation_id',
        'finalization_vector_generation_id',
    }.isdisjoint(persisted)
    assert transaction.sets[0][0].id == jobs._job_id('uid-1', 'conversation-1', 1)


def test_explicit_active_mode_persists_v2_plan_with_an_empty_content_free_effect_ledger(monkeypatch):
    monkeypatch.setenv(jobs.FINALIZATION_EFFECT_PLAN_MODE_ENV, 'active')
    transaction = _Transaction()
    conversation_ref = _Ref(
        'conversation-1',
        {'status': 'in_progress', 'transcript_segments': [{'text': 'persisted on the conversation only'}]},
    )

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        _Collection(),
        'uid-1',
        'conversation-1',
        False,
        _admit,
        _now(),
    )

    assert intent['created'] is True
    persisted = transaction.sets[0][1]
    assert persisted['fanout_plan_version'] == 2
    assert persisted['completed_effects'] == []
    assert persisted['finalization_incarnation_id']
    assert persisted['finalization_incarnation_id'] in persisted['fanout_key']
    assert persisted['finalization_vector_generation_id'] == transaction.sets[0][0].id
    assert jobs.REQUIRED_EFFECT_KEYS == (
        'structured_vector',
        'transcript_vectors',
    )
    assert {
        'transcript',
        'transcript_segments',
        'structured',
        'memories',
        'action_items',
        'effect_results',
    }.isdisjoint(persisted)


def test_active_mode_does_not_retrofit_an_existing_unversioned_job(monkeypatch):
    monkeypatch.setenv(jobs.FINALIZATION_EFFECT_PLAN_MODE_ENV, 'active')
    existing_job = {
        'status': 'queued',
        'dispatch_generation': 2,
        'requires_byok': False,
        'fanout_key': 'legacy-fanout',
    }
    conversation_ref = _Ref(
        'conversation-1',
        {
            'status': 'processing',
            'transcript_segments': [{'text': 'persisted'}],
            'finalization_job_id': 'legacy-job',
        },
    )
    transaction = _Transaction()

    intent = jobs._create_or_get_finalization_intent_txn(
        transaction,
        conversation_ref,
        _Collection({'legacy-job': _Ref('legacy-job', existing_job)}),
        'uid-1',
        'conversation-1',
        False,
        _admit,
        _now(),
    )

    assert intent['job_id'] == 'legacy-job'
    assert intent['created'] is False
    assert {'fanout_plan_version', 'completed_effects'}.isdisjoint(existing_job)
    assert transaction.sets == []
    assert transaction.updates == []


def test_fanout_claim_returns_v2_plan_and_completed_effect_keys_in_plan_order():
    ref = _Ref(
        'job-1',
        _v2_job(
            completed_effects=['transcript_vectors', 'structured_vector'],
            fanout_status='pending',
            fanout_lease_epoch=0,
        ),
    )
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: _completed_conversation(),
    )

    assert claim == {
        'status': 'claimed',
        'fanout_key': 'conversation:conversation-1:incarnation:incarnation-1:finalization:1',
        'plan_version': 2,
        'completed_effects': ('structured_vector', 'transcript_vectors'),
        'finalization_incarnation_id': 'incarnation-1',
        'finalization_vector_generation_id': 'generation-job-1',
        'transcript_vector_count': None,
    }
    assert transaction.updates[0][1]['fanout_lease_epoch'] == 7


def test_first_v2_fanout_claim_persists_a_content_free_source_fingerprint():
    job = _v2_job(fanout_status='pending', fanout_lease_epoch=0)
    job.pop(effect_store.FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD)
    ref = _Ref('job-1', job)
    conversation = _completed_conversation()
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: conversation,
    )

    assert claim['status'] == 'claimed'
    fingerprint = transaction.updates[0][1][effect_store.FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD]
    assert fingerprint == effect_store.finalization_effect_source_fingerprint(conversation.data or {})
    assert len(fingerprint) == 64
    assert 'conversation-1' not in fingerprint
    assert fingerprint != effect_store.finalization_effect_source_fingerprint(
        (conversation.data or {}) | {'user_title': 'concurrent edit'}
    )


def test_same_count_source_change_requires_old_generation_cleanup_before_any_checkpoint():
    job = _v2_job(completed_effects=['structured_vector'])
    job['transcript_vector_count'] = 2
    ref = _Ref('job-1', job)
    changed = _completed_conversation()
    changed.data['structured'] = {'title': 'changed after the first checkpoint'}
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: changed,
    )

    assert claim['status'] == 'cleanup_required'
    assert claim['finalization_vector_generation_id'] == 'generation-job-1'
    assert claim['transcript_vector_count'] == 2
    assert transaction.updates == []

    checkpoint = _Transaction()
    assert (
        _checkpoint(
            checkpoint,
            ref,
            3,
            7,
            'transcript_vectors',
            _now(),
            conversation_ref=changed,
        )
        == 'conversation_replaced'
    )
    assert checkpoint.updates == []

    cleanup = _Transaction()
    assert effect_store.cleanup_fence_txn(
        cleanup,
        ref,
        3,
        7,
        _now(),
        is_current_lease=jobs.is_current_finalization_lease,
        conversation_ref_for_job=lambda *_: changed,
        conversation_admits_fanout=jobs._conversation_admits_fanout,
        fenced_update=jobs.fenced_finalization_update,
        record_projection=lambda *_: None,
    )
    assert cleanup.updates[0][1]['fanout_status'] == 'fenced'


def test_effect_boundary_fails_closed_for_a_missing_or_malformed_v2_source_fingerprint():
    for malformed in (None, '', 'not-a-digest', 7):
        job = _v2_job()
        if malformed is None:
            job.pop(effect_store.FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD)
        else:
            job[effect_store.FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD] = malformed
        transaction = _Transaction()

        assert not effect_store.conversation_admits_fanout(_completed_conversation().data or {}, job, 'job-1')
        assert _checkpoint(transaction, _Ref('job-1', job), 3, 7, 'structured_vector', _now()) == 'conflict'
        assert transaction.updates == []


@pytest.mark.parametrize(
    ('completed_effects', 'fanout_status', 'expected_status'),
    (
        (['structured_vector'], 'leased', 'cleanup_required'),
        (list(jobs.REQUIRED_EFFECT_KEYS), 'completed', 'completed_cleanup_required'),
    ),
)
def test_missing_source_fingerprint_never_rebinds_an_existing_effect_generation(
    completed_effects,
    fanout_status,
    expected_status,
):
    job = _v2_job(completed_effects=completed_effects, fanout_status=fanout_status)
    job.pop(effect_store.FINALIZATION_EFFECT_SOURCE_FINGERPRINT_FIELD)
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        _Ref('job-1', job),
        3,
        7,
        _now(),
        lambda *_: _completed_conversation(),
    )

    assert claim['status'] == expected_status
    assert claim['finalization_vector_generation_id'] == 'generation-job-1'
    assert transaction.updates == []


def test_effect_checkpoints_progress_in_fixed_order_and_are_idempotent():
    ref = _Ref('job-1', _v2_job())

    for index, effect in enumerate(jobs.REQUIRED_EFFECT_KEYS, start=1):
        transaction = _Transaction()
        assert _checkpoint(transaction, ref, 3, 7, effect, _now()) == 'completed'
        _apply_update(transaction, ref)
        assert ref.data['completed_effects'] == list(jobs.REQUIRED_EFFECT_KEYS[:index])

    duplicate = _Transaction()
    assert (
        _checkpoint(
            duplicate,
            ref,
            3,
            7,
            jobs.REQUIRED_EFFECT_KEYS[-1],
            _now(),
        )
        == 'completed'
    )
    assert duplicate.updates == []


@pytest.mark.parametrize(
    ('job_updates', 'dispatch_generation', 'lease_epoch', 'effect'),
    (
        ({}, 2, 7, 'structured_vector'),
        ({}, 3, 6, 'structured_vector'),
        ({'status': 'queued'}, 3, 7, 'structured_vector'),
        ({'fanout_status': 'pending'}, 3, 7, 'structured_vector'),
        ({'fanout_lease_epoch': 6}, 3, 7, 'structured_vector'),
        ({}, 3, 7, 'unbounded_effect'),
    ),
)
def test_effect_checkpoint_rejects_stale_generation_lease_fanout_or_key(
    job_updates: dict,
    dispatch_generation: int,
    lease_epoch: int,
    effect: str,
):
    ref = _Ref('job-1', _v2_job() | job_updates)
    transaction = _Transaction()

    assert (
        _checkpoint(
            transaction,
            ref,
            dispatch_generation,
            lease_epoch,
            effect,
            _now(),
        )
        == 'conflict'
    )
    assert transaction.updates == []


def test_effect_checkpoint_prioritizes_missing_conversation_after_lease_loss():
    ref = _Ref('job-1', _v2_job())
    transaction = _Transaction()

    status = _checkpoint(
        transaction,
        ref,
        3,
        6,
        'structured_vector',
        _now(),
        conversation_ref=_Ref('conversation-1', None),
    )

    assert status == 'conversation_missing'
    assert transaction.updates == []


def test_post_cleanup_fence_accepts_leased_fanout_only_while_conversation_remains_missing():
    ref = _Ref('job-1', _v2_job())
    transaction = _Transaction()
    projection_updates = []

    fenced = effect_store.cleanup_fence_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        is_current_lease=jobs.is_current_finalization_lease,
        conversation_ref_for_job=lambda *_: _Ref('conversation-1', None),
        conversation_admits_fanout=jobs._conversation_admits_fanout,
        fenced_update=jobs.fenced_finalization_update,
        record_projection=lambda txn, job: projection_updates.append((txn, job)),
    )

    assert fenced is True
    assert transaction.updates[0][1]['fanout_status'] == 'fenced'
    assert projection_updates == [(transaction, ref.data)]


def test_post_cleanup_fence_accepts_recreated_conversation_after_exact_old_generation_cleanup():
    ref = _Ref('job-1', _v2_job())
    transaction = _Transaction()
    recreated = _completed_conversation()
    recreated.data['finalization_incarnation_id'] = 'incarnation-2'

    fenced = effect_store.cleanup_fence_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        is_current_lease=jobs.is_current_finalization_lease,
        conversation_ref_for_job=lambda *_: recreated,
        conversation_admits_fanout=jobs._conversation_admits_fanout,
        fenced_update=jobs.fenced_finalization_update,
        record_projection=lambda *_: None,
    )

    assert fenced is True
    assert transaction.updates[0][1]['fanout_status'] == 'fenced'


def test_post_cleanup_fence_rejects_the_still_current_conversation():
    ref = _Ref('job-1', _v2_job())
    transaction = _Transaction()

    fenced = effect_store.cleanup_fence_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        is_current_lease=jobs.is_current_finalization_lease,
        conversation_ref_for_job=lambda *_: _completed_conversation(),
        conversation_admits_fanout=jobs._conversation_admits_fanout,
        fenced_update=jobs.fenced_finalization_update,
        record_projection=lambda *_: None,
    )

    assert fenced is False
    assert transaction.updates == []


def test_retry_preserves_checkpoints_and_next_fanout_claim_resumes_them():
    completed = ['structured_vector']
    ref = _Ref('job-1', _v2_job(completed_effects=completed))

    retry = _Transaction()
    assert jobs._mark_finalization_retryable_txn(retry, ref, 3, 7, 'effect_failed', _now()) is True
    _apply_update(retry, ref)
    assert ref.data['status'] == 'queued'
    assert ref.data['completed_effects'] == completed

    reclaim = _Transaction()
    claim = jobs._claim_finalization_job_txn(
        reclaim,
        ref,
        3,
        False,
        1500,
        _now() + timedelta(seconds=1),
    )
    assert claim['status'] == 'claimed'
    assert claim['lease_epoch'] == 8
    _apply_update(reclaim, ref)

    fanout = _Transaction()
    resumed = jobs._claim_finalization_fanout_txn(
        fanout,
        ref,
        3,
        8,
        _now() + timedelta(seconds=1),
        lambda *_: _completed_conversation(),
    )

    assert resumed['plan_version'] == 2
    assert resumed['completed_effects'] == tuple(completed)
    assert fanout.updates[0][1]['fanout_lease_epoch'] == 8


def test_retry_transition_cannot_queue_over_an_older_undrained_fanout_epoch():
    ref = _Ref(
        'job-1',
        _v2_job(lease_epoch=8, fanout_lease_epoch=7),
    )
    transaction = _Transaction()

    assert not jobs._mark_finalization_retryable_txn(
        transaction,
        ref,
        3,
        8,
        'effect_failed',
        _now(),
    )
    assert transaction.updates == []


def test_v2_fanout_completion_refuses_a_missing_effect_then_accepts_the_full_plan():
    ref = _Ref('job-1', _v2_job(completed_effects=list(jobs.REQUIRED_EFFECT_KEYS[:-1])))

    incomplete = _Transaction()
    assert jobs._mark_finalization_fanout_completed_txn(incomplete, ref, 3, 7, _now()) is False
    assert incomplete.updates == []

    final_effect = _Transaction()
    assert (
        _checkpoint(
            final_effect,
            ref,
            3,
            7,
            jobs.REQUIRED_EFFECT_KEYS[-1],
            _now(),
        )
        == 'completed'
    )
    _apply_update(final_effect, ref)

    complete = _Transaction()
    assert jobs._mark_finalization_fanout_completed_txn(complete, ref, 3, 7, _now()) is True
    assert complete.updates[0][1]['fanout_status'] == 'completed'


def test_incomplete_v2_completed_fanout_is_reclaimed_and_can_finish_missing_effects():
    ref = _Ref(
        'job-1',
        _v2_job(
            completed_effects=['structured_vector'],
            fanout_status='completed',
        ),
    )
    ref.data['fanout_completed_at'] = _now() - timedelta(seconds=1)
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: _completed_conversation(),
    )

    assert claim['status'] == 'claimed'
    assert claim['completed_effects'] == ('structured_vector',)
    assert transaction.updates[0][1]['fanout_status'] == 'leased'
    assert transaction.updates[0][1]['fanout_completed_at'] is jobs.firestore.DELETE_FIELD
    _apply_update(transaction, ref)

    checkpoint = _Transaction()
    assert _checkpoint(checkpoint, ref, 3, 7, 'transcript_vectors', _now()) == 'completed'
    _apply_update(checkpoint, ref)

    complete = _Transaction()
    assert jobs._mark_finalization_fanout_completed_txn(complete, ref, 3, 7, _now()) is True


@pytest.mark.parametrize('status', ('leased', 'completed'))
def test_v2_job_completion_rejects_an_incomplete_effect_ledger(status: str):
    ref = _Ref(
        'job-1',
        _v2_job(
            completed_effects=['structured_vector'],
            status=status,
            fanout_status='completed',
        ),
    )
    transaction = _Transaction()

    assert jobs._mark_finalization_completed_txn(transaction, ref, 3, 7, _now()) is False
    assert transaction.updates == []


def test_v2_job_completion_accepts_the_complete_effect_ledger():
    ref = _Ref(
        'job-1',
        _v2_job(
            completed_effects=list(jobs.REQUIRED_EFFECT_KEYS),
            fanout_status='completed',
        ),
    )
    transaction = _Transaction()

    assert jobs._mark_finalization_completed_txn(transaction, ref, 3, 7, _now()) is True
    assert transaction.updates[0][1]['status'] == 'completed'


def test_unversioned_v1_jobs_keep_legacy_fanout_completion_behavior():
    ref = _Ref(
        'job-1',
        {
            key: value
            for key, value in _v2_job(fanout_status='pending', fanout_lease_epoch=0).items()
            if key
            not in {
                'fanout_plan_version',
                'completed_effects',
                'finalization_incarnation_id',
                'finalization_vector_generation_id',
            }
        },
    )
    claim_transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        claim_transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: _completed_conversation(),
    )
    assert claim['plan_version'] == 1
    assert claim['completed_effects'] == ()
    _apply_update(claim_transaction, ref)

    checkpoint = _Transaction()
    assert (
        _checkpoint(
            checkpoint,
            ref,
            3,
            7,
            'structured_vector',
            _now(),
        )
        == 'completed'
    )
    assert checkpoint.updates == []

    complete = _Transaction()
    assert jobs._mark_finalization_fanout_completed_txn(complete, ref, 3, 7, _now()) is True
    assert complete.updates[0][1]['fanout_status'] == 'completed'


def _completed_v1_job() -> dict:
    return {
        key: value
        for key, value in _v2_job(fanout_status='completed').items()
        if key
        not in {
            'fanout_plan_version',
            'completed_effects',
            'finalization_incarnation_id',
            'finalization_vector_generation_id',
        }
    }


def test_completed_v2_fanout_with_missing_conversation_requires_cleanup_before_acknowledgement():
    ref = _Ref(
        'job-1',
        _v2_job(completed_effects=list(jobs.REQUIRED_EFFECT_KEYS), fanout_status='completed'),
    )
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: _Ref('conversation-1', None),
    )

    assert claim['status'] == 'completed_cleanup_required'
    assert claim['plan_version'] == 2
    assert transaction.updates == []


def test_completed_v2_fanout_with_recreated_same_id_requires_only_old_generation_cleanup():
    ref = _Ref(
        'job-1',
        _v2_job(completed_effects=list(jobs.REQUIRED_EFFECT_KEYS), fanout_status='completed'),
    )
    recreated = _completed_conversation()
    recreated.data['finalization_incarnation_id'] = 'incarnation-2'
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: recreated,
    )

    assert claim['status'] == 'completed_cleanup_required'
    assert claim['finalization_incarnation_id'] == 'incarnation-1'
    assert claim['finalization_vector_generation_id'] == 'generation-job-1'
    assert transaction.updates == []


def test_completed_old_revision_cleanup_cannot_target_newer_same_incarnation_generation():
    ref = _Ref(
        'job-1',
        _v2_job(completed_effects=list(jobs.REQUIRED_EFFECT_KEYS), fanout_status='completed'),
    )
    newer_revision = _completed_conversation()
    newer_revision.data.update(
        {
            'finalization_job_id': 'job-2',
            'finalization_revision': 2,
            'finalization_vector_generation_id': 'generation-job-2',
        }
    )
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: newer_revision,
    )

    assert claim['status'] == 'completed_cleanup_required'
    assert claim['finalization_incarnation_id'] == 'incarnation-1'
    assert claim['finalization_vector_generation_id'] == 'generation-job-1'
    assert newer_revision.data['finalization_vector_generation_id'] == 'generation-job-2'
    assert transaction.updates == []


def test_vector_cleanup_fence_prevents_fanout_for_an_otherwise_current_job():
    conversation = _completed_conversation()
    conversation.data['vector_cleanup_pending'] = True

    assert jobs._conversation_admits_fanout(conversation.data, _v2_job(), 'job-1') is False


def test_completed_v1_fanout_preserves_legacy_acknowledgement_without_vector_replay():
    ref = _Ref('job-1', _completed_v1_job())
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: _completed_conversation(),
    )

    assert claim == {
        'status': 'completed',
        'fanout_key': 'conversation:conversation-1:finalization:1',
        'plan_version': 1,
        'completed_effects': (),
        'finalization_incarnation_id': None,
        'finalization_vector_generation_id': None,
        'transcript_vector_count': None,
    }
    assert transaction.updates == []


@pytest.mark.parametrize(
    ('conversation_ref', 'expected_status'),
    (
        (_Ref('conversation-1', None), 'completed'),
        (
            _Ref(
                'conversation-1',
                {
                    'status': 'completed',
                    'discarded': True,
                    'finalization_job_id': 'job-1',
                    'finalization_revision': 1,
                },
            ),
            'completed',
        ),
    ),
)
def test_completed_v1_fanout_preserves_acknowledgement_when_conversation_is_not_current(
    conversation_ref: _Ref,
    expected_status: str,
):
    ref = _Ref('job-1', _completed_v1_job())
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        ref,
        3,
        7,
        _now(),
        lambda *_: conversation_ref,
    )

    assert claim['status'] == expected_status
    assert transaction.updates == []


def test_completed_v1_fanout_replay_rejects_a_stale_worker_lease():
    transaction = _Transaction()

    claim = jobs._claim_finalization_fanout_txn(
        transaction,
        _Ref('job-1', _completed_v1_job()),
        3,
        6,
        _now(),
        lambda *_: _completed_conversation(),
    )

    assert claim['status'] == 'lease_conflict'
    assert transaction.updates == []


def test_lifecycle_wrapper_delegates_the_fenced_effect_checkpoint(monkeypatch):
    observed = []

    def complete(
        job_id: str,
        dispatch_generation: int,
        lease_epoch: int,
        effect: str,
        *,
        persist_effect: bool,
    ) -> effect_store_db.FinalizationEffectBoundaryStatus:
        observed.append((job_id, dispatch_generation, lease_epoch, effect, persist_effect))
        return 'completed'

    monkeypatch.setattr(lifecycle_service.effect_store, 'mark_finalization_effect_completed', complete)

    assert lifecycle_service.complete_finalization_effect('job-1', 3, 7, 'transcript_vectors') == 'completed'
    assert observed == [('job-1', 3, 7, 'transcript_vectors', True)]


def test_prepare_wrapper_persists_one_transcript_shape_and_rejects_drift(monkeypatch):
    job = _Ref('job-1', _v2_job())
    client = _Client(job, _completed_conversation())
    monkeypatch.setattr(effect_store_db.firestore, 'transactional', lambda function: function)

    assert (
        effect_store_db.prepare_finalization_effect(
            'job-1',
            3,
            7,
            'transcript_vectors',
            4,
            firestore_client=client,
        )
        == 'completed'
    )
    assert job.data['transcript_vector_count'] == 4
    assert client.conversations.refs['conversation-1'].data['transcript_vector_count'] == 4
    assert (
        effect_store_db.prepare_finalization_effect(
            'job-1',
            3,
            7,
            'transcript_vectors',
            4,
            firestore_client=client,
        )
        == 'completed'
    )
    assert (
        effect_store_db.prepare_finalization_effect(
            'job-1',
            3,
            7,
            'transcript_vectors',
            5,
            firestore_client=client,
        )
        == 'conflict'
    )


def test_completion_wrapper_can_run_a_post_write_fence_without_persisting_the_effect(monkeypatch):
    job = _Ref('job-1', _v2_job())
    client = _Client(job, _completed_conversation())
    monkeypatch.setattr(effect_store_db.firestore, 'transactional', lambda function: function)

    assert (
        effect_store_db.mark_finalization_effect_completed(
            'job-1',
            3,
            7,
            'structured_vector',
            persist_effect=False,
            firestore_client=client,
        )
        == 'completed'
    )
    assert job.data['completed_effects'] == []
    assert client.transactions[-1].updates == []


def test_cleanup_wrapper_fences_old_generation_and_updates_projection_for_recreated_row(monkeypatch):
    job_data = _v2_job() | {'projection_generation': jobs.FINALIZATION_PROJECTION_GENERATION, 'projection_shard': 2}
    job = _Ref('job-1', job_data)
    recreated = _completed_conversation()
    recreated.data['finalization_incarnation_id'] = 'incarnation-2'
    client = _Client(job, recreated)
    monkeypatch.setattr(effect_store_db.firestore, 'transactional', lambda function: function)

    assert (
        effect_store_db.mark_finalization_enrichment_cleaned(
            'job-1',
            3,
            7,
            firestore_client=client,
        )
        is True
    )
    assert job.data['fanout_status'] == 'fenced'
    assert client.transactions[-1].sets
