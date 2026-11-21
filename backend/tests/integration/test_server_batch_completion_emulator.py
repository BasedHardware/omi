"""Local-only Firestore proof for atomic server-batch terminal and transforms.

Run from backend under Firebase emulators:exec with a demo-* project:
python -m pytest tests/integration/test_server_batch_completion_emulator.py -q
No credential, provider or production service is used.
"""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import os
import uuid

import pytest
from google.auth.credentials import AnonymousCredentials
from google.api_core.exceptions import Aborted
from google.cloud import firestore

from database import conversation_finalization_jobs as jobs
from utils.conversations import lifecycle


@pytest.fixture
def seeded(monkeypatch):
    host = os.environ.get('FIRESTORE_EMULATOR_HOST', '')
    if not host:
        pytest.skip('local Firestore emulator required')
    assert host.split(':')[0] in {'127.0.0.1', 'localhost'}, 'refuse non-local Firestore'
    project = os.environ.get('GCLOUD_PROJECT', 'demo-listen')
    assert project.startswith('demo-'), 'refuse non-demo project'
    client = firestore.Client(project=project, credentials=AnonymousCredentials())
    uid, cid, jid = ('atomic-' + uuid.uuid4().hex for _ in range(3))
    row_ref = client.collection('users').document(uid).collection('conversations').document(cid)
    job_ref = client.collection(jobs.FINALIZATION_JOBS_COLLECTION).document(jid)
    shard = jobs._projection_shard(jid)
    projection_ref = client.collection(jobs.FINALIZATION_PROJECTION_COLLECTION).document(
        jobs._projection_shard_id(jobs.FINALIZATION_PROJECTION_GENERATION, shard)
    )
    capture = {
        'id': cid,
        'status': 'processing',
        'record_lane_owner': 'batch_live_v1',
        'external_data': {'server_batch_only': True},
        'private_cloud_sync_enabled': True,
        'data_protection_level': 'standard',
        'finalization_job_id': jid,
        'finalization_revision': 1,
    }
    row_ref.set(capture)
    job_ref.set(
        {
            'uid': uid,
            'conversation_id': cid,
            'status': 'leased',
            'dispatch_generation': 1,
            'lease_epoch': 1,
            'finalization_revision': 1,
            'fanout_status': 'pending',
            'projection_generation': jobs.FINALIZATION_PROJECTION_GENERATION,
            'projection_shard': shard,
        }
    )
    baseline = projection_ref.get().to_dict() or {}
    effects = Mock()
    monkeypatch.setattr(jobs, 'stop_quiet_check_for_conversation', effects)
    monkeypatch.setattr(jobs, 'invalidate_people_stats_cache', effects)
    monkeypatch.setattr(jobs.conversations_db, 'serving_for', lambda *args: True)
    monkeypatch.setattr(jobs.conversations_db, 'sync_conversation_search_index_public', effects)

    def complete():
        return lifecycle.complete_server_batch_capture(uid, cid, capture, jid, 1, 1, firestore_client=client)

    yield client, row_ref, job_ref, projection_ref, baseline, effects, complete
    row_ref.delete()
    job_ref.delete()
    client.close()


def assert_deltas(ref, baseline, **expected):
    current = ref.get().to_dict() or {}
    for key in ('leased', 'completed', 'success', 'stale'):
        assert current.get(key, 0) - baseline.get(key, 0) == expected.get(key, 0)


@pytest.mark.parametrize('fault', ['before_commit', 'lost_commit_response', 'aborted_retry'])
def test_fault_and_replay(seeded, monkeypatch, fault):
    client, row, job, projection, baseline, effects, complete = seeded
    transaction_factory = client.transaction
    injected = False

    def transaction(*args, **kwargs):
        txn = transaction_factory(*args, **kwargs)
        commit = txn._commit

        def fault_once():
            nonlocal injected
            if not injected:
                injected = True
                if fault == 'aborted_retry':
                    # A real server abort releases its read locks. Mirror that
                    # before the SDK restarts the failed transaction.
                    txn._rollback()
                    raise Aborted('emulator injected retry before commit')
                raise RuntimeError('emulator injected commit boundary failure')
            return commit()

        monkeypatch.setattr(txn, '_commit', fault_once)
        return txn

    if fault == 'lost_commit_response':
        # Lose the caller's response after SDK commit/cleanup, before observers.
        # Injecting after Transaction._commit instead would make the SDK try to
        # roll back its already-cleaned transaction, an impossible SDK state.
        transactional = jobs.firestore.transactional

        def lose_response(fn):
            wrapped = transactional(fn)

            def invoke(*args, **kwargs):
                nonlocal injected
                result = wrapped(*args, **kwargs)
                if not injected:
                    injected = True
                    raise RuntimeError('emulator injected commit boundary failure')
                return result

            return invoke

        monkeypatch.setattr(jobs.firestore, 'transactional', lose_response)
    else:
        monkeypatch.setattr(client, 'transaction', transaction)
    if fault == 'aborted_retry':
        assert complete() == 'completed'
    else:
        with pytest.raises(RuntimeError, match='commit boundary failure'):
            complete()
        effects.assert_not_called()
        if fault == 'before_commit':
            assert row.get().to_dict()['status'] == 'processing'
            assert job.get().to_dict()['status'] == 'leased'
            assert_deltas(projection, baseline)
        else:
            assert row.get().to_dict()['status'] == job.get().to_dict()['status'] == 'completed'
    assert injected
    assert complete() == complete() == 'completed'
    assert row.get().to_dict()['relevance_decision']['trigger'] == 'lifecycle_terminal'
    assert job.get().to_dict()['fanout_status'] == 'completed'
    assert_deltas(projection, baseline, leased=-1, completed=1, success=1)


@pytest.mark.parametrize(
    'owner,change',
    [
        ('job', {'lease_epoch': 2}),
        ('job', {'dispatch_generation': 2}),
        ('conversation', {'private_cloud_sync_enabled': False}),
        ('conversation', {'discarded': True}),
        ('conversation', {'finalization_revision': 2}),
        ('conversation', {'finalization_job_id': 'successor'}),
        ('conversation', {'external_data': {'server_batch_only': False}}),
    ],
)
def test_fences_after_registration(seeded, owner, change):
    _, row, job, projection, baseline, effects, complete = seeded
    (job if owner == 'job' else row).update(change)
    expected = 'lease_conflict' if owner == 'job' else 'fenced'
    assert complete() == complete() == expected
    assert row.get().to_dict()['status'] == 'processing'
    effects.assert_not_called()
    if owner == 'job':
        assert job.get().to_dict()['status'] == 'leased'
        assert_deltas(projection, baseline)
    else:
        assert job.get().to_dict()['terminal_outcome'] == 'stale'
        assert_deltas(projection, baseline, leased=-1, completed=1, stale=1)


def test_concurrent_redelivery_commits_one_terminal_projection(seeded):
    _, row, job, projection, baseline, _, complete = seeded
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: complete(), range(2))) == ['completed', 'completed']
    assert row.get().to_dict()['status'] == job.get().to_dict()['status'] == 'completed'
    assert_deltas(projection, baseline, leased=-1, completed=1, success=1)
