"""Real Firestore paging and atomic rollback; requires an isolated loopback emulator."""

from datetime import datetime, timezone
import os
from types import SimpleNamespace

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

from database.batch_pipeline_store import FirestoreStore, FirestoreTransaction
from utils.batch_pipeline import record_seal_nojob as backfill

pytestmark = pytest.mark.skipif(
    not os.getenv('FIRESTORE_EMULATOR_HOST', '').startswith(('127.0.0.1:', 'localhost:')),
    reason='isolated loopback Firestore emulator required',
)


@pytest.fixture
def source(monkeypatch):
    client = firestore.Client(project='demo-sealbackfill', credentials=AnonymousCredentials())
    store = FirestoreStore('batch_pipeline_test_sealbackfill', firestore_client=client)
    user = client.collection('users').document('synthetic-backfill-owner')
    user.set({'private_cloud_sync_enabled': True})
    paths = []
    for name in ('first', 'second'):
        ref = user.collection('conversations').document(name)
        ref.set(
            {
                'record_lane_owner': 'batch_live_v1',
                'status': 'completed',
                'private_cloud_sync_enabled': True,
                'finished_at': datetime.fromtimestamp(102, timezone.utc),
            }
        )
        paths.append(ref.path)
    monkeypatch.setattr(backfill, 'retained_tail_proof', lambda *a: 'synthetic-tail-proof')
    return client, store, sorted(paths)


def make_plan(source, paths):
    return backfill.plan_backfill(
        source[1],
        paths,
        object(),
        SimpleNamespace(),
        server_flags={
            'K_SERVICE': 'synthetic-serving-role',
            'BATCH_PIPELINE_PERCENT': '0',
            'BATCH_LIVE_STT_RETIRE_PERCENT': '0',
        },
    )


def test_real_discovery_resumes_and_seal_registration_is_idempotent(source):
    client, store, paths = source
    first, cursor = backfill.discover(client, limit=1)
    second, end = backfill.discover(client, limit=1, after=cursor)
    assert first + second == paths
    empty, wrapped = backfill.discover(client, limit=1, after=end)
    assert empty == [] and wrapped is None
    late = client.document(paths[0].rsplit('/', 1)[0] + '/aaa-late-match')
    late.set(client.document(paths[0]).get().to_dict())
    assert backfill.discover(client, limit=1, after=wrapped)[0] == [late.path]
    assert backfill.summary(make_plan(source, [late.path]))['dispositions'] == {'eligible': 1}
    result = make_plan(source, paths)
    assert backfill.summary(result)['dispositions'] == {'eligible': 2}
    assert backfill.apply_backfill(store, result, result['plan_sha256']) == {'sealed_registered': 2}
    for entry in result['entries']:
        row = client.document(entry['path']).get().to_dict()
        assert row['record_audio_closed'] and row['record_upload_sessions'] == {}
        job = client.collection(f'{store.namespace}_jobs').document(entry['job']['segment_id']).get().to_dict()
        assert job['state'] == 'record_pending'
    assert backfill.apply_backfill(store, result, result['plan_sha256']) == {'already_registered': 2}


def test_real_transaction_rolls_back_job_if_seal_write_never_reached(source, monkeypatch):
    client, store, paths = source
    interrupted_path = paths[0] + '-interrupted'
    client.document(interrupted_path).set(client.document(paths[0]).get().to_dict())
    result = make_plan(source, [interrupted_path])
    original = FirestoreTransaction.flush

    def interrupted(view):
        original(view)  # Stages the job write in the real SDK transaction.
        raise RuntimeError('synthetic interruption before seal write')

    monkeypatch.setattr(FirestoreTransaction, 'flush', interrupted)
    assert backfill.apply_backfill(store, result, result['plan_sha256']) == {'write_error': 1}
    job_id = result['entries'][0]['job']['segment_id']
    assert not client.collection(f'{store.namespace}_jobs').document(job_id).get().exists
    assert not client.document(interrupted_path).get().to_dict().get('record_audio_closed')
