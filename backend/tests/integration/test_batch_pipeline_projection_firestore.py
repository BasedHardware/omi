"""Real assignment/ledger/outbox crash boundaries; loopback emulator only."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4
import os
import threading

from google.auth.credentials import AnonymousCredentials
from google.cloud import firestore
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def lane(monkeypatch):
    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback emulator required; no cloud fallback')
    from database import _client, conversations, llm_usage
    from database.batch_pipeline_intake import admit
    from database.batch_pipeline_store import FirestoreStore
    from database.sync_ledger import sync_content_ledger_ref
    from utils.batch_pipeline.contracts import WorkItem, WorkResult, Priority, ProjectionBinding
    from utils.batch_pipeline.scheduler import Scheduler
    from utils.batch_pipeline.merge import OrderedMerge
    from utils.batch_pipeline.projection import Projector
    from utils.sync import reprocess
    from utils.sync.capture import chunk_identity

    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PERCENT', '100')
    monkeypatch.setenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', 'true')
    client = firestore.Client(project=f'demo-pr1-c-{uuid4().hex[:12]}', credentials=AnonymousCredentials())
    store = FirestoreStore(f'batch_pipeline_test_{uuid4().hex}', firestore_client=client)
    uid = f'synthetic-projection-{uuid4().hex}'
    user = client.collection('users').document(uid)
    user.set({'data_protection_level': 'standard'})
    monkeypatch.setattr(_client, '_firestore_client', client)
    monkeypatch.setattr(llm_usage, 'resolve_usage_plan_id', lambda *args, **kwargs: 'pro')
    import fakeredis
    from utils import fair_use

    monkeypatch.setattr(fair_use, 'redis_client', fakeredis.FakeRedis())
    monkeypatch.setattr(fair_use, 'FAIR_USE_ENABLED', True)
    monkeypatch.setattr(conversations, 'invalidate_people_stats_cache', lambda *_: None)
    monkeypatch.setattr(conversations, '_sync_conversation_search_index', lambda *_: None)
    monkeypatch.setattr(conversations, '_delete_conversation_search_index', lambda *_: None)
    # Keep the bridge's actual redirect/retraction decisions; only its legacy
    # global read boundary is injected with this isolated emulator client.
    monkeypatch.setattr(
        conversations,
        'get_conversation',
        lambda owner, cid: user.collection('conversations').document(cid).get().to_dict(),
    )
    tasks, published, loads = [], [], []
    monkeypatch.setattr(reprocess, '_enqueue', lambda row: tasks.append(row))
    clock = lambda: 10000.0
    payload = {
        'words': [
            {'word': 'We', 'timestamp': [0.0, 1.0]},
            {'word': 'discussed', 'timestamp': [1.0, 2.0]},
            {'word': 'the', 'timestamp': [2.0, 3.0]},
            {'word': 'project.', 'timestamp': [3.0, 4.0]},
        ],
        'diarization': {'turns': [{'start': 0.0, 'end': 10.0, 'speaker': 'SPEAKER_00'}]},
        'audio_seconds': 30,
        'speech_seconds': 4.0,
        'words_provider': 'parakeet',
    }

    def load(item, uri):
        loads.append(item.segment_id)
        return payload

    projector = Projector(store, load, publish=lambda b, r: published.append(r), clock=clock)
    queue, merge = Scheduler(store), OrderedMerge(store)

    def seed(names=('a',), *, device=None, protection='standard', capture_at=1000.0):
        ids = tuple(f'{name}-{uuid4().hex[:8]}' for name in names)
        binding = ProjectionBinding(
            uid,
            f'job-{uuid4().hex}',
            f'content-{uuid4().hex}',
            ids,
            client_device_id=device,
            data_protection_level=protection,
        )
        items = [
            WorkItem(
                sid,
                uid,
                capture_at + i * 30,
                f'gs://synthetic/{sid}#1',
                30,
                Priority.DEEP,
                conversation_id=chunk_identity(uid, 'omi', device, False, capture_at + i * 30),
                privacy_generation=0,
            )
            for i, sid in enumerate(ids)
        ]
        assert admit(store, items, binding, 0, namespace=store.namespace)['outcome'] == 'batch'
        ledger = sync_content_ledger_ref(client, uid, binding.content_id)
        leases = {lease.item.segment_id: lease for lease in queue.pull(0, len(items))}
        assert len(leases) == len(items)
        return SimpleNamespace(binding=binding, ids=ids, items=items, ledger=ledger, leases=leases)

    def finish(batch, index=0, outcome='success'):
        sid = batch.ids[index]
        assert queue.complete(WorkResult(sid, f'gs://synthetic/results/{sid}#1', outcome), batch.leases[sid].token, 1)
        return merge.commit_next(uid, 2)

    value = SimpleNamespace(**locals())
    yield value
    client.close()


def active_rows(lane):
    result = []
    for snapshot in lane.user.collection('conversations').stream():
        row = snapshot.to_dict()
        if not row.get('deleted'):
            row['transcript_segments'] = lane.conversations.decode_transcript_segments_verified(
                lane.uid,
                row.get('transcript_segments'),
                bool(row.get('transcript_segments_compressed')),
            )
            result.append(row)
    return result


def test_replay_has_one_assignment_one_enrichment_version_and_durable_before_client(lane):
    batch = lane.seed()
    lane.finish(batch)
    result = lane.projector.project(batch.ids[0])
    row = active_rows(lane)[0]
    assert row['status'] == 'completed' and row['sync_content_revision'] == 1
    assert row['transcript_segments'][0]['text'] == 'We discussed the project.'
    assert row['transcript_segments'][0]['speaker_id_scope'] == f'sync:{batch.ids[0]}'
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    assert lane.projector.status(lane.uid, batch.binding.content_id)['status'] == 'completed'
    assert lane.published == [result]
    assert lane.projector.project(batch.ids[0]) == result
    assert active_rows(lane)[0]['sync_content_revision'] == 1
    assert len(lane.tasks) == 1 and lane.loads == [batch.ids[0]]
    outbox = (
        lane.client.collection(lane.reprocess.COLLECTION)
        .document(lane.reprocess.key(lane.uid, row['id']))
        .get()
        .to_dict()
    )
    assert outbox['version'] == 1


def test_out_of_order_compute_and_projection_waits_for_capture_predecessor(lane):
    from database.batch_pipeline_projection import ProjectionBlocked

    batch = lane.seed(('a', 'b'))
    assert lane.finish(batch, 1) is None
    with pytest.raises(ProjectionBlocked):
        lane.projector.project(batch.ids[1])
    assert lane.finish(batch, 0)['segment_id'] == batch.ids[0]
    assert lane.merge.commit_next(lane.uid, 2)['segment_id'] == batch.ids[1]
    with pytest.raises(ProjectionBlocked, match='earlier'):
        lane.projector.project(batch.ids[1])
    assert lane.projector.project(batch.ids[0]) is None
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.published
    completed = lane.projector.project(batch.ids[1])
    assert completed['failed_segments'] == 0
    assert completed['new_memories'] == completed['updated_memories']
    rows = active_rows(lane)
    assert len(rows) == 1 and rows[0]['sync_content_revision'] == 2
    assert len(rows[0]['transcript_segments']) == 2


def test_competing_same_uid_projection_commits_once(lane):
    batch = lane.seed()
    lane.finish(batch)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lane.projector.project, [batch.ids[0], batch.ids[0]]))
    assert results[0] == results[1]
    assert active_rows(lane)[0]['sync_content_revision'] == 1
    assert len(lane.tasks) == 1


def test_crash_after_assignment_resumes_without_appending(lane, monkeypatch):
    batch = lane.seed()
    lane.finish(batch)

    def lost_reply(*_):
        raise RuntimeError('synthetic crash after Firestore assignment commit')

    monkeypatch.setattr(lane.conversations, '_sync_conversation_search_index', lost_reply)
    with pytest.raises(RuntimeError, match='synthetic crash'):
        lane.projector.project(batch.ids[0])
    assert len(active_rows(lane)) == 1
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.tasks and not lane.published
    monkeypatch.setattr(lane.conversations, '_sync_conversation_search_index', lambda *_: None)
    lane.projector.project(batch.ids[0])
    assert active_rows(lane)[0]['sync_content_revision'] == 1 and len(lane.tasks) == 1


def test_crash_after_enrichment_commit_keeps_exactly_one_mark(lane, monkeypatch):
    batch = lane.seed()
    lane.finish(batch)

    def lost_enqueue_reply(row):
        raise RuntimeError('synthetic lost enqueue reply')

    monkeypatch.setattr(lane.reprocess, '_enqueue', lost_enqueue_reply)
    with pytest.raises(RuntimeError, match='synthetic lost enqueue'):
        lane.projector.project(batch.ids[0])
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.published
    monkeypatch.setattr(lane.reprocess, '_enqueue', lambda row: lane.tasks.append(row))
    lane.projector.project(batch.ids[0])
    row = active_rows(lane)[0]
    outbox = (
        lane.client.collection(lane.reprocess.COLLECTION)
        .document(lane.reprocess.key(lane.uid, row['id']))
        .get()
        .to_dict()
    )
    assert outbox['version'] == 1
    assert not lane.tasks  # #21679 durable outbox sweep owns enqueue repair.


def test_crash_after_ledger_completion_repairs_client_without_reprocessing(lane):
    batch = lane.seed()
    lane.finish(batch)

    def unavailable(*_):
        assert batch.ledger.get().to_dict()['status'] == 'completed'
        raise RuntimeError('synthetic Redis unavailable')

    lane.projector.publish = unavailable
    with pytest.raises(RuntimeError, match='Redis'):
        lane.projector.project(batch.ids[0])
    lane.projector.publish = lambda b, r: lane.published.append(r)
    lane.projector.project(batch.ids[0])
    assert len(lane.published) == 1 and len(lane.tasks) == 1 and len(lane.loads) == 1


@pytest.mark.parametrize('kind', ['account', 'conversation'])
def test_deletion_during_projection_cannot_resurrect_or_complete(lane, monkeypatch, kind):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from utils.batch_pipeline import projection

    batch = lane.seed()
    lane.finish(batch)
    built, deleted = threading.Event(), threading.Event()
    original = projection.build_incoming

    def pause(*args):
        incoming = original(*args)
        built.set()
        assert deleted.wait(10)
        return incoming

    monkeypatch.setattr(projection, 'build_incoming', pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lane.projector.project, batch.ids[0])
        assert built.wait(10)
        if kind == 'account':
            lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'queued'})
        else:
            lane.user.collection('deleted_conversations').document(batch.items[0].conversation_id).set(
                {'deleted': True}
            )
        deleted.set()
        with pytest.raises(BatchPrivacyBlocked):
            future.result()
    assert not active_rows(lane) and not lane.tasks and not lane.published
    assert batch.ledger.get().to_dict()['status'] == 'processing'


def test_silence_commits_without_loading_transcript_or_marking_enrichment(lane):
    batch = lane.seed()
    lane.finish(batch, outcome='silence')
    result = lane.projector.project(batch.ids[0])
    assert result['outcome'] == 'expected_silence'
    assert not active_rows(lane) and not lane.tasks and not lane.loads
    assert len(lane.published) == 1


def test_expired_redis_never_lets_legacy_take_batch_content(lane, monkeypatch):
    from database import sync_ledger

    batch = lane.seed()
    monkeypatch.setattr(sync_ledger, 'get_sync_job', lambda *_: pytest.fail('batch must not consult Redis ownership'))
    claim = sync_ledger.claim_sync_content(
        lane.uid, batch.binding.content_id, 'legacy-twin', 'backfill', firestore_client=lane.client
    )
    assert claim['outcome'] == 'busy' and claim['dispatch_protocol'] == 'batch_v1'
    assert not sync_ledger.bind_sync_content_run_token(
        lane.uid, batch.binding.content_id, batch.binding.job_id, 'old', 1, firestore_client=lane.client
    ).bound
    assert not sync_ledger.release_sync_content_claim_after_job_retired(
        lane.uid, batch.binding.content_id, batch.binding.job_id, firestore_client=lane.client
    )
    assert not sync_ledger.mark_sync_content_completed(
        lane.uid,
        batch.binding.content_id,
        batch.binding.job_id,
        {'failed_segments': 0, 'total_segments': 1, 'errors': [], 'outcome': 'success'},
        firestore_client=lane.client,
    )
    assert batch.ledger.get().to_dict()['status'] == 'processing'


def test_assignment_read_contention_uses_bounded_retry_without_duplicate_receipt(lane, monkeypatch):
    from google.api_core.exceptions import Aborted

    batch = lane.seed()
    lane.finish(batch)
    original = lane.conversations.assign_sync_conversation
    attempts = []

    def contention(*args, **kwargs):
        guard = kwargs['before_assign']

        def flaky(transaction):
            guard(transaction)
            attempts.append(1)
            if len(attempts) == 1:
                raise Aborted('synthetic read-time contention')

        return original(*args, **{**kwargs, 'before_assign': flaky})

    monkeypatch.setattr(lane.conversations, 'assign_sync_conversation', contention)
    lane.projector.project(batch.ids[0])
    assert len(attempts) == 2
    assert active_rows(lane)[0]['sync_content_revision'] == 1 and len(lane.tasks) == 1


def test_assignment_failure_rolls_back_receipt_and_ledger_checkpoint(lane, monkeypatch):
    from database.batch_pipeline_projection import ProjectionSession

    batch = lane.seed()
    lane.finish(batch)
    original = ProjectionSession.persist

    def crash(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('synthetic crash before atomic commit')

    monkeypatch.setattr(ProjectionSession, 'persist', crash)
    with pytest.raises(RuntimeError, match='before atomic commit'):
        lane.projector.project(batch.ids[0])
    assert not active_rows(lane)
    assert not batch.ledger.get().to_dict().get('processed_segment_ids')
    assert 'projection' not in lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    monkeypatch.setattr(ProjectionSession, 'persist', original)
    lane.projector.project(batch.ids[0])
    assert len(active_rows(lane)) == 1 and len(lane.tasks) == 1


def test_distinct_same_uid_projections_race_without_reversing_capture_order(lane):
    from database.batch_pipeline_projection import ProjectionBlocked

    batch = lane.seed(('a', 'b'))
    lane.finish(batch, 0)
    lane.finish(batch, 1)

    def project(sid):
        try:
            return lane.projector.project(sid)
        except ProjectionBlocked:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(project, batch.ids))
    for sid in batch.ids:
        lane.projector.project(sid)
    row = active_rows(lane)[0]
    assert row['sync_content_revision'] == 2
    assert [s['speaker_id_scope'] for s in row['transcript_segments']] == [f'sync:{sid}' for sid in batch.ids]


def test_delete_after_assignment_cannot_recreate_reprocess_obligation(lane, monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from utils.sync import bridge

    batch = lane.seed()
    lane.finish(batch)
    original = bridge.finish_sync_bridges

    def delete_before_mark(uid, cid):
        result = original(uid, cid)
        lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'queued'})
        return result

    monkeypatch.setattr(bridge, 'finish_sync_bridges', delete_before_mark)
    with pytest.raises(BatchPrivacyBlocked):
        lane.projector.project(batch.ids[0])
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.tasks and not lane.published
    assert not list(lane.client.collection(lane.reprocess.COLLECTION).stream())


def test_durable_sweep_recovers_lost_after_merge_callback(lane):
    batch = lane.seed()
    lane.finish(batch)
    assert not active_rows(lane)
    assert lane.projector.sweep() == {'completed': 1, 'waiting': 0, 'blocked': 0, 'error': 0}
    assert lane.projector.sweep() == {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}


def test_private_audio_reuses_legacy_persistence_then_replay_skips_upload(lane, monkeypatch):
    from dataclasses import asdict
    from utils.sync import merge_audio

    batch = lane.seed()
    binding = replace(batch.binding, private_cloud_sync_enabled=True)
    lane.projector.store.ref('jobs', batch.ids[0]).update({'projection_binding': asdict(binding)})
    lane.finish(batch)
    audio, calls = [], []
    lane.projector.fetch_audio = lambda item: audio.append(item.segment_id) or b'synthetic-wav'
    monkeypatch.setattr(merge_audio, 'store_intake_audio', lambda *args: calls.append(args))
    lane.projector.project(batch.ids[0])
    assert audio == [batch.ids[0]] and len(calls) == 1
    assert calls[0][0] == lane.uid and calls[0][1] == batch.items[0].capture_at
    assert calls[0][4][0]['start'] == 0 and calls[0][4][0]['end'] == 4
    assert calls[0][5] == 1 and calls[0][6] is True
    lane.projector.project(batch.ids[0])
    assert len(calls) == 1


def test_real_fenced_client_status_changes_only_after_durable_persist(lane, monkeypatch):
    import fakeredis
    from database import sync_jobs
    from utils.batch_pipeline.projection import publish_client_completion

    batch = lane.seed()
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', redis)
    sync_jobs.create_sync_job(lane.uid, 1, 1, batch.binding.job_id, content_id=batch.binding.content_id)
    lane.finish(batch)
    original = lane.projector.load_result

    def load(item, uri):
        assert sync_jobs.get_sync_job(batch.binding.job_id)['status'] == 'queued'
        assert batch.ledger.get().to_dict()['status'] == 'processing'
        return original(item, uri)

    lane.projector.load_result = load
    lane.projector.publish = publish_client_completion
    result = lane.projector.project(batch.ids[0])
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    client_job = sync_jobs.get_sync_job(batch.binding.job_id)
    assert client_job['status'] == 'completed' and client_job['result'] == result


def test_erased_gap_can_advance_cursor_without_recreating_deleted_payload(lane):
    from database.batch_pipeline_purge import purge_batch_owner

    first = lane.seed(('first',), capture_at=1000)
    erased = lane.seed(('erased',), capture_at=1030)
    last = lane.seed(('last',), capture_at=1060)
    for batch in (first, erased, last):
        lane.finish(batch)
    cid = erased.items[0].conversation_id
    lane.user.collection('deleted_conversations').document(cid).set({'deleted': True})
    purge_batch_owner(
        lane.uid,
        firestore_client=lane.client,
        conversation_id=cid,
        namespaces=[lane.store.namespace],
        delete_uri=lambda *_: None,
    )
    stub = lane.projector.store.ref('results', erased.ids[0])
    assert stub.get().to_dict()['projection_state'] == 'erased'
    assert 'expires_at' not in stub.get().to_dict()
    lane.projector.project(first.ids[0])
    lane.projector.project(last.ids[0])
    assert 'result' not in stub.get().to_dict() and 'expires_at' in stub.get().to_dict()
    assert not lane.projector.store.ref('jobs', erased.ids[0]).get().exists
    assert active_rows(lane)[0]['sync_content_revision'] == 2


def test_erased_sibling_is_terminal_user_authority_without_resurrection(lane):
    from database.batch_pipeline_purge import purge_batch_owner

    batch = lane.seed(('keep', 'erase'))
    lane.finish(batch, 0)
    lane.finish(batch, 1)
    cid = batch.items[1].conversation_id
    lane.user.collection('deleted_conversations').document(cid).set({'deleted': True})
    purge_batch_owner(
        lane.uid,
        firestore_client=lane.client,
        conversation_id=cid,
        namespaces=[lane.store.namespace],
        delete_uri=lambda *_: None,
    )
    result = lane.projector.project(batch.ids[0])
    assert result['total_segments'] == 2 and result['failed_segments'] == 0
    assert result['outcome'] == 'success'
    assert not lane.projector.store.ref('jobs', batch.ids[1]).get().exists
    assert active_rows(lane)[0]['sync_content_revision'] == 1
    assert not lane.user.collection('conversations').document(cid).get().exists


def test_receipt_ttl_and_body_cleanup_are_armed_only_after_completion(lane):
    batch = lane.seed()
    lane.finish(batch)
    ref = lane.projector.store.ref('results', batch.ids[0])
    assert 'expires_at' not in ref.get().to_dict()
    lane.projector.project(batch.ids[0])
    row = ref.get().to_dict()
    assert row['projection_state'] == 'completed'
    assert row['expires_at'].timestamp() == lane.clock() + 45 * 86400


def test_hourly_usage_and_fair_use_are_once_only_with_completion_replay(lane):
    batch = lane.seed()
    lane.finish(batch)
    lane.projector.project(batch.ids[0])
    lane.projector.project(batch.ids[0])
    usage = list(lane.user.collection('hourly_usage').stream())
    assert len(usage) == 1
    row = usage[0].to_dict()
    assert row['transcription_seconds'] == 4 and row['speech_seconds'] == 4
    assert row['plan_usage']['pro']['speech_seconds'] == 4
    assert batch.ledger.get().to_dict()['usage_committed_at'] is not None


def test_leading_silence_preserves_absolute_capture_and_playback_clock(lane):
    batch = lane.seed()
    lane.payload['words'] = [
        {**word, 'timestamp': [word['timestamp'][0] + 10, word['timestamp'][1] + 10]} for word in lane.payload['words']
    ]
    lane.payload['diarization']['turns'] = [{'start': 10, 'end': 20, 'speaker': 'SPEAKER_00'}]
    lane.finish(batch)
    lane.projector.project(batch.ids[0])
    row = active_rows(lane)[0]
    assert row['started_at'].timestamp() == batch.items[0].capture_at
    assert row['transcript_segments'][0]['start'] == 10
    assert row['finished_at'].timestamp() == batch.items[0].capture_at + 14
