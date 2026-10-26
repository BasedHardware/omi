"""Atomic durable admission and exact lease/generation rollback fences."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from database import conversation_merge_jobs as jobs
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore

NOW = datetime(2026, 10, 22, tzinfo=timezone.utc)


@pytest.fixture
def store(monkeypatch):
    owner = uuid4().hex
    client = StrictFirestore({('users', owner, 'conversations', cid): {'status': 'completed'} for cid in ('a', 'b')})
    monkeypatch.setattr(jobs, '_now', lambda: NOW)
    return client, owner


def admit(store):
    client, owner = store
    return jobs.admit(owner, ['a', 'b'], True, firestore_client=client)


def row(store, cid):
    return store[0].rows[('users', store[1], 'conversations', cid)]


def jobrow(store, job):
    return store[0].rows[(jobs.COLLECTION, job['job_id'])]


def test_admission_is_one_transaction_and_second_claim_cannot_strand_half_the_sources(store):
    job = admit(store)
    assert job['kind'] == 'conversation_merge' and job['status'] == 'queued'
    assert all(row(store, cid)['merge_job_id'] == job['job_id'] for cid in ('a', 'b'))
    assert admit(store) is None
    assert len(store[0].rows) == 3
    tx = store[0].transactions[0]
    assert len(tx.creates) == 1 and len(tx.updates) == 2


@pytest.mark.parametrize('patch', [{'status': 'processing'}, {'deleted': True}, {'is_locked': True}])
def test_admission_rereads_compatibility_before_any_source_mutation(store, patch):
    row(store, 'b').update(patch)
    assert admit(store) is None
    assert row(store, 'a')['status'] == 'completed'
    assert not any(tx.creates or tx.updates for tx in store[0].transactions)


@pytest.mark.parametrize('account', [True, False])
def test_account_or_conversation_deletion_fences_admission(store, account):
    client, owner = store
    path = ('account_deletions', owner) if account else ('users', owner, 'deleted_conversations', 'a')
    client.rows[path] = {'deleted': True}
    assert admit(store) is None
    assert row(store, 'a')['status'] == 'completed'


def test_claim_renew_and_finish_require_current_unexpired_epoch(store, monkeypatch):
    job = admit(store)
    claimed = jobs.claim(job['job_id'], firestore_client=store[0])
    assert claimed['lease_epoch'] == 1
    assert jobs.claim(job['job_id'], firestore_client=store[0]) is None
    assert not jobs.renew(job['job_id'], 0, firestore_client=store[0])
    assert jobs.renew(job['job_id'], 1, firestore_client=store[0])
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE + timedelta(seconds=1))
    assert not jobs.renew(job['job_id'], 1, firestore_client=store[0])
    assert not jobs.finish(job['job_id'], 1, firestore_client=store[0])


def test_expiry_fences_old_worker_and_restores_only_exact_source_bindings(store, monkeypatch):
    job = admit(store)
    jobs.claim(job['job_id'], firestore_client=store[0])
    assert jobs.begin_recovery(job['job_id'], firestore_client=store[0]) is None
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE + timedelta(seconds=1))
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=store[0])
    assert recovery['recovery'] == 'rollback'
    assert not jobs.renew(job['job_id'], 1, firestore_client=store[0])
    row(store, 'b')['merge_job_id'] = 'new-generation'
    assert jobs.finish_recovery(job['job_id'], recovery['lease_epoch'], firestore_client=store[0])
    assert row(store, 'a')['status'] == 'completed'
    assert row(store, 'b')['status'] == 'merging'
    assert row(store, 'b')['merge_job_id'] == 'new-generation'
    assert jobrow(store, job)['phase'] == 'rolled_back'


def test_crash_before_worker_claim_also_rolls_back_durable_admission(store, monkeypatch):
    job = admit(store)
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE)
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=store[0])
    assert jobs.finish_recovery(job['job_id'], recovery['lease_epoch'], firestore_client=store[0])
    assert all(row(store, cid)['status'] == 'completed' for cid in ('a', 'b'))


def test_pretransfer_crash_is_still_safe_to_roll_back(store, monkeypatch):
    job = admit(store)
    jobs.claim(job['job_id'], firestore_client=store[0])
    assert jobs.renew(job['job_id'], 1, phase='source_retraction', firestore_client=store[0])
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE + timedelta(seconds=1))
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=store[0])
    assert recovery['recovery'] == 'rollback'
    assert jobs.finish_recovery(job['job_id'], recovery['lease_epoch'], firestore_client=store[0])
    assert all(row(store, cid)['status'] == 'completed' for cid in ('a', 'b'))


def test_sealed_cleanup_replays_with_new_generation_and_preserves_survivor(store, monkeypatch):
    job = admit(store)
    jobs.claim(job['job_id'], firestore_client=store[0])
    jobrow(store, job)['phase'] = 'source_cleanup'
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE + timedelta(seconds=1))
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=store[0])
    assert recovery['recovery'] == 'resume_cleanup'
    assert recovery['dispatch_generation'] == 2
    assert all(row(store, cid)['status'] == 'merging' for cid in ('a', 'b'))
    assert jobs.claim(job['job_id'], generation=1, firestore_client=store[0]) is None
    assert jobs.claim(job['job_id'], generation=2, firestore_client=store[0])['phase'] == 'source_cleanup'


def test_cleanup_retries_are_bounded_and_keep_survivor_for_manual_recovery(store, monkeypatch):
    job = admit(store)
    jobrow(store, job).update(phase='source_cleanup', attempt_count=5)
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE + timedelta(seconds=1))
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=store[0])
    assert recovery['recovery'] == 'manual'
    assert jobrow(store, job)['failure_code'] == 'merge_cleanup_exhausted'
    assert all(row(store, cid)['status'] == 'merging' for cid in ('a', 'b'))


def test_completion_and_phase_checkpoint_do_not_accept_stale_workers_or_deleted_sources(store):
    job = admit(store)
    jobs.claim(job['job_id'], firestore_client=store[0])
    row(store, 'b')['deleted'] = True
    assert not jobs.renew(job['job_id'], 1, phase='target_started', firestore_client=store[0])
    assert not jobs.finish(job['job_id'], 2, firestore_client=store[0])
    assert jobs.finish(job['job_id'], 1, firestore_client=store[0])
    assert jobrow(store, job)['status'] == 'completed'


def test_merge_admission_retires_legacy_quiet_debt(store):
    from database.quiet_check_retirement import quiet_check_id
    from google.cloud import firestore

    client, uid = store
    paths = [(jobs.COLLECTION, quiet_check_id(uid, cid)) for cid in ('a', 'b')]
    for path in paths:
        client.rows[path] = {
            'kind': 'listen_quiet_check',
            'status': 'waiting_quiet',
            'dispatch_generation': 3,
            'reconcile_after_at': NOW,
        }
    assert admit(store)
    for path in paths:
        assert client.rows[path]['status'] == 'quiet_done'
        assert client.rows[path]['reconcile_after_at'] is firestore.DELETE_FIELD


def test_merge_rollback_retires_old_debt_and_preserves_reopened_owner(store, monkeypatch):
    from database.quiet_check_retirement import quiet_check_id

    client, uid = store
    job = admit(store)
    paths = [(jobs.COLLECTION, quiet_check_id(uid, cid)) for cid in ('a', 'b')]
    for path in paths:
        client.rows[path] = {
            'kind': 'listen_quiet_check',
            'status': 'waiting_quiet',
            'dispatch_generation': 3,
            'reconcile_after_at': NOW,
        }
    row(store, 'b').update(status='in_progress', merge_job_id='new-owner')
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE)
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=client)
    assert jobs.finish_recovery(job['job_id'], recovery['lease_epoch'], firestore_client=client)
    assert client.rows[paths[0]]['status'] == 'quiet_done'
    assert client.rows[paths[1]]['status'] == 'waiting_quiet'


def test_old_partial_merge_source_cannot_be_admitted_as_fresh_input(store):
    row(store, 'a')['transcript_corrections_moved_to'] = 'retained-previous-target'
    assert admit(store) is None
    assert all(row(store, cid)['status'] == 'completed' for cid in ('a', 'b'))
    assert not any(tx.creates or tx.updates for tx in store[0].transactions)


def test_semantic_duplicate_hint_without_transfer_receipt_remains_mergeable(store):
    row(store, 'a').update(dream_duplicate=True, dream_duplicate_of='similar-conversation')
    job = admit(store)
    assert job is not None
    assert all(row(store, cid)['merge_job_id'] == job['job_id'] for cid in ('a', 'b'))
