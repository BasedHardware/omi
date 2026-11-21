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


def finish_clean_rollback(job_id, epoch, *, firestore_client):
    return jobs.finish_recovery(
        job_id, epoch, cleanup_steps=jobs.ROLLBACK_CLEANUP_STEPS, firestore_client=firestore_client
    )


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


def test_restored_account_can_admit_and_claim_conversation_merge(store):
    client, owner = store
    client.rows[('account_deletions', owner)] = {'wipe_status': 'cancelled'}

    job = admit(store)

    assert job is not None
    assert jobs.claim(job['job_id'], firestore_client=client) is not None


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
    assert finish_clean_rollback(job['job_id'], recovery['lease_epoch'], firestore_client=store[0])
    assert row(store, 'a')['status'] == 'completed'
    assert row(store, 'b')['status'] == 'merging'
    assert row(store, 'b')['merge_job_id'] == 'new-generation'
    assert jobrow(store, job)['phase'] == 'rolled_back'


def test_crash_before_worker_claim_also_rolls_back_durable_admission(store, monkeypatch):
    job = admit(store)
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE)
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=store[0])
    assert finish_clean_rollback(job['job_id'], recovery['lease_epoch'], firestore_client=store[0])
    assert all(row(store, cid)['status'] == 'completed' for cid in ('a', 'b'))
    assert all(row(store, cid)['relevance_decision']['verdict'] == 'keep' for cid in ('a', 'b'))


@pytest.fixture(scope='module')
def visible_conversation():
    # Load the production dependency in setup: the call-phase CPU guard measures
    # rollback/visibility work, not the first import of the serving helpers.
    from database.conversations import is_visible_conversation

    return is_visible_conversation


@pytest.mark.parametrize('reason', ['filler_only', 'empty_transcript'])
def test_crash_rollback_preserves_legacy_rule_discard_and_visibility(store, monkeypatch, reason, visible_conversation):
    prior = dict(verdict='discard', decided_by='rule', reason=reason, trigger='capture_end')
    row(store, 'a').update(discarded=False, relevance_decision=prior)
    job = admit(store)
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE)
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=store[0])
    assert finish_clean_rollback(job['job_id'], recovery['lease_epoch'], firestore_client=store[0])
    assert row(store, 'a')['relevance_decision'] == prior
    assert not visible_conversation(row(store, 'a'))


def test_pretransfer_crash_is_still_safe_to_roll_back(store, monkeypatch):
    job = admit(store)
    jobs.claim(job['job_id'], firestore_client=store[0])
    assert jobs.renew(job['job_id'], 1, phase='source_retraction', firestore_client=store[0])
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE + timedelta(seconds=1))
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=store[0])
    assert recovery['recovery'] == 'rollback'
    assert finish_clean_rollback(job['job_id'], recovery['lease_epoch'], firestore_client=store[0])
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
    assert finish_clean_rollback(job['job_id'], recovery['lease_epoch'], firestore_client=client)
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


@pytest.fixture(scope='module')
def go_retraction_ports():
    from database import sync_jobs
    from utils.account_cutover import access
    from utils.conversations import merge_conversations as merge
    from utils.conversations import merge_conversations_job as worker

    return sync_jobs, access, merge, worker


def test_go_retraction_requires_current_sealed_lease_and_live_target(store, monkeypatch, go_retraction_ports):
    from unittest.mock import Mock

    sync_jobs, access, merge, worker = go_retraction_ports

    client, owner = store
    admitted = admit(store)
    job_id, target = admitted['job_id'], admitted['merge_target_id']
    assert jobs.claim(job_id, firestore_client=client)
    jobrow(store, admitted).update(phase='source_cleanup', go_cleanup_epoch=1)
    client.rows[('users', owner, 'conversations', target)] = {'status': 'completed'}
    row(store, 'a')['transcript_corrections_moved_to'] = target
    monkeypatch.setattr(jobs, 'client_for', lambda _client: client)
    monkeypatch.setattr(access, 'should_skip_background_account_mutation', lambda _owner: False)
    monkeypatch.setattr(sync_jobs, 'try_acquire_job_run_lock', lambda _key: 'lock')
    release = Mock()
    retract = Mock()
    monkeypatch.setattr(sync_jobs, 'release_job_run_lock', release)
    monkeypatch.setattr(merge, 'retract_sync_bridge_source', retract)

    assert not worker.retract_go_merge_source(job_id, 1, 2, 0)
    assert not worker.retract_go_merge_source(job_id, 2, 1, 0)
    assert not worker.retract_go_merge_source(job_id, 1, 1, 1)
    retract.assert_not_called()
    assert worker.retract_go_merge_source(job_id, 1, 1, 0)
    assert retract.call_args.args == (owner, 'a')
    assert callable(retract.call_args.kwargs['write_guard'])
    assert retract.call_count == 1
    assert row(store, 'a')['merge_job_id'] == job_id
    assert release.call_count == 4
    assert jobrow(store, admitted)['go_cleanup_receipts'] == {
        'source_0': {'generation': 1, 'epoch': 1, 'source': 'a', 'target': target}
    }
    assert worker.retract_go_merge_source(job_id, 1, 1, 0)
    assert retract.call_args.args == (owner, 'a')
    assert callable(retract.call_args.kwargs['write_guard'])
    assert retract.call_count == 1
    jobrow(store, admitted).update(lease_epoch=2, go_cleanup_epoch=2)
    retract.side_effect = lambda *_args, **_kwargs: row(store, 'a').pop('transcript_corrections_moved_to')
    assert not worker.retract_go_merge_source(job_id, 1, 2, 0)
    assert jobrow(store, admitted)['go_cleanup_receipts']['source_0']['epoch'] == 1
    retract.reset_mock()

    del client.rows[('users', owner, 'conversations', target)]
    assert not worker.retract_go_merge_source(job_id, 1, 2, 0)
    retract.assert_not_called()


def test_rollback_retains_all_sources_until_provisional_target_is_absent(store, monkeypatch):
    client, owner = store
    job = admit(store)
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE)
    recovery = jobs.begin_recovery(job['job_id'], firestore_client=client)
    path = ('users', owner, 'conversations', job['merge_target_id'])
    client.rows[path] = {'status': 'processing'}

    assert not finish_clean_rollback(job['job_id'], recovery['lease_epoch'], firestore_client=client)
    assert all(row(store, cid)['merge_job_id'] == job['job_id'] for cid in ('a', 'b'))
    assert jobrow(store, job)['phase'] == 'recovering'

    del client.rows[path]
    deletion_path = ('account_deletions', owner)
    client.rows[deletion_path] = {'wipe_status': 'pending'}
    assert not finish_clean_rollback(job['job_id'], recovery['lease_epoch'], firestore_client=client)
    assert all(row(store, cid)['status'] == 'merging' for cid in ('a', 'b'))
    client.rows[deletion_path]['wipe_status'] = 'cancelled'
    assert finish_clean_rollback(job['job_id'], recovery['lease_epoch'], firestore_client=client)
    assert all(row(store, cid)['status'] == 'completed' for cid in ('a', 'b'))


def test_rollback_with_absent_target_retries_sibling_cleanup_and_skips_tombstoned_source(
    store, monkeypatch, go_retraction_ports
):
    _, _, merge, worker = go_retraction_ports
    client, owner = store
    job = admit(store)
    target_path = ('users', owner, 'conversations', job['merge_target_id'])
    client.rows[target_path] = {'status': 'processing'}
    attempt = []

    def cleanup(uid, target, *, rollback_step):
        assert (uid, target) == (owner, job['merge_target_id'])
        attempt.append(target_path in client.rows)
        client.rows.pop(target_path, None)
        for step in jobs.ROLLBACK_CLEANUP_STEPS - {'pipeline_ledger'}:
            rollback_step(step)
        if len(attempt) == 1:
            return False
        rollback_step('pipeline_ledger')
        return True

    monkeypatch.setattr(merge, 'cleanup_failed_merge_target', cleanup)
    monkeypatch.setattr(jobs, '_now', lambda: NOW + jobs.LEASE)

    assert worker.reconcile(job['job_id'], firestore_client=client) == 'cleanup_pending'
    assert target_path not in client.rows
    assert all(row(store, cid)['status'] == 'merging' for cid in ('a', 'b'))
    assert not jobs.finish_recovery(
        job['job_id'],
        jobrow(store, job)['lease_epoch'],
        cleanup_steps=jobs.ROLLBACK_CLEANUP_STEPS - {'pipeline_ledger'},
        firestore_client=client,
    )
    client.rows[('users', owner, 'deleted_conversations', 'a')] = {'conversation_id': 'a'}
    monkeypatch.setattr(jobs, '_now', lambda: NOW + 2 * jobs.LEASE)

    assert worker.reconcile(job['job_id'], firestore_client=client) == 'rolled_back'
    assert attempt == [True, False]
    assert row(store, 'a')['status'] == 'merging'
    assert row(store, 'b')['status'] == 'completed'
    assert jobrow(store, job)['rollback_cleanup_steps'] == sorted(jobs.ROLLBACK_CLEANUP_STEPS)


@pytest.mark.parametrize('change', ['tombstone', 'epoch'])
def test_go_retraction_fences_writes_after_initial_validation(store, monkeypatch, go_retraction_ports, change):
    from google.cloud import firestore

    sync_jobs, access, merge, worker = go_retraction_ports
    client, owner = store
    admitted = admit(store)
    job_id, target = admitted['job_id'], admitted['merge_target_id']
    assert jobs.claim(job_id, firestore_client=client)
    jobrow(store, admitted).update(phase='source_cleanup', go_cleanup_epoch=1)
    client.rows[('users', owner, 'conversations', target)] = {'status': 'completed'}
    row(store, 'a')['transcript_corrections_moved_to'] = target
    monkeypatch.setattr(jobs, 'client_for', lambda _: client)
    monkeypatch.setattr(access, 'should_skip_background_account_mutation', lambda _: False)
    monkeypatch.setattr(sync_jobs, 'try_acquire_job_run_lock', lambda _: 'lock')
    monkeypatch.setattr(sync_jobs, 'release_job_run_lock', lambda *_: None)

    def retract(uid, cid, *, write_guard):
        if change == 'tombstone':
            client.rows[('users', owner, 'deleted_conversations', target)] = {'deleted': True}
        else:
            jobrow(store, admitted).update(lease_epoch=2, go_cleanup_epoch=2)

        @firestore.transactional
        def destructive_commit(transaction):
            write_guard(transaction)
            transaction.update(
                client.collection('users').document(uid).collection('conversations').document(cid),
                {'test_retracted': True},
            )

        destructive_commit(client.transaction())

    monkeypatch.setattr(merge, 'retract_sync_bridge_source', retract)
    assert not worker.retract_go_merge_source(job_id, 1, 1, 0)
    assert 'test_retracted' not in row(store, 'a')
    assert 'go_cleanup_receipts' not in jobrow(store, admitted)
