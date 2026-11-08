"""A crash after discarded fanout close must permit the same lease's replay."""

from database import conversation_finalization_jobs as jobs
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.conversations import lifecycle


def test_discarded_server_batch_fanout_close_replays_before_terminal_commit(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(jobs, 'get_firestore_client', lambda: client)
    job_path = (jobs.FINALIZATION_JOBS_COLLECTION, 'job')
    client.rows[('users', 'synthetic', 'conversations', 'capture')] = {
        'status': 'completed',
        'discarded': True,
        'server_batch_only': True,
        'record_lane_owner': 'batch_live_v1',
        'finalization_job_id': 'job',
        'finalization_revision': 1,
    }
    client.rows[job_path] = {
        'uid': 'synthetic',
        'conversation_id': 'capture',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 7,
        'finalization_revision': 1,
        'fanout_status': 'pending',
    }
    # Discarded jobs close directly, without a fanout claim stamping its epoch.
    assert lifecycle.complete_finalization_fanout('job', 1, 7) is True
    assert client.rows[job_path]['fanout_lease_epoch'] == 7
    assert client.rows[job_path]['status'] == 'leased'

    # Crash before mark_finalization_completed: redeliver the same durable lease.
    assert lifecycle.complete_finalization_fanout('job', 1, 7) is True
    assert lifecycle.complete_finalization_fanout('job', 1, 8) is False
    assert jobs.mark_finalization_completed('job', 1, 7) is True
    assert client.rows[job_path]['terminal_outcome'] == 'success'
    assert client.rows[job_path]['status'] == 'completed'


def _discarded_parent_with_leased_job(client, *, parent_job_id='job', parent_revision=1):
    conversation_path = ('users', 'synthetic', 'conversations', 'capture')
    client.rows[conversation_path] = {
        'status': 'processing',
        'discarded': True,
        'server_batch_only': True,
        'record_lane_owner': 'batch_live_v1',
        'finalization_job_id': parent_job_id,
        'finalization_revision': parent_revision,
    }
    client.rows[(jobs.FINALIZATION_JOBS_COLLECTION, 'job')] = {
        'uid': 'synthetic',
        'conversation_id': 'capture',
        'status': 'leased',
        'dispatch_generation': 1,
        'lease_epoch': 7,
        'finalization_revision': 1,
        'fanout_status': 'pending',
    }
    return conversation_path


def test_discarded_zero_preview_fanout_advances_processing_parent_and_replays(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(jobs, 'get_firestore_client', lambda: client)
    conversation_path = _discarded_parent_with_leased_job(client)
    job_path = (jobs.FINALIZATION_JOBS_COLLECTION, 'job')

    assert lifecycle.complete_discarded_server_batch_fanout('synthetic', 'capture', 'job', 1, 7) is True
    assert client.rows[conversation_path]['status'] == 'completed'
    assert client.rows[job_path]['fanout_status'] == 'completed'
    assert client.rows[job_path]['fanout_lease_epoch'] == 7

    # Redelivery of the same lease replays; a stale lease does not.
    assert lifecycle.complete_discarded_server_batch_fanout('synthetic', 'capture', 'job', 1, 7) is True
    assert lifecycle.complete_discarded_server_batch_fanout('synthetic', 'capture', 'job', 1, 8) is False
    assert jobs.mark_finalization_completed('job', 1, 7) is True
    assert client.rows[job_path]['status'] == 'completed'


def test_discarded_fanout_leaves_parent_owned_by_a_newer_finalization(monkeypatch):
    client = StrictFirestore()
    monkeypatch.setattr(jobs, 'get_firestore_client', lambda: client)
    conversation_path = _discarded_parent_with_leased_job(client, parent_job_id='newer-job', parent_revision=2)
    job_path = (jobs.FINALIZATION_JOBS_COLLECTION, 'job')

    assert lifecycle.complete_discarded_server_batch_fanout('synthetic', 'capture', 'job', 1, 7) is True
    assert client.rows[conversation_path]['status'] == 'processing'
    assert client.rows[job_path]['fanout_status'] == 'completed'
