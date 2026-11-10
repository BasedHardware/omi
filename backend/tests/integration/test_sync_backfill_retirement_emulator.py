"""Real transaction/delete proof. Requires a loopback-only Firestore emulator."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference

from database import sync_backfill_sequencer as registry
from utils.sync import uid_sequencer
from scripts import repair_sync_backfill_owners as repair_script


@pytest.fixture
def state(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if urlparse(f'//{host}').hostname not in {'127.0.0.1', 'localhost', '::1'}:
        pytest.fail('A loopback Firestore emulator is required')
    client = firestore.Client(project='demo-sync-retirement', credentials=AnonymousCredentials())
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    uid, jid = uuid4().hex, uuid4().hex
    now = datetime.now(timezone.utc)
    registry.register_job(
        uid, jid, {'uid': uid, 'job_id': jid, 'content_id': 'content'}, None, firestore_client=client, now=now
    )
    ledger = client.collection('users').document(uid).collection('sync_content_ledger').document('content')
    ledger.set({'status': 'processing', 'job_id': jid, 'partial_result': {'checkpoint': 'keep'}})
    yield client, uid, jid, ledger
    client.close()


def test_retirement_atomically_releases_claim_and_deletes_pending(state):
    client, uid, jid, ledger = state
    assert registry.retire_expired(uid, jid, firestore_client=client)
    assert not client.collection(registry.PENDING_COLLECTION).document(jid).get().exists
    assert ledger.get().to_dict() == {
        'status': 'retryable',
        'partial_result': {'checkpoint': 'keep'},
        'updated_at': ledger.get().to_dict()['updated_at'],
    }
    assert not registry.retire_expired(uid, jid, firestore_client=client)


@pytest.mark.parametrize('binding', [{'ledger_run_token': 'live'}, {'ledger_run_epoch': 4}, {'status': 'completed'}])
def test_bound_or_completed_claim_prevents_retirement(state, binding):
    client, uid, jid, ledger = state
    ledger.update(binding)
    before = ledger.get().to_dict()
    assert not registry.retire_expired(uid, jid, firestore_client=client)
    assert client.collection(registry.PENDING_COLLECTION).document(jid).get().exists
    assert ledger.get().to_dict() == before


def test_newer_claim_is_preserved(state):
    client, uid, jid, ledger = state
    ledger.update({'job_id': 'new-owner', 'ledger_run_epoch': 3})
    before = ledger.get().to_dict()
    assert registry.retire_expired(uid, jid, firestore_client=client)
    assert ledger.get().to_dict() == before


def test_worker_beginning_before_retirement_transaction_wins(state, monkeypatch):
    client, uid, jid, ledger = state
    claim = registry.claim_next(uid, firestore_client=client)
    owner_ref = client.collection(registry.COLLECTION).document(uid)
    original = DocumentReference.get
    fired = []

    def get(ref, *args, **kwargs):
        if ref.path == owner_ref.path and kwargs.get('transaction') is not None and not fired:
            fired.append(True)
            assert registry.begin_job(uid, jid, claim['epoch'], firestore_client=client)
        return original(ref, *args, **kwargs)

    monkeypatch.setattr(DocumentReference, 'get', get)
    assert not registry.retire_expired(uid, jid, epoch=claim['epoch'], firestore_client=client)
    assert owner_ref.get().to_dict()['active_state'] == 'running'
    assert ledger.get().to_dict()['status'] == 'processing'


def test_dispatching_owner_retired_and_next_claimed(state):
    client, uid, jid, ledger = state
    claim = registry.claim_next(uid, firestore_client=client)
    registry.register_job(uid, 'next', {'uid': uid, 'job_id': 'next'}, None, firestore_client=client)
    assert registry.retire_expired(uid, jid, epoch=claim['epoch'], firestore_client=client)
    assert client.collection(registry.COLLECTION).document(uid).get().exists
    assert not registry.get_owner(uid, firestore_client=client).get('active_job_id')
    assert ledger.get().to_dict()['status'] == 'retryable'
    assert registry.claim_next(uid, firestore_client=client)['job_id'] == 'next'


def test_claim_candidate_identity_fence_uses_the_transactional_head(state):
    client, uid, jid, ledger = state
    assert registry.claim_next(uid, expected_job_id='not-inspected', firestore_client=client) is None
    assert client.collection(registry.COLLECTION).document(uid).get().exists
    assert not registry.get_owner(uid, firestore_client=client).get('active_job_id')
    assert client.collection(registry.PENDING_COLLECTION).document(jid).get().exists
    assert registry.claim_next(uid, expected_job_id=jid, firestore_client=client)['job_id'] == jid


@pytest.mark.parametrize('binding', [{'ledger_run_token': 'live'}, {'status': 'completed'}])
def test_claim_path_preserves_refused_head_and_ledger(state, monkeypatch, binding):
    client, uid, jid, ledger = state
    monkeypatch.setattr(registry, 'get_firestore_client', lambda: client)
    monkeypatch.setenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'true')
    monkeypatch.setattr(uid_sequencer, 'sync_job_key_exists', lambda job: False)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda job: 'token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda *args: None)
    ledger.update(binding)
    before = ledger.get().to_dict()
    assert uid_sequencer._claim_next(uid) is None
    assert not registry.get_owner(uid).get('active_job_id')
    assert client.collection(registry.PENDING_COLLECTION).document(jid).get().exists
    assert ledger.get().to_dict() == before


def test_bounded_claim_schedules_wake_for_live_successor(state, monkeypatch):
    client, uid, jid, ledger = state
    live = uuid4().hex
    registry.register_job(uid, live, {'uid': uid, 'job_id': live}, None, firestore_client=client)
    monkeypatch.setattr(registry, 'get_firestore_client', lambda: client)
    monkeypatch.setenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'true')
    monkeypatch.setattr(uid_sequencer, 'sync_job_key_exists', lambda job: job == live)
    monkeypatch.setattr(uid_sequencer, 'try_acquire_job_run_lock', lambda job: 'token')
    monkeypatch.setattr(uid_sequencer, 'release_job_run_lock', lambda *args: None)
    monkeypatch.setattr(uid_sequencer.backfill_cutover, 'quiet_remaining', lambda uid: (0, None))
    monkeypatch.setattr(uid_sequencer.backfill_cutover, 'direct_remaining_for_uid', lambda uid: (0, None))
    monkeypatch.setattr(uid_sequencer.backfill_cutover, 'claim_wake', lambda *args: True)
    wake = MagicMock()
    monkeypatch.setattr(uid_sequencer, '_enqueue_wake', wake)
    assert not uid_sequencer.kick(uid, retire_limit=1)
    wake.assert_called_once()
    assert registry.pending_head(uid)['job_id'] == live
    assert not registry.get_owner(uid).get('active_job_id')
    assert uid_sequencer._claim_next(uid)['job_id'] == live


def test_duplicate_admission_transactionally_repairs_missing_owner(state):
    client, uid, jid, ledger = state
    owner = client.collection(registry.COLLECTION).document(uid)
    owner.delete()  # Reproduce a legacy orphan, only inside the emulator.
    assert not registry.register_job(uid, jid, {'ignored': True}, None, firestore_client=client)
    assert owner.get().exists
    assert registry.get_owner(uid, firestore_client=client)['reconcile_at'] is not None


def test_repair_dry_run_and_stale_scan_are_read_only(state):
    client, uid, jid, ledger = state
    owner = client.collection(registry.COLLECTION).document(uid)
    owner.delete()
    assert registry.repair_owner(uid, dry_run=True, firestore_client=client)
    assert not owner.get().exists
    client.collection(registry.PENDING_COLLECTION).document(jid).delete()
    assert not registry.repair_owner(uid, firestore_client=client)
    assert not owner.get().exists


@pytest.mark.parametrize('release', ['finish', 'retire'])
def test_concurrent_admission_and_owner_release_cannot_strand_queue(state, release):
    # Both transaction orders must preserve ownership. Use the real Firestore
    # transaction runner: a serialized fake cannot prove contention behavior.
    client, uid, jid, ledger = state
    claim = registry.claim_next(uid, firestore_client=client)
    barrier = Barrier(2)
    next_job = uuid4().hex

    def admit():
        barrier.wait(timeout=10)
        return registry.register_job(uid, next_job, {'uid': uid, 'job_id': next_job}, None, firestore_client=client)

    def finish():
        barrier.wait(timeout=10)
        if release == 'finish':
            return registry.finish_job(uid, jid, claim['epoch'], 'completed', firestore_client=client)
        return registry.retire_expired(uid, jid, epoch=claim['epoch'], firestore_client=client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        admission = pool.submit(admit)
        completion = pool.submit(finish)
        assert admission.result(timeout=30)
        assert completion.result(timeout=30)
    owner = registry.get_owner(uid, firestore_client=client)
    assert owner and not owner.get('active_job_id')
    assert registry.has_pending(uid, firestore_client=client)
    assert registry.claim_next(uid, firestore_client=client)['job_id'] == next_job


def test_operator_repair_real_pagination_is_read_only_then_idempotent(state, monkeypatch):
    client, uid, jid, ledger = state
    owner = client.collection(registry.COLLECTION).document(uid)
    owner.delete()
    monkeypatch.setattr(repair_script.time, 'sleep', lambda seconds: None)
    dry = repair_script.repair(client, page_size=1)
    assert dry['missing_owners'] >= 1 and dry['repaired_owners'] == 0
    assert not owner.get().exists
    applied = repair_script.repair(client, apply=True, page_size=1)
    assert applied['repaired_owners'] >= 1 and applied['errors'] == 0
    assert owner.get().exists
    assert repair_script.repair(client, apply=True, page_size=1)['repaired_owners'] == 0


@pytest.mark.parametrize('state_name', ['dispatching', 'running'])
def test_301_parked_empty_owners_do_not_hide_stuck_lease_on_real_query(state, monkeypatch, state_name):
    client, uid, jid, ledger = state
    old = datetime.now(timezone.utc) - timedelta(hours=2)
    batch = client.batch()
    prefix = uuid4().hex
    for index in range(301):
        batch.set(client.collection(registry.COLLECTION).document(f'{prefix}-{index}'), {'epoch': 7, 'updated_at': old})
    batch.commit()
    claim = registry.claim_next(uid, firestore_client=client, now=old)
    if state_name == 'running':
        assert registry.begin_job(uid, jid, claim['epoch'], firestore_client=client, now=old)
    monkeypatch.setattr(registry, 'get_firestore_client', lambda: client)
    monkeypatch.setenv('SYNC_BACKFILL_RETIRE_EXPIRED_AT_CLAIM', 'false')
    monkeypatch.setattr(uid_sequencer, 'sync_job_run_lock_present', lambda job: False)
    monkeypatch.setattr(uid_sequencer, 'get_sync_job', lambda job: {'status': 'queued'})
    monkeypatch.setattr(uid_sequencer.backfill_cutover, 'quiet_remaining', lambda uid: (0, ''))
    monkeypatch.setattr(uid_sequencer.backfill_cutover, 'direct_remaining_for_uid', lambda uid: (0, ''))
    dispatched = []
    monkeypatch.setattr(uid_sequencer, '_dispatch', lambda job: dispatched.append(job))
    page = registry.due_owners(limit=100, firestore_client=client)
    assert any(row['uid'] == uid for row in page)
    assert all(not row['uid'].startswith(prefix) for row in page)
    assert all(row.get('active_job_id') or registry.has_pending(row['uid'], firestore_client=client) for row in page)
    uid_sequencer.sweep(limit=100)
    # A dispatching retry preserves the epoch/task identity; only an expired
    # running lease fences the previous executor with a higher epoch.
    assert any(
        job['job_id'] == jid
        and (job['epoch'] == claim['epoch'] if state_name == 'dispatching' else job['epoch'] > claim['epoch'])
        for job in dispatched
    )


def test_parking_and_admission_contend_without_losing_wakeup_or_epoch(state):
    client, uid, jid, ledger = state
    claim = registry.claim_next(uid, firestore_client=client)
    assert registry.finish_job(uid, jid, claim['epoch'], 'completed', firestore_client=client)
    assert 'reconcile_at' not in registry.get_owner(uid, firestore_client=client)
    next_job = uuid4().hex
    barrier = Barrier(2)

    def admit():
        barrier.wait(timeout=10)
        registry.register_job(uid, next_job, {'uid': uid, 'job_id': next_job}, None, firestore_client=client)

    def park():
        barrier.wait(timeout=10)
        registry.defer_owner(uid, 120, firestore_client=client)

    with ThreadPoolExecutor(max_workers=2) as pool:
        admission, parking = pool.submit(admit), pool.submit(park)
        admission.result(timeout=30)
        parking.result(timeout=30)
    owner = registry.get_owner(uid, firestore_client=client)
    assert owner['reconcile_at'] is not None and owner['epoch'] == claim['epoch']
    assert registry.claim_next(uid, firestore_client=client)['epoch'] > claim['epoch']


def test_repair_deadline_is_respected_by_real_claim_and_stale_deferral(state, monkeypatch):
    client, uid, jid, ledger = state
    client.collection(registry.COLLECTION).document(uid).delete()
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(registry.secrets, 'randbelow', lambda window: window - 1)
    assert registry.repair_owner(uid, repair_window=600, now=now, firestore_client=client)
    owner = registry.get_owner(uid, firestore_client=client)
    assert owner['reconcile_at'] == now + timedelta(seconds=600)
    assert not any(row['uid'] == uid for row in registry.due_owners(now=now, firestore_client=client))
    registry.defer_owner(uid, 120, now=now, firestore_client=client)
    assert registry.get_owner(uid, firestore_client=client)['reconcile_at'] == owner['reconcile_at']
    assert registry.claim_next(uid, now=now, firestore_client=client) is None
    assert registry.claim_next(uid, now=owner['reconcile_at'], firestore_client=client)['job_id'] == jid


def test_dark_guard_atomic_custody_retains_exact_request_and_partial_ledger(state, monkeypatch):
    from database import sync_redrive

    client, uid, jid, ledger = state
    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
    original = client.collection(registry.PENDING_COLLECTION).document(jid).get().to_dict()['payload']
    assert registry.retire_expired(uid, jid, firestore_client=client)
    assert not client.collection(registry.PENDING_COLLECTION).document(jid).get().exists
    custody = client.collection(sync_redrive.COLLECTION).document(jid).get().to_dict()
    assert custody['status'] == 'redrive_required'
    assert custody['payload'] == original
    assert ledger.get().to_dict()['partial_result'] == {'checkpoint': 'keep'}
    assert ledger.get().to_dict()['status'] == 'retryable'
    assert not registry.claim_next(uid, firestore_client=client)


def test_dark_guard_completion_race_never_reopens_completed_ledger(state, monkeypatch):
    from database import sync_redrive

    client, uid, jid, ledger = state
    monkeypatch.setenv('SYNC_DURABLE_REDRIVE_GUARD', 'true')
    result = {'total_segments': 0, 'failed_segments': 0, 'errors': [], 'outcome': 'expected_silence'}
    ledger.set({'status': 'completed', 'job_id': jid, 'result': result})
    assert registry.retire_expired(uid, jid, firestore_client=client)
    assert ledger.get().to_dict()['status'] == 'completed'
    assert not client.collection(sync_redrive.COLLECTION).document(jid).get().exists
