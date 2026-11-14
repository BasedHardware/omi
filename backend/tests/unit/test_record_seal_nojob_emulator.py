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
    monkeypatch.setattr(backfill, 'retained_tail_proof', lambda *a, **kw: 'synthetic-tail-proof')
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


def _delete_owned_jobs(refs, owner_id):
    for ref in refs:
        if (ref.get().to_dict() or {}).get('owner_id') == owner_id:
            ref.delete()


def test_cleanup_only_deletes_owned_job_references():
    client = firestore.Client(project='demo-seal-age-cleanup', credentials=AnonymousCredentials())
    jobs = client.collection('batch_pipeline_prod_jobs')
    own = jobs.document('synthetic-cleanup-owned')
    other_owner = jobs.document('synthetic-cleanup-other-owner')
    unlisted = jobs.document('synthetic-cleanup-unlisted')
    try:
        own.set({'owner_id': 'synthetic-cleanup-owner'})
        other_owner.set({'owner_id': 'synthetic-other-owner'})
        unlisted.set({'owner_id': 'synthetic-cleanup-owner'})
        _delete_owned_jobs([own, other_owner], 'synthetic-cleanup-owner')
        assert not own.get().exists
        assert other_owner.get().exists
        assert unlisted.get().exists
    finally:
        _delete_owned_jobs([own, unlisted], 'synthetic-cleanup-owner')
        _delete_owned_jobs([other_owner], 'synthetic-other-owner')
        client.close()


def test_real_jobs_age_order_numeric_coverage_frozen_horizon_and_cursor(monkeypatch):
    """Emulator proves query/cursor semantics; registry guards prove index coverage."""
    from config import record_seal_repair as config
    from config.record_audio import record_identity
    from utils.batch_pipeline import record_seal_cluster_repair as cluster
    from utils.batch_pipeline.record_seal_budget import SweepBudget
    from utils.batch_pipeline.record_seal_repair_cursor import RepairCursor

    monkeypatch.delenv('RECORD_SEAL_REPAIR_AGE_ORDER', raising=False)
    client = firestore.Client(project='demo-seal-age-order', credentials=AnonymousCredentials())
    jobs = client.collection('batch_pipeline_prod_jobs')
    owner_id = 'synthetic-age-owner'
    selected = {}
    clocks = [200.123456789, 100.123456789, 100.123456789, None, 'old', True, float('nan'), -float('inf'), 'missing']
    refs = [jobs.document(record_identity(owner_id, f'synthetic-{index}')[1]) for index in range(len(clocks))]
    late = jobs.document(record_identity(owner_id, 'late')[1])
    try:
        _delete_owned_jobs([*refs, late], owner_id)
        for index, clock in enumerate(clocks):
            cid = f'synthetic-{index}'
            content, _ = record_identity(owner_id, cid)
            data = {
                'state': 'record_pending',
                'owner_id': owner_id,
                'conversation_id': cid,
                'record_content_id': content,
            }
            if clock != 'missing':
                data['enqueued_at'] = clock
            ref = refs[index]
            ref.set(data)
        frontier = RepairCursor(client, b'synthetic-local-key' * 2, jobs=True)
        expected = [
            f'users/synthetic-age-owner/conversations/synthetic-{i}'
            for i in sorted(range(3), key=lambda i: (clocks[i], refs[i].id), reverse=True)
        ]
        observed, cursor, ages = [], None, []
        # Scan only one document at a time, including ineligible NaN/-inf.
        for _ in range(len(clocks) + 2):
            rows, saturated, cursor = cluster.discover_jobs(
                client, budget=SweepBudget(60), after=cursor, max_scan=1, selected_cursors=selected
            )
            observed += [path for path, _ in rows]
            ages += [age for _, age in rows]
            frontier.write(cursor, SweepBudget(60))
            cursor = frontier.read(SweepBudget(60))
            if cursor is None:
                break
        assert observed == expected and cursor is None
        assert all(age >= config.JOBS_MIN_AGE_SECONDS for age in ages)
        first, _, cursor = cluster.discover_jobs(client, budget=SweepBudget(60), max_rows=1)
        content, _ = record_identity(owner_id, 'late')
        late.set(
            {
                'state': 'record_pending',
                'owner_id': owner_id,
                'conversation_id': 'late',
                'record_content_id': content,
                'enqueued_at': cursor['horizon'].timestamp() + 1,
            }
        )
        rest, _, end = cluster.discover_jobs(client, budget=SweepBudget(60), after=cursor)
        assert [path for path, _ in first + rest] == expected and end is None
        # A new sweep recomputes ages against wall time; only row selection is stable.
        repeated, _, _ = cluster.discover_jobs(client, budget=SweepBudget(60), max_rows=1)
        assert [path for path, _ in repeated] == [path for path, _ in first]
        # The legacy cursor can still be written and read, and off returns all
        # the same eligible rows in exact Firestore document-name order.
        monkeypatch.setenv('RECORD_SEAL_REPAIR_AGE_ORDER', 'off')
        old, _, old_cursor = cluster.discover_jobs(client, budget=SweepBudget(60), max_rows=1)
        frontier.write(old_cursor, SweepBudget(60))
        assert frontier.read(SweepBudget(60)) == old_cursor
        rest, _, _ = cluster.discover_jobs(client, budget=SweepBudget(60), after=old_cursor)
        expected_hash = [
            f'users/synthetic-age-owner/conversations/synthetic-{i}' for i in sorted(range(3), key=lambda i: refs[i].id)
        ]
        assert [path for path, _ in old + rest] == expected_hash
    finally:
        _delete_owned_jobs([*refs, late], owner_id)
        client.close()
