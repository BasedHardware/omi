from dataclasses import asdict
from unittest.mock import MagicMock, Mock

from database.batch_pipeline_privacy import BatchPrivacyBlocked
from database.batch_pipeline_projection_protocol import ProjectionBinding
from database.batch_pipeline_quarantine_recovery import cancel_fenced_recovery
from database.batch_pipeline_store import FirestoreStore
from database.jobstore.postgres_store import PostgresStore
from testing.pipeline_sim.store import CustomerData, SimStore
from utils.batch_pipeline.contracts import Priority, WorkItem


def test_sim_store_cancel_fenced_recovery_when_deleted():
    customer = CustomerData()
    store = SimStore(customer, namespace='batch_pipeline_test_sim')
    owner_id = 'test-owner-001'
    customer.add_user(owner_id)

    binding = ProjectionBinding(owner_id, 'bp_upload', 'content', ('seg-1',))
    item = WorkItem('seg-1', owner_id, 1000.0, 'gs://synthetic/audio', 4, Priority.FRESH, privacy_generation=0)

    job_data = {
        **asdict(item),
        'projection_binding': asdict(binding),
        'owner_key': f'owner:{owner_id}',
        'protocol_version': 1,
        'state': 'quarantined',
        'quarantine_reason': 'worker_failed',
        'recovery_state': 'prepared',
        'recovery': {'token': 'token-test-123'},
    }
    store.rows[('jobs', 'seg-1')] = job_data

    # 1. Allowed state -> cancel_fenced_recovery returns False, state remains prepared
    assert cancel_fenced_recovery(store, 'seg-1') is False
    assert store.rows[('jobs', 'seg-1')]['recovery_state'] == 'prepared'

    # 2. Delete account -> cancel_fenced_recovery returns True, recovery_state becomes cancelled
    customer.delete_account(owner_id)
    assert cancel_fenced_recovery(store, 'seg-1') is True
    cancelled_job = store.rows[('jobs', 'seg-1')]
    assert cancelled_job['recovery_state'] == 'cancelled'
    assert cancelled_job['recovery']['token'] == 'token-test-123'


def test_postgres_store_cancel_fenced_recovery():
    pool_mock = MagicMock()
    store = PostgresStore('batch_pipeline_test_pg', pool=pool_mock, customer_client=Mock())

    conn_mock = MagicMock()
    pool_mock.connection.return_value.__enter__.return_value = conn_mock
    conn_mock.transaction.return_value.__enter__.return_value = conn_mock

    owner_id = 'pg-owner-001'
    binding = ProjectionBinding(owner_id, 'bp_upload', 'content', ('seg-pg',))
    job = {
        'segment_id': 'seg-pg',
        'owner_id': owner_id,
        'state': 'quarantined',
        'recovery_state': 'prepared',
        'recovery': {'token': 'token-pg-456'},
        'projection_binding': asdict(binding),
    }

    store.read_doc = Mock(return_value=job)
    store.write_doc = Mock()

    # check_privacy_for raises BatchPrivacyBlocked
    store.check_privacy_for = Mock(side_effect=BatchPrivacyBlocked('Account deleted'))

    result = cancel_fenced_recovery(store, 'seg-pg')

    assert result is True
    store.write_doc.assert_called_once()
    args, _ = store.write_doc.call_args
    assert args[1] == 'jobs'
    assert args[2] == 'seg-pg'
    assert args[3]['recovery_state'] == 'cancelled'
    assert args[3]['recovery']['token'] == 'token-pg-456'


def test_firestore_store_cancel_fenced_recovery(monkeypatch):
    emulator_host = '127.0.0.1:8080'
    monkeypatch.setenv('FIRESTORE_EMULATOR_HOST', emulator_host)
    client_mock = MagicMock()
    client_mock._emulator_host = emulator_host
    store = FirestoreStore('batch_pipeline_test_fs', firestore_client=client_mock)

    owner_id = 'fs-owner-001'
    binding = ProjectionBinding(owner_id, 'bp_upload', 'content', ('seg-fs',))
    job = {
        'segment_id': 'seg-fs',
        'owner_id': owner_id,
        'state': 'quarantined',
        'recovery_state': 'prepared',
        'recovery': {'token': 'token-fs-789'},
        'projection_binding': asdict(binding),
    }

    doc_mock = MagicMock()
    doc_mock.get.return_value.to_dict.return_value = job
    client_mock.collection.return_value.document.return_value = doc_mock

    def fake_transactional(fn):
        def wrapper(tx):
            return fn(tx)

        return wrapper

    import google.cloud.firestore

    orig_tx = getattr(google.cloud.firestore, 'transactional', None)
    google.cloud.firestore.transactional = fake_transactional

    import database.batch_pipeline_privacy

    orig_assert = database.batch_pipeline_privacy.assert_batch_write_allowed
    database.batch_pipeline_privacy.assert_batch_write_allowed = Mock(
        side_effect=BatchPrivacyBlocked('Account deleted')
    )

    try:
        result = cancel_fenced_recovery(store, 'seg-fs')
        assert result is True
        tx_mock_used = client_mock.transaction.return_value
        tx_mock_used.update.assert_called_once_with(doc_mock, {'recovery_state': 'cancelled'})
    finally:
        database.batch_pipeline_privacy.assert_batch_write_allowed = orig_assert
        if orig_tx is not None:
            google.cloud.firestore.transactional = orig_tx
