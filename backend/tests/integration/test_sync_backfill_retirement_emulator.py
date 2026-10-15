"""Real transaction/delete proof. Requires a loopback-only Firestore emulator."""

import os
from datetime import datetime, timezone
from urllib.parse import urlparse
from uuid import uuid4
from unittest.mock import MagicMock

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
from google.cloud.firestore_v1.document import DocumentReference

from database import sync_backfill_sequencer as registry
from utils.sync import uid_sequencer


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
    assert not client.collection(registry.COLLECTION).document(uid).get().exists
    assert ledger.get().to_dict()['status'] == 'retryable'
    assert registry.claim_next(uid, firestore_client=client)['job_id'] == 'next'


def test_claim_candidate_identity_fence_uses_the_transactional_head(state):
    client, uid, jid, ledger = state
    assert registry.claim_next(uid, expected_job_id='not-inspected', firestore_client=client) is None
    assert not client.collection(registry.COLLECTION).document(uid).get().exists
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
    assert registry.get_owner(uid) == {}
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
    assert registry.get_owner(uid) == {}
    assert uid_sequencer._claim_next(uid)['job_id'] == live
