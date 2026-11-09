"""Revision CAS losses yield durable custody; terminal lifecycle fences do not."""

from database import conversation_processing_recovery as processing_recovery

from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from database import conversation_finalization_jobs as jobs
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 10, 30, tzinfo=timezone.utc)


def system():
    store = StrictFirestore()
    job_ref = store.collection(jobs.FINALIZATION_JOBS_COLLECTION).document('job')
    conv_ref = store.collection('users').document('u').collection('conversations').document('c')
    store.rows[job_ref.path] = {
        'uid': 'u',
        'conversation_id': 'c',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 2,
        'finalization_revision': 1,
        'fanout_status': 'pending',
        'worker_claim_count': 1,
        'lease_counts_worker_attempt': True,
    }
    store.rows[conv_ref.path] = {
        'id': 'c',
        'status': 'processing',
        'discarded': False,
        'finalization_job_id': 'job',
        'finalization_revision': 1,
        'sync_content_revision': 19,
        'processing_admitted_at': NOW - timedelta(seconds=1000),
        'structured': {'title': 'Retained recording'},
    }
    strict_get = job_ref.get

    def job_snapshot(*args, **kwargs):
        snap = strict_get(*args, **kwargs)
        snap.id = job_ref.id
        return snap

    job_ref.get = job_snapshot
    return store, job_ref, conv_ref


def defer(store, job, conv):
    return jobs._defer_sync_revision_fence_txn(store.transaction(), job, lambda *_: conv, 1, 2, 18, NOW)


def test_revision_fence_replays_new_generation_and_completes_exactly_once():
    store, job, conv = system()
    assert defer(store, job, conv)
    assert not defer(store, job, conv)
    assert store.rows[job.path]['worker_claim_count'] == 0
    quiet = NOW + timedelta(seconds=jobs.SYNC_REVISION_QUIET_SECONDS)
    assert not jobs._claim_finalization_replay_txn(store.transaction(), job, timedelta(seconds=300), NOW)['created']
    replay = jobs._claim_finalization_replay_txn(store.transaction(), job, timedelta(seconds=300), quiet)
    assert replay['created'] and replay['dispatch_generation'] == 2
    assert not jobs._claim_finalization_replay_txn(store.transaction(), job, timedelta(seconds=300), NOW)['created']
    claim = jobs._claim_finalization_job_txn(store.transaction(), job, 2, False, 1500, NOW)
    assert claim['status'] == 'claimed'
    # The new processor persisted revision 19; only this generation may fan out.
    store.rows[conv.path]['status'] = 'completed'
    epoch = claim['lease_epoch']
    assert (
        jobs._claim_finalization_fanout_txn(store.transaction(), job, 1, 2, NOW, lambda *_: conv)['status']
        == 'lease_conflict'
    )
    assert (
        jobs._claim_finalization_fanout_txn(store.transaction(), job, 2, epoch, NOW, lambda *_: conv)['status']
        == 'claimed'
    )
    assert jobs._mark_finalization_fanout_completed_txn(store.transaction(), job, 2, epoch, NOW)
    assert jobs._mark_finalization_completed_txn(store.transaction(), job, 2, epoch, NOW)
    assert jobs._claim_finalization_job_txn(store.transaction(), job, 2, False, 1500, NOW)['status'] == 'completed'


@pytest.mark.parametrize(
    'patch',
    [
        {'deleted': True},
        {'discarded': True},
        {'status': 'completed'},
        {'finalization_job_id': 'replacement'},
        {'sync_content_revision': 18},
    ],
)
def test_terminal_or_unchanged_fence_never_redispatches(patch):
    store, job, conv = system()
    store.rows[conv.path].update(patch)
    original = deepcopy(store.rows)
    assert not defer(store, job, conv)
    assert store.rows == original
    assert jobs._mark_finalization_fenced_txn(store.transaction(), job, 1, 2, NOW)
    assert store.rows[job.path]['status'] == 'completed'
    assert store.rows[job.path]['finalization_outcome'] == 'fenced'


@pytest.mark.parametrize('status', ['completed', 'dead_letter', 'queued', 'leased', 'blocked_byok'])
def test_orphan_completion_rechecks_terminal_job_inside_transaction(status):
    store, job, conv = system()
    store.rows[job.path]['status'] = status
    admitted = store.rows[conv.path]['processing_admitted_at']
    done = processing_recovery._complete_orphan_conversation_txn(
        store.transaction(),
        conv,
        admitted,
        NOW,
        job_ref_for_id=lambda _: job,
    )
    assert done == (status in jobs.TERMINAL_JOB_STATUSES)
    assert store.rows[conv.path]['status'] == ('completed' if done else 'processing')
    if done:
        assert not processing_recovery._complete_orphan_conversation_txn(
            store.transaction(),
            conv,
            admitted,
            NOW,
            job_ref_for_id=lambda _: job,
        )


def test_terminal_job_legacy_row_is_migrated_before_aged_completion():
    store, job, conv = system()
    store.rows[job.path]['status'] = 'completed'
    store.rows[conv.path]['processing_admitted_at'] = None
    assert processing_recovery._stamp_processing_admission_if_absent_txn(
        store.transaction(),
        conv,
        NOW,
        job_ref_for_id=lambda _: job,
    )
    assert store.rows[conv.path]['status'] == 'processing'
    assert store.rows[conv.path]['processing_admitted_at'] == NOW


def test_deleted_document_never_redispatches():
    store, job, conv = system()
    del store.rows[conv.path]
    assert not defer(store, job, conv)
    assert jobs._mark_finalization_fenced_txn(store.transaction(), job, 1, 2, NOW)
    assert conv.path not in store.rows


def replay(store, job, conv, now):
    return jobs._claim_finalization_replay_txn(
        store.transaction(),
        job,
        timedelta(seconds=300),
        now,
        conversation_ref_for_job=lambda *_: conv,
    )


def test_repeated_revision_advances_stop_after_three_redispatches_and_allow_sweep():
    store, job, conv = system()
    now, generation, epoch = NOW, 1, 2
    for attempt in range(jobs.SYNC_REVISION_MAX_REDISPATCHES):
        store.rows[conv.path]['sync_content_revision'] = 19 + attempt
        assert jobs._defer_sync_revision_fence_txn(
            store.transaction(), job, lambda *_: conv, generation, epoch, 18 + attempt, now
        )
        # Even an old Cloud Task after the delay cannot bypass replay ownership.
        now += timedelta(seconds=jobs.SYNC_REVISION_QUIET_SECONDS)
        assert (
            jobs._claim_finalization_job_txn(store.transaction(), job, generation, False, 1500, now)['status']
            == 'not_actionable'
        )
        intent = replay(store, job, conv, now)
        assert intent['created']
        generation = intent['dispatch_generation']
        claim = jobs._claim_finalization_job_txn(
            store.transaction(), job, generation, False, 1500, now, count_worker_claim=True
        )
        epoch = claim['lease_epoch']
    store.rows[conv.path]['sync_content_revision'] += 1
    assert not jobs._defer_sync_revision_fence_txn(
        store.transaction(), job, lambda *_: conv, generation, epoch, 21, now
    )
    assert jobs._mark_finalization_fenced_txn(store.transaction(), job, generation, epoch, now)
    assert store.rows[job.path]['sync_revision_redispatch_count'] == 3
    assert processing_recovery._complete_orphan_conversation_txn(
        store.transaction(),
        conv,
        store.rows[conv.path]['processing_admitted_at'],
        now,
        job_ref_for_id=lambda _: job,
    )
    assert store.rows[conv.path]['status'] == 'completed'


def test_advances_while_queued_restart_quiet_window_but_cannot_wait_forever():
    store, job, conv = system()
    assert defer(store, job, conv)
    for seconds in range(30, jobs.SYNC_REVISION_MAX_WAIT_SECONDS, 30):
        store.rows[conv.path]['sync_content_revision'] += 1
        now = NOW + timedelta(seconds=seconds)
        assert not replay(store, job, conv, now)['created']
        assert store.rows[job.path]['sync_revision_not_before'] == now + timedelta(seconds=30)
    intent = replay(store, job, conv, NOW + timedelta(seconds=jobs.SYNC_REVISION_MAX_WAIT_SECONDS))
    assert not intent['created'] and intent['status'] == 'completed'
    assert store.rows[job.path]['last_failure_code'] == 'sync_revision_wait_exhausted'
    assert processing_recovery._complete_orphan_conversation_txn(
        store.transaction(),
        conv,
        store.rows[conv.path]['processing_admitted_at'],
        NOW,
        job_ref_for_id=lambda _: job,
    )


def test_byok_revision_wait_resumes_with_live_credentials_after_quiet_period():
    store, job, conv = system()
    store.rows[job.path]['requires_byok'] = True
    assert defer(store, job, conv)
    assert jobs._claim_finalization_job_txn(store.transaction(), job, 1, True, 1500, NOW)['status'] == 'not_actionable'
    now = NOW + timedelta(seconds=300)
    assert replay(store, job, conv, now)['status'] == 'blocked_byok'
    assert jobs._resume_blocked_byok_job_txn(store.transaction(), job, now)['status'] == 'queued'
    assert jobs._claim_finalization_job_txn(store.transaction(), job, 1, False, 1500, now)['status'] == 'blocked_byok'
    assert jobs._claim_finalization_job_txn(store.transaction(), job, 1, True, 1500, now)['status'] == 'claimed'
    assert not store.rows[job.path]['sync_revision_waiting']
