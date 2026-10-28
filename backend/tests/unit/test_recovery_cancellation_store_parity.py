"""Parity tests for recovery cancellation across Store implementations.

Exercises the revocation-only cancellation operation on the shared Store surface
as required by PL-072 and issue #23761:
- SimStore
- PostgresStore
- FirestoreStore
"""

from copy import deepcopy
from dataclasses import asdict
from unittest.mock import MagicMock, Mock

import pytest

from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
from database.batch_pipeline_quarantine_recovery import cancel_fenced_recovery
from database.batch_pipeline_store import FirestoreStore, Store
from database.jobstore.postgres_store import PostgresStore, PostgresTransaction
from testing.pipeline_sim.store import CustomerData, SimStore
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.contracts import Priority, ProjectionBinding
from utils.batch_pipeline.quarantine_recovery import QuarantineRecovery
from utils.batch_pipeline.scheduler import owner_key


def test_sim_store_cancel_fenced_recovery_direct():
    customer = CustomerData()
    store = SimStore(customer, namespace='batch_pipeline_test')
    owner = 'user-123'
    customer.add_user(owner)
    segment_id = 'seg-1'
    binding = ProjectionBinding(owner, 'upload', 'content', (segment_id,))

    store.apply(
        ('jobs', segment_id),
        {
            'owner_id': owner,
            'owner_key': owner_key(owner),
            'state': 'quarantined',
            'recovery_state': 'held',
            'recovery': {'token': 'tok-1', 'started_at': 100},
            'projection_binding': asdict(binding),
        },
    )

    # Before privacy block: cancel_fenced_recovery returns False, state remains held
    assert cancel_fenced_recovery(store, segment_id) is False
    assert store.rows[('jobs', segment_id)]['recovery_state'] == 'held'

    # After privacy block (account deletion)
    customer.delete_account(owner)

    # Must cancel successfully without AttributeError
    assert cancel_fenced_recovery(store, segment_id) is True
    assert store.rows[('jobs', segment_id)]['recovery_state'] == 'cancelled'


def test_sim_store_quarantine_recovery_coordinator_cancelled(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'offline')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_UID_ALLOWLIST', 'user-456')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_EMPTY_ASR_DISPOSITION_ENABLED', 'true')
    monkeypatch.setenv('STT_CAP_DISPATCH_ENFORCEMENT', 'false')

    customer = CustomerData()
    store = SimStore(customer, namespace='batch_pipeline_test')
    owner = 'user-456'
    customer.add_user(owner)
    segment_id = 'seg-coord-1'
    binding = ProjectionBinding(owner, 'upload', 'content', (segment_id,))

    store.apply(
        ('jobs', segment_id),
        {
            'segment_id': segment_id,
            'owner_id': owner,
            'owner_key': owner_key(owner),
            'audio_uri': 'gs://synthetic/audio',
            'capture_at': 100,
            'duration_seconds': 5,
            'priority': Priority.FRESH.value,
            'state': 'quarantined',
            'quarantine_reason': 'worker_failed',
            'recovery_state': 'held',
            'recovery': {'token': 'tok-coord', 'started_at': 100},
            'merge_pending': False,
            'token': '',
            'lease_until': 0,
            'enqueued_at': 100,
            'projection_binding': asdict(binding),
        },
    )

    artifacts = Mock()
    artifacts.fetch_audio.return_value = b'synthetic-audio-bytes'
    artifacts.find_recovery_result.return_value = None
    stt = Mock(return_value={'synthetic': True})
    recovery = QuarantineRecovery(store, artifacts, stt=stt, clock=lambda: 105)

    # Account deleted before recovery
    customer.delete_account(owner)

    # Coordinator recover() must catch BatchPrivacyBlocked, invoke cancel_fenced_recovery,
    # and return 'cancelled' without crashing with AttributeError on SimStore
    outcome = recovery.recover(segment_id, owner)
    assert outcome == 'cancelled'
    assert store.rows[('jobs', segment_id)]['recovery_state'] == 'cancelled'
    stt.assert_not_called()


def test_firestore_store_cancel_fenced_recovery(monkeypatch):
    monkeypatch.setenv('OMI_ENV_STAGE', 'prod')
    owner = 'user-fs-789'
    segment_id = 'seg-fs-1'
    binding = ProjectionBinding(owner, 'upload', 'content', (segment_id,))
    rows = {
        ('users', owner): {'data_protection_level': 'standard'},
        ('batch_pipeline_prod_jobs', segment_id): {
            'owner_id': owner,
            'state': 'quarantined',
            'recovery_state': 'held',
            'recovery': {'token': 'tok-fs', 'started_at': 100},
            'projection_binding': asdict(binding),
        },
    }
    client = StrictFirestore(rows)
    store = FirestoreStore('batch_pipeline_prod', firestore_client=client)

    # Before deletion: returns False
    assert store.cancel_fenced_recovery(segment_id) is False
    assert client.rows[('batch_pipeline_prod_jobs', segment_id)]['recovery_state'] == 'held'

    # Mark account deleted
    client.rows[('account_deletions', owner)] = {'wipe_status': 'pending'}

    # After deletion: cancels and updates state
    assert store.cancel_fenced_recovery(segment_id) is True
    assert client.rows[('batch_pipeline_prod_jobs', segment_id)]['recovery_state'] == 'cancelled'


def test_postgres_store_cancel_fenced_recovery_unit():
    """Unit test PostgresStore.cancel_fenced_recovery transaction semantics."""
    owner = 'user-pg-1'
    segment_id = 'seg-pg-1'
    binding = ProjectionBinding(owner, 'upload', 'content', (segment_id,))
    job_doc = {
        'owner_id': owner,
        'state': 'quarantined',
        'recovery_state': 'held',
        'recovery': {'token': 'tok-pg', 'started_at': 100},
        'projection_binding': asdict(binding),
    }

    written_docs = {}

    store = PostgresStore.__new__(PostgresStore)
    store.namespace = 'batch_pipeline_test_pg'

    # Mock transaction execution
    def fake_run(body):
        tx = MagicMock()
        tx.store = store
        tx.conn = MagicMock()
        tx.check_privacy.side_effect = lambda uid, convs, gen: store.check_privacy_for(uid, convs, gen)

        def fake_get(table, key):
            if table == 'jobs' and key == segment_id:
                return deepcopy(job_doc)
            return {}

        tx.get.side_effect = fake_get
        return body(tx)

    store.run = fake_run

    def fake_write_doc(conn, table, key, doc):
        written_docs[(table, key)] = doc

    store.write_doc = fake_write_doc

    # Case 1: Privacy not blocked -> cancel_fenced_recovery returns False
    store.check_privacy_for = Mock(return_value=1)
    res = store.cancel_fenced_recovery(segment_id)
    assert res is False
    assert written_docs == {}

    # Case 2: Privacy blocked -> cancel_fenced_recovery writes cancelled and returns True
    store.check_privacy_for = Mock(side_effect=BatchPrivacyBlocked('Account marked for deletion'))
    res = store.cancel_fenced_recovery(segment_id)
    assert res is True
    assert written_docs[('jobs', segment_id)]['recovery_state'] == 'cancelled'


def test_store_protocol_conformance():
    """Verify Store protocol and all implementations expose cancel_fenced_recovery."""
    for cls in (Store, FirestoreStore, PostgresStore, SimStore):
        assert hasattr(cls, 'cancel_fenced_recovery')
        assert callable(getattr(cls, 'cancel_fenced_recovery'))
