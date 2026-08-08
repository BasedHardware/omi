"""Behavioral contract tests for the durable listen finalization job state machine.

Reshaped onto the neutral storage port (WP2): every test drives the public API against a
``FakeDocumentStore`` seeded at the module's real logical paths, so the transactions run through
``FakeDocumentStore.run_transaction`` exactly as production runs them through the store adapter.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from database import conversation_finalization_jobs as jobs
from tests.store_fakes import FakeDocumentStore

_GEN = jobs.FINALIZATION_PROJECTION_GENERATION


@pytest.fixture
def store(monkeypatch) -> FakeDocumentStore:
    fake = FakeDocumentStore()
    monkeypatch.setattr(jobs, 'get_document_store', lambda: fake)
    return fake


@pytest.fixture
def now(monkeypatch) -> datetime:
    fixed = datetime(2026, 7, 13, tzinfo=timezone.utc)
    monkeypatch.setattr(jobs, '_now', lambda: fixed)
    return fixed


# --- path + seed helpers (mirror the module's logical addressing) ---


def _conv_path(uid: str, cid: str) -> str:
    return f'users/{uid}/conversations/{cid}'


def _job_path(job_id: str) -> str:
    return f'conversation_finalization_jobs/{job_id}'


def _shard_path(shard: int) -> str:
    return f'conversation_finalization_projection_shards/{jobs._projection_shard_id(_GEN, shard)}'


def _cursor_path() -> str:
    return f'{jobs.STALE_PROCESSING_SWEEP_STATE_COLLECTION}/{jobs.STALE_PROCESSING_SWEEP_STATE_DOC}'


def _seed_conversation(store, uid: str, cid: str, data: dict | None = None, *, has_legacy_photo: bool = False) -> None:
    base = {'status': 'in_progress', 'transcript_segments': [{'text': 'persisted'}]}
    base.update(data or {})
    store.set(_conv_path(uid, cid), base)
    if has_legacy_photo:
        store.set(f'{_conv_path(uid, cid)}/photos/p1', {'id': 'p1'})


def _seed_processing(
    store,
    uid: str,
    cid: str,
    *,
    admitted_at: datetime | None,
    deferred: bool = False,
    finalization_job_id: str | None = None,
    created_at: datetime | None = None,
) -> None:
    data: dict = {'status': 'processing', 'created_at': created_at or admitted_at}
    if admitted_at is not None:
        data['processing_admitted_at'] = admitted_at
    if deferred:
        data['deferred'] = True
    if finalization_job_id:
        data['finalization_job_id'] = finalization_job_id
    store.set(_conv_path(uid, cid), data)


def _admit_finalization(_conversation_data: dict) -> jobs.FinalizationAdmission:
    return {
        'accepted': True,
        'terminal': False,
        'reason': 'accepted',
        'fanout_key': 'fanout-key',
    }


# --- create-or-get finalization intent (outbox admission) ---


def test_intent_persists_outbox_before_any_live_handoff_and_omits_byok_material(store):
    _seed_conversation(store, 'uid-1', 'conversation-1')

    intent = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=_admit_finalization
    )

    assert intent['status'] == 'queued'
    assert intent['job_id']
    job = store.get(_job_path(intent['job_id'])).to_dict()
    assert job['uid'] == 'uid-1'
    assert job['conversation_id'] == 'conversation-1'
    assert job['dispatch_generation'] == 1
    assert job['status'] == 'queued'
    assert job['fanout_key'] == 'fanout-key'
    assert job['fanout_status'] == 'pending'
    forbidden = {'byok_keys', 'transcript', 'transcript_segments', 'authorization', 'raw_error'}
    assert forbidden.isdisjoint(job)
    conversation = store.get(_conv_path('uid-1', 'conversation-1')).to_dict()
    assert conversation['status'] == 'processing'
    assert conversation['finalization_job_id'] == intent['job_id']


def test_rest_intent_persists_its_force_mode_and_calendar_context_atomically(store):
    _seed_conversation(store, 'uid-1', 'conversation-1')

    intent = jobs.create_or_get_finalization_intent(
        'uid-1',
        'conversation-1',
        requires_byok=False,
        finalization_admission=_admit_finalization,
        force_process=True,
        extra_updates={'external_data': {'calendar_meeting_context': {'event_id': 'event-1'}}},
    )

    assert store.get(_job_path(intent['job_id'])).to_dict()['force_process'] is True
    conversation = store.get(_conv_path('uid-1', 'conversation-1')).to_dict()
    assert conversation['external_data'] == {'calendar_meeting_context': {'event_id': 'event-1'}}
    assert conversation['status'] == 'processing'
    assert conversation['finalization_job_id'] == intent['job_id']
    assert conversation['finalization_revision'] == 1
    assert conversation['finalization_status'] == 'queued'


def test_create_or_get_intent_is_idempotent_and_counts_acceptance_once(store):
    """A reconnect/retry reuses the same durable job and never double-counts acceptance.

    The store owns the transaction retry that the retired
    ``run_with_transaction_contention_retry`` used to provide; this pins the
    idempotency guarantee that a replayed admission commits exactly one job and
    one accepted projection delta.
    """
    _seed_conversation(store, 'uid-1', 'conversation-1')

    first = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=_admit_finalization
    )
    assert first['created'] is True

    second = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=_admit_finalization
    )
    assert second['job_id'] == first['job_id']
    assert second['created'] is False

    assert list(store.list_ids('conversation_finalization_jobs')) == [first['job_id']]
    shard = jobs._projection_shard(first['job_id'])
    shard_doc = store.get(_shard_path(shard)).to_dict()
    assert shard_doc['accepted'] == 1
    assert shard_doc['queued'] == 1


def test_photo_only_conversation_with_durable_content_marker_is_admitted(store):
    _seed_conversation(store, 'uid-1', 'conversation-1', {'transcript_segments': [], 'has_content': True})

    intent = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=_admit_finalization
    )

    assert intent['status'] == 'queued'
    assert store.get(_conv_path('uid-1', 'conversation-1')).to_dict()['status'] == 'processing'
    assert store.exists(_job_path(intent['job_id']))


def test_legacy_photo_only_conversation_is_admitted_from_its_child_document(store):
    _seed_conversation(
        store, 'uid-1', 'conversation-1', {'transcript_segments': [], 'has_content': False}, has_legacy_photo=True
    )

    intent = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=_admit_finalization
    )

    assert intent['status'] == 'queued'
    assert store.get(_conv_path('uid-1', 'conversation-1')).to_dict()['status'] == 'processing'


def test_photo_only_conversation_without_content_or_photos_is_not_admitted(store):
    _seed_conversation(store, 'uid-1', 'conversation-1', {'transcript_segments': [], 'has_content': False})

    intent = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=_admit_finalization
    )

    assert intent['status'] == 'no_content'
    assert intent['job_id'] is None
    assert list(store.list_ids('conversation_finalization_jobs')) == []


def test_duplicate_reconnect_reuses_the_same_outbox_job(store):
    _seed_conversation(
        store,
        'uid-1',
        'conversation-1',
        {'status': 'processing', 'finalization_job_id': 'job-1', 'finalization_revision': 1},
    )
    store.set(_job_path('job-1'), {'status': 'queued', 'dispatch_generation': 1, 'requires_byok': False})
    before = store.get(_conv_path('uid-1', 'conversation-1')).to_dict()

    intent = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=_admit_finalization
    )

    assert intent == {
        'job_id': 'job-1',
        'status': 'queued',
        'dispatch_generation': 1,
        'requires_byok': False,
        'fanout_key': None,
        'created': False,
    }
    # No second job, no conversation mutation, no projection write.
    assert list(store.list_ids('conversation_finalization_jobs')) == ['job-1']
    assert store.get(_conv_path('uid-1', 'conversation-1')).to_dict() == before
    assert list(store.list_ids('conversation_finalization_projection_shards')) == []


def test_duplicate_finalization_intent_keeps_the_same_processing_admission(store):
    """Characterize #2d67863cad: a disconnect/reconnect never starts a second job.

    The first finalization transaction already moved the conversation to
    ``processing``.  A later finalizer must reuse that durable identity without
    another conversation write, so a future service migration cannot re-open the
    disconnect race while rearranging the handoff.
    """
    _seed_conversation(
        store,
        'uid-1',
        'conversation-1',
        {'status': 'processing', 'finalization_job_id': 'job-1', 'finalization_revision': 1},
    )
    store.set(_job_path('job-1'), {'status': 'queued', 'dispatch_generation': 1, 'requires_byok': False})
    before = store.get(_conv_path('uid-1', 'conversation-1')).to_dict()

    intent = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=_admit_finalization
    )

    assert intent['job_id'] == 'job-1'
    assert intent['dispatch_generation'] == 1
    assert store.get(_conv_path('uid-1', 'conversation-1')).to_dict() == before


def test_byok_job_is_explicitly_blocked_without_persisting_a_key(store):
    _seed_conversation(store, 'uid-1', 'conversation-1')

    intent = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=True, finalization_admission=_admit_finalization
    )

    assert intent['status'] == 'blocked_byok'
    persisted = store.get(_job_path(intent['job_id'])).to_dict()
    assert persisted['requires_byok'] is True
    assert set(persisted).isdisjoint({'byok_keys', 'openai', 'anthropic', 'gemini', 'deepgram'})


def test_atomic_admission_rejects_terminal_snapshot_before_any_outbox_write(store):
    _seed_conversation(store, 'uid-1', 'conversation-1', {'status': 'failed'})

    def terminal(_conversation_data: dict) -> jobs.FinalizationAdmission:
        return {'accepted': False, 'terminal': True, 'reason': 'terminal', 'fanout_key': None}

    intent = jobs.create_or_get_finalization_intent(
        'uid-1', 'conversation-1', requires_byok=False, finalization_admission=terminal
    )

    assert intent['status'] == 'terminal'
    assert list(store.list_ids('conversation_finalization_jobs')) == []
    assert store.get(_conv_path('uid-1', 'conversation-1')).to_dict()['status'] == 'failed'


# --- claim / lease ---


def test_duplicate_task_delivery_claims_only_once_until_lease_expires(store, now):
    store.set(_job_path('job-1'), {'status': 'queued', 'dispatch_generation': 2, 'attempt_count': 0})

    claim = jobs.claim_finalization_job('job-1', 2)
    assert claim == {'status': 'claimed', 'lease_epoch': 1, 'attempt_count': 1, 'created_at': None}
    job = store.get(_job_path('job-1')).to_dict()
    assert job['status'] == 'leased'
    assert job['attempt_count'] == 1

    duplicate = jobs.claim_finalization_job('job-1', 2)
    assert duplicate == {'status': 'leased', 'lease_epoch': None, 'attempt_count': 0, 'created_at': None}


def test_expired_worker_lease_can_be_safely_reclaimed(store, now):
    store.set(
        _job_path('job-1'),
        {
            'status': 'leased',
            'dispatch_generation': 2,
            'attempt_count': 1,
            'lease_expires_at': now - timedelta(seconds=1),
        },
    )

    claim = jobs.claim_finalization_job('job-1', 2)
    assert claim == {'status': 'claimed', 'lease_epoch': 1, 'attempt_count': 2, 'created_at': None}
    job = store.get(_job_path('job-1')).to_dict()
    assert job['attempt_count'] == 2
    assert job['lease_epoch'] == 1


def test_live_pusher_claim_cannot_use_another_conversations_job(store, now):
    store.set(
        _job_path('job-1'),
        {'status': 'queued', 'dispatch_generation': 1, 'uid': 'owner-uid', 'conversation_id': 'owner-conversation'},
    )
    before = store.get(_job_path('job-1')).to_dict()

    status = jobs.claim_finalization_job(
        'job-1', 1, expected_uid='other-uid', expected_conversation_id='other-conversation'
    )

    assert status == {'status': 'identity_mismatch', 'lease_epoch': None, 'attempt_count': 0, 'created_at': None}
    assert store.get(_job_path('job-1')).to_dict() == before


def test_completed_and_dead_letter_jobs_never_execute_again(store, now):
    for status in ('completed', 'dead_letter'):
        store.set(_job_path('job-1'), {'status': status, 'dispatch_generation': 1})
        before = store.get(_job_path('job-1')).to_dict()
        assert jobs.claim_finalization_job('job-1', 1) == {
            'status': status,
            'lease_epoch': None,
            'attempt_count': 0,
            'created_at': None,
        }
        assert store.get(_job_path('job-1')).to_dict() == before


def test_completed_fenced_job_replays_as_a_fenced_result(store, now):
    store.set(
        _job_path('job-1'),
        {'status': 'completed', 'finalization_outcome': 'fenced', 'dispatch_generation': 1},
    )

    claim = jobs.claim_finalization_job('job-1', 1)

    assert claim == {'status': 'fenced', 'lease_epoch': None, 'attempt_count': 0, 'created_at': None}


# --- completion / fanout ownership ---


def test_finalization_completion_requires_durable_fanout_completion(store, now):
    store.set(
        _job_path('job-1'),
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
    store.set(
        _conv_path('uid-1', 'conversation-1'),
        {
            'status': 'completed',
            'discarded': False,
            'finalization_job_id': 'job-1',
            'finalization_revision': 1,
            'transcript_segments': [{'text': 'x'}],
        },
    )

    assert jobs.mark_finalization_completed('job-1', 1, 4) is False

    claim = jobs.claim_finalization_fanout('job-1', 1, 4)
    assert claim == {'status': 'claimed', 'fanout_key': 'conversation:conversation-1:finalization:1'}

    assert jobs.mark_finalization_fanout_completed('job-1', 1, 4) is True
    assert jobs.mark_finalization_completed('job-1', 1, 4) is True
    assert store.get(_job_path('job-1')).to_dict()['terminal_outcome'] == 'success'


def test_admitted_terminal_replay_updates_its_shard_once(store, now):
    shard = jobs._projection_shard('job-1')
    store.set(
        _job_path('job-1'),
        {
            'status': 'leased',
            'dispatch_generation': 1,
            'lease_epoch': 4,
            'fanout_status': 'completed',
            'projection_generation': _GEN,
            'projection_shard': shard,
        },
    )

    assert jobs.mark_finalization_completed('job-1', 1, 4) is True
    shard_doc = store.get(_shard_path(shard)).to_dict()
    assert shard_doc['generation'] == _GEN and shard_doc['shard'] == shard
    assert shard_doc['completed'] == 1 and shard_doc['success'] == 1 and shard_doc['leased'] == -1

    # A store retry observes the committed terminal snapshot and performs no
    # second aggregate write, even though the API remains idempotently true.
    assert jobs.mark_finalization_completed('job-1', 1, 4) is True
    assert store.get(_shard_path(shard)).to_dict() == shard_doc


def test_pre_projection_terminal_keeps_its_outcome_without_moving_the_new_denominator(store, now):
    store.set(
        _job_path('legacy-job'),
        {'status': 'leased', 'dispatch_generation': 1, 'lease_epoch': 1, 'fanout_status': 'completed'},
    )

    assert jobs.mark_finalization_completed('legacy-job', 1, 1) is True
    assert store.get(_job_path('legacy-job')).to_dict()['terminal_outcome'] == 'success'
    assert list(store.list_ids('conversation_finalization_projection_shards')) == []


def test_byok_resume_moves_only_its_admitted_projection_state(store, now):
    store.set(
        _job_path('job-1'),
        {
            'status': 'blocked_byok',
            'requires_byok': True,
            'projection_generation': _GEN,
            'projection_shard': 3,
        },
    )

    intent = jobs.resume_blocked_byok_job_for_live_session('job-1')

    assert intent['status'] == 'queued'
    assert store.get(_job_path('job-1')).to_dict()['status'] == 'queued'
    shard_doc = store.get(_shard_path(3)).to_dict()
    assert shard_doc['blocked_byok'] == -1 and shard_doc['queued'] == 1


def test_fanout_claim_terminally_fences_a_discard_that_wins_before_its_transaction(store, now):
    """A processor may finish while a disconnect discard wins the fanout race.

    The store retries this transaction if the conversation changes after its
    read. This fixture represents the retried transaction snapshot after that
    discard, which must both reject integrations and close the job rather than
    make it retryable or eligible for a dead letter.
    """
    store.set(
        _job_path('job-1'),
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
    store.set(
        _conv_path('uid-1', 'conversation-1'),
        {
            'status': 'completed',
            'discarded': True,
            'finalization_job_id': 'job-1',
            'finalization_revision': 1,
        },
    )

    claim = jobs.claim_finalization_fanout('job-1', 1, 4)

    assert claim == {'status': 'fenced', 'fanout_key': 'conversation:conversation-1:finalization:1'}
    job = store.get(_job_path('job-1')).to_dict()
    assert job['status'] == 'completed'
    assert job['finalization_outcome'] == 'fenced'
    assert job['terminal_outcome'] == 'stale'
    assert job['fanout_status'] == 'fenced'


def test_fanout_claim_terminally_fences_a_superseded_finalization_binding(store, now):
    store.set(
        _job_path('job-1'),
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
    # The conversation is now owned by a newer finalization generation (job-2 / rev 2).
    store.set(
        _conv_path('uid-1', 'conversation-1'),
        {
            'status': 'completed',
            'discarded': False,
            'finalization_job_id': 'job-2',
            'finalization_revision': 2,
        },
    )

    claim = jobs.claim_finalization_fanout('job-1', 1, 4)

    assert claim == {'status': 'fenced', 'fanout_key': 'conversation:conversation-1:finalization:1'}
    job = store.get(_job_path('job-1')).to_dict()
    assert job['fanout_status'] == 'fenced'
    assert job['finalization_outcome'] == 'fenced'


def test_fenced_finalization_is_a_terminal_no_fanout_outcome(store, now):
    store.set(
        _job_path('job-1'),
        {'status': 'leased', 'dispatch_generation': 1, 'lease_epoch': 4, 'fanout_status': 'pending'},
    )

    assert jobs.mark_finalization_fenced('job-1', 1, 4) is True
    job = store.get(_job_path('job-1')).to_dict()
    assert job['status'] == 'completed'
    assert job['finalization_outcome'] == 'fenced'
    assert job['terminal_outcome'] == 'stale'
    assert job['fanout_status'] == 'fenced'


# --- replay / dead-letter ---


def test_reconciler_replaces_stale_generation_after_worker_crash(store, now):
    store.set(
        _job_path('job-1'),
        {
            'status': 'leased',
            'dispatch_generation': 4,
            'requires_byok': False,
            'lease_expires_at': now - timedelta(seconds=1),
        },
    )

    intent = jobs.claim_finalization_replay('job-1', stale_after=timedelta(minutes=5))

    assert intent['status'] == 'queued'
    assert intent['dispatch_generation'] == 5
    assert store.get(_job_path('job-1')).to_dict()['dispatch_generation'] == 5


def test_expired_lease_reclaim_fences_a_stale_worker_terminal_write(store, now):
    store.set(
        _job_path('job-1'),
        {
            'status': 'leased',
            'dispatch_generation': 3,
            'lease_epoch': 4,
            'lease_expires_at': now - timedelta(seconds=1),
            'fanout_status': 'completed',
        },
    )

    new_claim = jobs.claim_finalization_job('job-1', 3)
    assert new_claim == {'status': 'claimed', 'lease_epoch': 5, 'attempt_count': 1, 'created_at': None}

    # The stale worker's terminal write (epoch 4) is fenced; only the current epoch (5) commits.
    assert jobs.mark_finalization_completed('job-1', 3, 4) is False
    assert jobs.mark_finalization_completed('job-1', 3, 5) is True


def test_final_attempt_sets_visible_dead_letter_instead_of_completed(store, now):
    store.set(_job_path('job-1'), {'status': 'leased', 'dispatch_generation': 3, 'lease_epoch': 1})

    assert jobs.mark_finalization_dead_letter('job-1', 3, 1, 5) is True
    job = store.get(_job_path('job-1')).to_dict()
    assert job['status'] == 'dead_letter'
    assert job['terminal_outcome'] == 'failure'
    assert job['task_retry_count'] == 5
    assert 'completed_at' not in job


def test_final_attempt_atomically_closes_its_bound_processing_conversation(store, now):
    store.set(
        _job_path('job-1'),
        {
            'status': 'leased',
            'uid': 'uid-1',
            'conversation_id': 'conversation-1',
            'finalization_revision': 3,
            'dispatch_generation': 3,
            'lease_epoch': 1,
        },
    )
    store.set(
        _conv_path('uid-1', 'conversation-1'),
        {
            'status': 'processing',
            'discarded': False,
            'finalization_job_id': 'job-1',
            'finalization_revision': 3,
            'transcript_segments': [{'text': 'x'}],
        },
    )

    assert jobs.mark_finalization_dead_letter('job-1', 3, 1, 5) is True

    job = store.get(_job_path('job-1')).to_dict()
    assert job['status'] == 'dead_letter'
    assert job['terminal_outcome'] == 'failure'
    assert job['task_retry_count'] == 5
    assert 'reconcile_after_at' not in job  # DELETE sentinel removed the field
    conversation = store.get(_conv_path('uid-1', 'conversation-1')).to_dict()
    assert conversation['status'] == 'failed'
    assert conversation['discarded'] is True
    assert conversation['finalization_status'] == 'dead_letter'


# --- metrics / bounded queries ---


def test_durable_summary_reads_a_fixed_projection_shard_set_without_job_aggregations(store, now):
    # Totals derive ONLY from the fixed projection generation shards; the jobs
    # collection is never aggregated (a seeded job must not move any total).
    store.set(
        _shard_path(0),
        {
            'generation': _GEN,
            'shard': 0,
            'accepted': 8,
            'queued': 2,
            'leased': 1,
            'blocked_byok': 2,
            'completed': 2,
            'dead_letter': 1,
            'success': 1,
            'stale': 1,
            'failure': 1,
        },
    )
    store.set(_job_path('ignored'), {'status': 'completed', 'terminal_outcome': 'success'})

    summary = jobs.get_finalization_job_summary()

    assert summary == {
        'accepted': 8,
        'success': 1,
        'failure': 1,
        'stale': 1,
        'nonterminal': 3,
        'queued': 2,
        'leased': 1,
        'blocked_byok': 2,
        'completed': 2,
        'dead_letter': 1,
        'terminal_unknown': 0,
        'oldest_nonterminal_age_seconds': 0.0,
    }


def test_replay_candidates_use_a_server_side_bounded_due_query(store, now):
    # A terminal due row is excluded; the server-side page is clamped to 100.
    for i in range(105):
        store.set(_job_path(f'q{i:03d}'), {'status': 'queued', 'reconcile_after_at': now - timedelta(seconds=1)})
    store.set(_job_path('terminal'), {'status': 'completed', 'reconcile_after_at': now - timedelta(seconds=1)})

    candidates = jobs.get_finalization_replay_candidates(limit=1000)

    assert len(candidates) == 100
    assert all(candidate['status'] == 'queued' for candidate in candidates)
    assert all('job_id' in candidate for candidate in candidates)


# ---------------------------------------------------------------------------
# Stale bare-processing orphan recovery (#10461 revision): authoritative
# server-owned admission fence, bounded cursor pagination, and legacy migration.
# ---------------------------------------------------------------------------


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


def test_stale_orphan_sweep_is_cross_parent_on_processing_status(store, now):
    """A collection-group ``status == 'processing'`` sweep spans every parent uid."""
    aged = now - timedelta(hours=1)
    _seed_processing(store, 'uid-a', 'c1', admitted_at=aged)
    _seed_processing(store, 'uid-b', 'c2', admitted_at=aged)
    # A non-processing row under a third parent must be excluded by the equality filter.
    store.set(_conv_path('uid-c', 'c3'), {'status': 'completed', 'processing_admitted_at': aged})

    result = jobs.get_stale_processing_orphan_candidates(stale_after=timedelta(seconds=900))

    got = {(candidate['uid'], candidate['conversation_id']) for candidate in result['candidates']}
    assert got == {('uid-a', 'c1'), ('uid-b', 'c2')}


def test_stale_orphan_age_authority_is_processing_admitted_at_not_created_at(store, now):
    """Only the server-owned admission stamp bounds age; caller-controlled
    created_at is never the authority, and legacy rows migrate rather than
    complete."""
    stale_after = timedelta(seconds=900)
    # Fresh admission, ancient caller-controlled created_at: must NOT act.
    _seed_processing(
        store, 'uid', 'fresh-admit-old-create', admitted_at=now - timedelta(seconds=10),
        created_at=now - timedelta(days=30),
    )
    # Aged admission, fresh created_at: the genuine orphan — must act.
    _seed_processing(
        store, 'uid', 'aged-admit-fresh-create', admitted_at=now - timedelta(seconds=1000),
        created_at=now - timedelta(seconds=5),
    )
    # Legacy row with no admission stamp: migrate, never complete on sight.
    _seed_processing(store, 'uid', 'legacy-no-admit', admitted_at=None, created_at=now - timedelta(days=30))

    candidates = jobs.get_stale_processing_orphan_candidates(stale_after=stale_after)['candidates']

    by_id = {candidate['conversation_id']: candidate for candidate in candidates}
    assert 'fresh-admit-old-create' not in by_id
    eligible = by_id['aged-admit-fresh-create']
    assert eligible['legacy'] is False
    assert eligible['processing_admitted_at'] == now - timedelta(seconds=1000)
    legacy = by_id['legacy-no-admit']
    assert legacy['legacy'] is True
    assert legacy['processing_admitted_at'] is None


def test_stale_orphan_candidates_exclude_deferred_and_durable_job_rows(store, now):
    aged = now - timedelta(seconds=1000)
    _seed_processing(store, 'uid', 'deferred', admitted_at=aged, deferred=True)
    _seed_processing(store, 'uid', 'durable', admitted_at=aged, finalization_job_id='job-x')
    _seed_processing(store, 'uid', 'orphan', admitted_at=aged)

    candidates = jobs.get_stale_processing_orphan_candidates(stale_after=timedelta(seconds=900))['candidates']

    assert [candidate['conversation_id'] for candidate in candidates] == ['orphan']


def test_stale_orphan_candidates_page_past_excluded_rows_to_reach_a_later_orphan(store, now, monkeypatch):
    """A stable first page of excluded rows cannot hide a later eligible orphan."""
    aged = now - timedelta(seconds=1000)
    for i in range(120):
        _seed_processing(store, 'uid', f'deferred-{i:03d}', admitted_at=aged, deferred=True)
    # 'later-orphan' sorts after every 'deferred-*' path, so it can only be reached on a later page.
    _seed_processing(store, 'uid', 'later-orphan', admitted_at=aged)

    pages: list[str | None] = []
    original = store.query_group

    def spy(*args, **kwargs):
        pages.append(kwargs.get('start_after'))
        return original(*args, **kwargs)

    monkeypatch.setattr(store, 'query_group', spy)

    candidates = jobs.get_stale_processing_orphan_candidates(stale_after=timedelta(seconds=900))['candidates']

    assert [candidate['conversation_id'] for candidate in candidates] == ['later-orphan']
    # The first page was entirely excluded, so at least two query pages with a cursor were issued.
    assert len(pages) >= 2
    assert any(cursor is not None for cursor in pages[1:])


def test_stale_orphan_candidates_bound_total_scan(store, now):
    """The per-sweep scan bound prevents an unbounded walk under backlog."""
    aged = now - timedelta(seconds=1000)
    for i in range(50):
        _seed_processing(store, 'uid', f'deferred-{i:02d}', admitted_at=aged, deferred=True)
    _seed_processing(store, 'uid', 'later-orphan', admitted_at=aged)

    bounded = jobs.get_stale_processing_orphan_candidates(stale_after=timedelta(seconds=900), max_scan=10)['candidates']
    # The bound stops scanning before the orphan (which sorts last) is reached.
    assert bounded == []

    recovered = jobs.get_stale_processing_orphan_candidates(
        stale_after=timedelta(seconds=900), max_scan=10_000
    )['candidates']
    assert [candidate['conversation_id'] for candidate in recovered] == ['later-orphan']


def test_persisted_cursor_reaches_a_later_orphan_beyond_any_per_invocation_bound(store, now):
    """A rotated wraparound cursor guarantees eventual discovery.

    A stable excluded prefix larger than every per-invocation ``max_scan`` would
    permanently hide a later orphan if each sweep restarted from the top. The
    sweep instead resumes from a persisted cursor and wraps to the top once the
    collection is exhausted, so repeated bounded sweeps reach the orphan.
    """
    aged = now - timedelta(seconds=1000)
    # An excluded prefix far larger than the per-invocation bound, then one orphan.
    for i in range(2500):
        _seed_processing(store, 'uid', f'deferred-{i:04d}', admitted_at=aged, deferred=True)
    _seed_processing(store, 'uid', 'later-orphan', admitted_at=aged)

    recovered: list[dict] = []
    resume_after_path = None
    sweeps = 0
    for _ in range(10):
        sweeps += 1
        result = jobs.get_stale_processing_orphan_candidates(
            stale_after=timedelta(seconds=900), max_scan=1000, resume_after_path=resume_after_path
        )
        recovered.extend(result['candidates'])
        resume_after_path = None if result['exhausted'] else result['resume_after_path']
        if any(candidate['conversation_id'] == 'later-orphan' for candidate in recovered):
            break

    assert [candidate['conversation_id'] for candidate in recovered] == ['later-orphan']
    # More than one bounded sweep was required: the orphan sits beyond max_scan.
    assert sweeps >= 2


def test_persisted_cursor_wraps_to_the_top_when_the_resume_document_is_gone(store, now):
    """A deleted cursor document must not strand the sweep: it resumes from the top."""
    aged = now - timedelta(seconds=1000)
    _seed_processing(store, 'uid', 'orphan', admitted_at=aged)

    result = jobs.get_stale_processing_orphan_candidates(
        stale_after=timedelta(seconds=900), resume_after_path='users/uid/conversations/does-not-exist'
    )

    assert [candidate['conversation_id'] for candidate in result['candidates']] == ['orphan']
    assert result['exhausted'] is True


def test_stamp_processing_admission_if_absent_only_stamps_a_legacy_processing_row(store, now):
    store.set(_conv_path('uid', 'legacy'), {'status': 'processing', 'created_at': now - timedelta(days=1)})

    assert jobs.stamp_processing_admission_if_absent('uid', 'legacy') is True
    assert store.get(_conv_path('uid', 'legacy')).to_dict()['processing_admitted_at'] == now


def test_stamp_processing_admission_if_absent_is_idempotent_and_fences_non_processing(store, now):
    store.set(
        _conv_path('uid', 'already'),
        {'status': 'processing', 'processing_admitted_at': now - timedelta(hours=2)},
    )
    store.set(_conv_path('uid', 'terminal'), {'status': 'completed'})

    assert jobs.stamp_processing_admission_if_absent('uid', 'already') is False
    assert jobs.stamp_processing_admission_if_absent('uid', 'terminal') is False
    assert store.get(_conv_path('uid', 'already')).to_dict()['processing_admitted_at'] == now - timedelta(hours=2)


# ---------------------------------------------------------------------------
# Ownership fence (#10461 revision 2): the recovery transaction verifies the
# exact orphan generation/ownership immediately before terminalization.
# ---------------------------------------------------------------------------


def test_complete_orphan_completes_only_an_unchanged_orphan_generation(store, now):
    admitted = now - timedelta(seconds=1000)
    store.set(_conv_path('uid', 'orphan'), {'status': 'processing', 'processing_admitted_at': admitted})

    assert jobs.complete_orphan_conversation('uid', 'orphan', expected_admitted_at=admitted) is True
    assert store.get(_conv_path('uid', 'orphan')).to_dict()['status'] == 'completed'


def test_complete_orphan_fences_a_row_a_finalizer_claimed_after_discovery(store, now):
    admitted = now - timedelta(seconds=1000)
    # Between discovery (job-less) and terminalization, a finalizer attached durable ownership.
    store.set(
        _conv_path('uid', 'claimed'),
        {'status': 'processing', 'processing_admitted_at': admitted, 'finalization_job_id': 'job-1'},
    )

    assert jobs.complete_orphan_conversation('uid', 'claimed', expected_admitted_at=admitted) is False
    assert store.get(_conv_path('uid', 'claimed')).to_dict()['status'] == 'processing'


def test_complete_orphan_fences_a_live_processor_that_renewed_its_lease(store, now):
    scanned = now - timedelta(seconds=1000)
    # A live processor renewed its lease after discovery, advancing the generation.
    store.set(
        _conv_path('uid', 'renewed'),
        {'status': 'processing', 'processing_admitted_at': now - timedelta(seconds=5)},
    )

    assert jobs.complete_orphan_conversation('uid', 'renewed', expected_admitted_at=scanned) is False
    assert store.get(_conv_path('uid', 'renewed')).to_dict()['status'] == 'processing'


def test_complete_orphan_fences_deferred_and_terminal_and_discarded_rows(store, now):
    admitted = now - timedelta(seconds=1000)
    store.set(
        _conv_path('uid', 'deferred'),
        {'status': 'processing', 'processing_admitted_at': admitted, 'deferred': True},
    )
    store.set(_conv_path('uid', 'terminal'), {'status': 'completed', 'processing_admitted_at': admitted})
    store.set(
        _conv_path('uid', 'discarded'),
        {'status': 'processing', 'processing_admitted_at': admitted, 'discarded': True},
    )

    assert jobs.complete_orphan_conversation('uid', 'deferred', expected_admitted_at=admitted) is False
    assert jobs.complete_orphan_conversation('uid', 'terminal', expected_admitted_at=admitted) is False
    assert jobs.complete_orphan_conversation('uid', 'discarded', expected_admitted_at=admitted) is False


def test_renew_processing_lease_refreshes_only_a_live_processing_row(store, now):
    store.set(
        _conv_path('uid', 'processing'),
        {'status': 'processing', 'processing_admitted_at': now - timedelta(seconds=120)},
    )
    store.set(_conv_path('uid', 'completed'), {'status': 'completed'})
    store.set(_conv_path('uid', 'discarded'), {'status': 'processing', 'discarded': True})

    assert jobs.renew_processing_lease('uid', 'processing') is True
    assert store.get(_conv_path('uid', 'processing')).to_dict()['processing_admitted_at'] == now
    assert jobs.renew_processing_lease('uid', 'completed') is False
    assert jobs.renew_processing_lease('uid', 'discarded') is False


# --- CAS sweep cursor ---


def test_advance_cursor_succeeds_when_generation_matches(store, now):
    """CAS cursor advance: a writer holding the current generation commits and bumps it."""
    store.set(_cursor_path(), {'resume_after_path': 'users/u/c/a', 'generation': 3})

    assert jobs.advance_stale_processing_sweep_cursor(3, 'users/u/c/b') is True
    cursor = store.get(_cursor_path()).to_dict()
    assert cursor['resume_after_path'] == 'users/u/c/b'
    assert cursor['generation'] == 4
    assert cursor['updated_at'] == now


def test_advance_cursor_fails_when_generation_changed(store, now):
    """CAS cursor advance: a writer with a stale generation is fenced out — no rewind."""
    store.set(_cursor_path(), {'resume_after_path': 'users/u/c/x', 'generation': 5})

    assert jobs.advance_stale_processing_sweep_cursor(3, 'users/u/c/b') is False
    cursor = store.get(_cursor_path()).to_dict()
    assert cursor['resume_after_path'] == 'users/u/c/x'
    assert cursor['generation'] == 5


def test_advance_cursor_succeeds_on_first_write_when_doc_absent(store, now):
    """First-ever cursor advance: absent doc is generation 0, expected 0 succeeds."""
    assert jobs.advance_stale_processing_sweep_cursor(0, 'users/u/c/first') is True
    cursor = store.get(_cursor_path()).to_dict()
    assert cursor['generation'] == 1
    assert cursor['resume_after_path'] == 'users/u/c/first'
