"""Real assignment/ledger/outbox crash boundaries; loopback emulator only."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from itertools import permutations
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import json
import os
import subprocess
import sys
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
    monkeypatch.setenv('SYNC_TASKS_QUEUE', 'sync-jobs')
    monkeypatch.setenv('SYNC_TASKS_HANDLER_URL', 'https://fresh.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_TASKS_INVOKER_SA', 'invoker@example.invalid')
    monkeypatch.delenv('SYNC_TASKS_OIDC_AUDIENCE', raising=False)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_BACKFILL_ROUTING_ENABLED', 'false')
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

    def seed(
        names=('a',), *, device=None, protection='standard', capture_at=1000.0, duration_seconds=30.0, owner_id=None
    ):
        owner_id = owner_id or uid
        client.collection('users').document(owner_id).set({'data_protection_level': 'standard'})
        ids = tuple(f'{name}-{uuid4().hex[:8]}' for name in names)
        binding = ProjectionBinding(
            owner_id,
            f'job-{uuid4().hex}',
            f'content-{uuid4().hex}',
            ids,
            client_device_id=device,
            data_protection_level=protection,
        )
        items = [
            WorkItem(
                sid,
                owner_id,
                capture_at + i * 30,
                f'gs://synthetic/{sid}#1',
                duration_seconds,
                Priority.DEEP,
                conversation_id=chunk_identity(owner_id, 'omi', device, False, capture_at + i * 30),
                privacy_generation=0,
            )
            for i, sid in enumerate(ids)
        ]
        assert admit(store, items, binding, 0, namespace=store.namespace)['outcome'] == 'batch'
        ledger = sync_content_ledger_ref(client, owner_id, binding.content_id)
        leases = {}
        for _ in range(240):
            leases.update({lease.item.segment_id: lease for lease in queue.pull(0, min(32, len(items)))})
            if len(leases) == len(items):
                break
        assert len(leases) == len(items)
        return SimpleNamespace(binding=binding, ids=ids, items=items, ledger=ledger, leases=leases)

    def finish(batch, index=0, outcome='success'):
        sid = batch.ids[index]
        assert queue.complete(WorkResult(sid, f'gs://synthetic/results/{sid}#1', outcome), batch.leases[sid].token, 1)
        return merge.commit_next(batch.binding.owner_id, 2)

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

    def pause(*args, **kwargs):
        incoming = original(*args, **kwargs)
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
    assert client_job['status'] == 'completed'
    # Redis intentionally stores only the bounded public result fields.
    assert client_job['result'] == {
        key: result[key] for key in ('new_memories', 'updated_memories', 'failed_segments', 'total_segments', 'errors')
    }


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
    total = list(lane.user.collection('monthly_usage_totals').stream())
    assert len(total) == 1
    assert total[0].to_dict()['totals']['speech_seconds'] == 4
    assert total[0].to_dict()['totals']['transcription_seconds'] == 4


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


def frozen_manifest(lane, batch, **extra):
    import io
    import wave
    from utils.batch_pipeline.audio import with_context

    item, binding = batch.items[0], batch.binding
    context = {
        'owner_id': lane.uid,
        'job_id': binding.job_id,
        'content_id': binding.content_id,
        'segment_id': item.segment_id,
        'capture_at': item.capture_at,
        'source': binding.source,
        'should_lock': binding.is_locked,
        'client_device_id': binding.client_device_id,
        'client_platform': binding.client_platform,
        'conversation_id': binding.target_conversation_id,
        **extra,
    }
    stream = io.BytesIO()
    with wave.open(stream, 'wb') as handle:
        handle.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        handle.writeframes(b'\0' * (32000 * 30))
    return with_context(stream.getvalue(), context)


def ambiguous_manifest(lane, batch, monkeypatch, *, ambiguous_index=None):
    from utils.sync import recording_lineage

    lane.projector.store.ref('jobs', batch.ids[0]).update({'requires_compute_admission': True})
    lane.payload.setdefault('speech_spans', [{'start': 0, 'end': 4}])
    manifest = frozen_manifest(
        lane,
        batch,
        recording_session_id='synthetic-recording',
        audio_start_seconds=batch.items[0].capture_at,
        audio_end_seconds=batch.items[0].capture_at + batch.items[0].duration_seconds,
    )
    lane.projector.fetch_audio = lambda _: manifest
    monkeypatch.setattr(recording_lineage, 'lineage_resolution_requested', lambda *a, **kw: True)
    monkeypatch.setattr(recording_lineage, 'ambiguous_binding_pending', lambda _, reason: reason == 'ambiguous_pending')

    def plan(ids, timestamp_of, duration_of, uid, origin, stamped, source, device, locked, job, reasons):
        index = round((timestamp_of(ids[0]) - batch.items[0].capture_at) / 150)
        reasons[ids[0]] = 'ambiguous_pending' if ambiguous_index is None or index == ambiguous_index else None
        return {ids[0]: None}

    monkeypatch.setattr(recording_lineage, 'plan_segment_targets', plan)


def test_ambiguous_head_retains_custody_and_successor_drains_idempotently(lane, monkeypatch):
    from utils.batch_pipeline.scheduler import owner_key
    from utils.batch_pipeline.retention import expire_completed_segment
    from utils.batch_pipeline.projection_repair import plan_owner, apply_owner
    from utils.batch_pipeline.projection import Projector

    head = lane.seed()
    lane.finish(head)
    ambiguous_manifest(lane, head, monkeypatch)
    tail = lane.seed(capture_at=2000)
    lane.finish(tail)
    from utils.batch_pipeline import context as context_module
    from utils.sync import recording_lineage

    manifests = {
        head.ids[0]: lane.projector.fetch_audio(head.items[0]),
        tail.ids[0]: frozen_manifest(
            lane, tail, recording_session_id='synthetic-tail', audio_start_seconds=2000, audio_end_seconds=2030
        ),
    }
    lane.projector.store.ref('jobs', tail.ids[0]).update({'requires_compute_admission': True})
    lane.projector.fetch_audio = lambda item: manifests[item.segment_id]
    lane.projector.require_lineage_fence = True
    monkeypatch.setattr(context_module, 'sync_live_dedupe_active_for', lambda _: True)
    from utils.batch_pipeline.projection import build_incoming

    live = build_incoming(tail.items[0], tail.binding, lane.payload)
    live['id'] = 'synthetic-tail-target'
    lane.conversations.assign_sync_conversation(lane.uid, live, firestore_client=lane.client)

    def strict_plan(ids, timestamp_of, duration_of, uid, origin, stamped, source, device, locked, job, reasons):
        ambiguous = origin == 'synthetic-recording'
        reasons[ids[0]] = 'ambiguous_pending' if ambiguous else 'bound'
        return {ids[0]: None if ambiguous else 'synthetic-tail-target'}

    monkeypatch.setattr(recording_lineage, 'plan_segment_targets', strict_plan)
    # The serving role pins its own stage policy before an operator may reuse it.
    for sid in (head.ids[0], tail.ids[0]):
        lane.projector.store.read(sid)
    plan = plan_owner(lane.store, lane.uid)
    assert plan['units'] == [head.ids[0], tail.ids[0]]
    assert apply_owner(lane.projector, plan) == {'quarantine_held': 1, 'completed': 1}
    receipt = lane.projector.store.ref('results', head.ids[0]).get().to_dict()
    assert receipt['projection_state'] == 'quarantine_held' and receipt['protocol_version'] == 2
    part = receipt['projection_parts']['0']
    assert part['state'] == 'quarantined' and part['disposition'] == 'ambiguous_generation'
    assert part['held_speech_seconds'] == 4 and part['speech_seconds'] == 0
    assert 'expires_at' not in receipt
    assert head.ledger.get().to_dict()['status'] == 'processing'
    assert not expire_completed_segment(lane.store, lane.uid, head.ids[0], 10000)
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) == tail.ids[0]
    assert len(active_rows(lane)) == 1 and len(lane.published) == 1
    assert sum(len(segment['text'].split()) for segment in active_rows(lane)[0]['transcript_segments']) == 4
    restarted = Projector(lane.store, lane.projector.load_result, publish=lane.projector.publish, clock=lane.clock)
    assert restarted.project(head.ids[0]) is None  # must not reload the manifest or assign held text
    assert apply_owner(restarted, plan_owner(lane.store, lane.uid)) == {}
    assert len(active_rows(lane)) == 1 and len(lane.published) == 1


@pytest.mark.parametrize('ambiguous_index', [0, 1, 2])
def test_multipart_ambiguity_replays_proven_parts_without_completing_held_upload(lane, monkeypatch, ambiguous_index):
    batch = multipart(lane, 3)
    ambiguous_manifest(lane, batch, monkeypatch, ambiguous_index=ambiguous_index)
    assert lane.projector.project(batch.ids[0]) is None
    assert lane.projector.project(batch.ids[0]) is None
    row = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert row['projection_state'] == 'quarantine_held'
    assert row['projection_parts'][str(ambiguous_index)]['state'] == 'quarantined'
    assert len(active_rows(lane)) == 2 and len(lane.tasks) == 2
    assert all(c['sync_content_revision'] == 1 for c in active_rows(lane))
    assert batch.ledger.get().to_dict()['status'] == 'processing' and not lane.published
    assert not list(lane.user.collection('hourly_usage').stream())


def test_quarantine_transaction_rechecks_privacy_before_releasing_head(lane, monkeypatch):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked
    from database.batch_pipeline_projection_session import ProjectionSession
    from utils.batch_pipeline.scheduler import owner_key

    batch = lane.seed()
    lane.finish(batch)
    ambiguous_manifest(lane, batch, monkeypatch)
    original = ProjectionSession.persist_empty

    def erase_before_commit(session, **kwargs):
        if kwargs.get('quarantined'):
            lane.user.update({'data_protection_level': 'e2ee'})
        return original(session, **kwargs)

    monkeypatch.setattr(ProjectionSession, 'persist_empty', erase_before_commit)
    with pytest.raises(BatchPrivacyBlocked):
        lane.projector.project(batch.ids[0])
    row = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert not row.get('projection_parts') and row['protocol_version'] == 1
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) is None
    assert not active_rows(lane)


def test_mixed_quarantine_keeps_proven_followups_discoverable_after_restart(lane, monkeypatch):
    from utils.batch_pipeline.projection import Projector
    from utils.batch_pipeline.metrics import QueueMetrics
    from prometheus_client import CollectorRegistry

    batch = multipart(lane, 3)
    ambiguous_manifest(lane, batch, monkeypatch, ambiguous_index=0)
    lane.projector.persist(batch.ids[0])  # async assignment, no follow-ups
    row = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert row['projection']['state'] == 'quarantined' and row['projection_state'] == 'persisted'
    assert batch.ids[0] in lane.store.projection_pending()
    assert not lane.tasks
    restarted = Projector(lane.store, lane.projector.load_result, publish=lane.projector.publish, clock=lane.clock)
    assert restarted.project(batch.ids[0]) is None
    row = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert row['projection_state'] == 'quarantine_held' and len(lane.tasks) == 2
    assert batch.ids[0] not in lane.store.projection_pending()
    metrics = QueueMetrics(CollectorRegistry())
    metrics.refresh_projection(lane.store, 10000)
    assert metrics.projection_age._value.get() == 9998
    assert not lane.published and batch.ledger.get().to_dict()['status'] == 'processing'


def test_partial_quarantine_crash_retains_watermark_fence_and_resumes(lane, monkeypatch):
    from database.batch_pipeline_projection_session import ProjectionSession
    from utils.batch_pipeline.scheduler import owner_key

    batch = multipart(lane, 3)
    ambiguous_manifest(lane, batch, monkeypatch, ambiguous_index=0)
    original = ProjectionSession.persist_empty

    def lose_first_reply(session, **kwargs):
        receipt = original(session, **kwargs)
        if kwargs.get('quarantined'):
            raise RuntimeError('synthetic partial quarantine crash')
        return receipt

    monkeypatch.setattr(ProjectionSession, 'persist_empty', lose_first_reply)
    with pytest.raises(RuntimeError, match='partial quarantine crash'):
        lane.projector.project(batch.ids[0])
    row = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert row['protocol_version'] == 2 and row['projection_state'] == 'pending'
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) is None
    monkeypatch.setattr(ProjectionSession, 'persist_empty', original)
    assert lane.projector.project(batch.ids[0]) is None
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) == batch.ids[0]
    assert len(active_rows(lane)) == 2 and not lane.published


def test_lost_quarantine_commit_reply_restarts_without_duplicate_or_custody_ttl(lane, monkeypatch):
    from database.batch_pipeline_projection_session import ProjectionSession
    from utils.batch_pipeline.scheduler import owner_key

    batch = lane.seed()
    lane.finish(batch)
    ambiguous_manifest(lane, batch, monkeypatch)
    original = ProjectionSession.persist_empty

    def lost(session, **kwargs):
        receipt = original(session, **kwargs)
        if kwargs.get('quarantined'):
            raise RuntimeError('synthetic lost quarantine reply')
        return receipt

    monkeypatch.setattr(ProjectionSession, 'persist_empty', lost)
    with pytest.raises(RuntimeError, match='lost quarantine reply'):
        lane.projector.project(batch.ids[0])
    monkeypatch.setattr(ProjectionSession, 'persist_empty', original)
    assert lane.projector.project(batch.ids[0]) is None
    assert lane.projector.store.projection_watermark(owner_key(lane.uid)) == batch.ids[0]
    assert not active_rows(lane) and not lane.published


def test_authenticated_manifest_preserves_location_and_uses_legacy_lineage_policy(lane, monkeypatch):
    from utils.batch_pipeline.projection import build_incoming
    from utils.sync import recording_lineage

    batch = lane.seed()
    live = build_incoming(batch.items[0], batch.binding, lane.payload)
    live['id'] = 'live-target'
    lane.conversations.assign_sync_conversation(lane.uid, live, firestore_client=lane.client)
    lane.finish(batch)
    lane.projector.store.ref('jobs', batch.ids[0]).update({'requires_compute_admission': True})
    lane.payload['speech_spans'] = [{'start': 0, 'end': 4}]
    geo = {'latitude': 21.03, 'longitude': 105.85, 'google_place_id': 'synthetic-place'}
    manifest = frozen_manifest(
        lane,
        batch,
        recording_session_id='synthetic-recording',
        audio_start_seconds=1000,
        audio_end_seconds=1030,
        geolocation=geo,
    )
    lane.projector.fetch_audio = lambda _: manifest
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_ENABLED', 'true')
    monkeypatch.setenv('SYNC_LINEAGE_RESOLVE_UID_ALLOWLIST', '')

    def plan(segments, timestamp_of, duration_of, uid, origin, stamped, source, device, locked, job, reasons):
        assert uid == lane.uid and origin == 'synthetic-recording'
        assert timestamp_of(segments[0]) == 1000 and duration_of(segments[0]) == 4
        reasons[segments[0]] = 'bound'
        return {segments[0]: 'live-target'}

    monkeypatch.setattr(recording_lineage, 'plan_segment_targets', plan)
    result = lane.projector.project(batch.ids[0])
    assert result['updated_memories'] == ['live-target'] and not result['new_memories']
    row = lane.user.collection('conversations').document('live-target').get().to_dict()
    assert {key: row['geolocation'][key] for key in geo} == geo


def test_authenticated_manifest_rejects_cross_owner_binding_before_assignment(lane):
    from database.batch_pipeline_projection import ProjectionBlocked

    batch = lane.seed()
    lane.finish(batch)
    lane.projector.store.ref('jobs', batch.ids[0]).update({'requires_compute_admission': True})
    lane.payload['speech_spans'] = [{'start': 0, 'end': 4}]
    manifest = frozen_manifest(lane, batch, owner_id='different-synthetic-owner')
    lane.projector.fetch_audio = lambda _: manifest
    with pytest.raises(ProjectionBlocked, match='metadata binding mismatch'):
        lane.projector.project(batch.ids[0])
    assert not active_rows(lane) and not lane.tasks and not lane.published
    assert batch.ledger.get().to_dict()['status'] == 'processing'


def test_unindexed_legacy_conversation_is_found_through_existing_candidate_lookup(lane):
    from dataclasses import replace
    from utils.batch_pipeline.projection import build_incoming

    batch = lane.seed()
    legacy = build_incoming(replace(batch.items[0], capture_at=990), batch.binding, lane.payload)
    legacy['id'] = 'legacy-record'
    lane.conversations.assign_sync_conversation(lane.uid, legacy, firestore_client=lane.client)
    for snapshot in lane.user.collection('sync_assignment').stream():
        snapshot.reference.delete()
    lane.finish(batch)
    result = lane.projector.project(batch.ids[0])
    assert result['updated_memories'] == ['legacy-record'] and not result['new_memories']
    assert len(active_rows(lane)) == 1


def test_coalesced_enrichment_task_consumes_persisted_transcript_once(lane):
    from utils.batch_pipeline.enrichment import run_enrichment

    batch = lane.seed()
    lane.finish(batch)
    lane.projector.project(batch.ids[0])
    key, row = lane.reprocess.key(lane.uid, active_rows(lane)[0]['id']), lane.tasks[0]
    calls = []

    def process(uid, cid, language):
        assert batch.ledger.get().to_dict()['status'] == 'completed'
        assert lane.user.collection('conversations').document(cid).get().exists
        calls.append((uid, cid, language))

    assert run_enrichment(key, row['task_token'], now=row['due_at'] + 1, process=process) == 'processed'
    assert run_enrichment(key, row['task_token'], now=row['due_at'] + 2, process=process) == 'stale'
    assert len(calls) == 1
    assert not lane.client.collection(lane.reprocess.COLLECTION).document(key).get().exists


def test_enrichment_task_drops_deleted_account_obligation(lane):
    from utils.batch_pipeline.enrichment import run_enrichment

    batch = lane.seed()
    lane.finish(batch)
    lane.projector.project(batch.ids[0])
    row = lane.tasks[0]
    key = lane.reprocess.key(lane.uid, row['conversation_id'])
    lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'queued'})
    calls = []
    assert (
        run_enrichment(key, row['task_token'], now=row['due_at'] + 1, process=lambda *args: calls.append(args))
        == 'superseded'
    )
    assert not calls and not lane.client.collection(lane.reprocess.COLLECTION).document(key).get().exists


def test_backfill_enrichment_retains_configured_worker_queue_and_audience(lane, monkeypatch):
    batch = lane.seed()
    lane.finish(batch)
    monkeypatch.setenv('SYNC_BACKFILL_ROUTING_ENABLED', 'true')
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_QUEUE', 'projects/demo/locations/test/queues/backfill')
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_HANDLER_URL', 'https://synthetic.invalid/v2/sync-jobs/run')
    monkeypatch.setenv('SYNC_BACKFILL_TASKS_OIDC_AUDIENCE', 'https://synthetic.invalid/v2/sync-jobs/run')
    lane.projector.project(batch.ids[0])
    dispatch = lane.tasks[0]['dispatch']
    assert dispatch['queue'].endswith('/queues/backfill')
    assert dispatch['handler'] == 'https://synthetic.invalid/v2/sync-jobs/run'
    assert dispatch['audience'] == 'https://synthetic.invalid/v2/sync-jobs/run'


def multipart(lane, count):
    duration = (count - 1) * 150 + 10
    batch = lane.seed(duration_seconds=duration)
    lane.payload.update(
        audio_seconds=duration,
        speech_seconds=float(count),
        speech_spans=[{'start': i * 150, 'end': i * 150 + 1} for i in range(count)],
        words=[{'word': f'Group {i}.', 'timestamp': [i * 150, i * 150 + 1]} for i in range(count)],
        diarization={'turns': [{'start': 0, 'end': duration, 'speaker': 'SPEAKER_00'}]},
    )
    lane.finish(batch)
    return batch


@pytest.mark.parametrize('count', [2, 3])
def test_multipart_capture_uses_separate_legacy_assignments_and_replays_once(lane, count):
    batch = multipart(lane, count)
    result = lane.projector.project(batch.ids[0])
    rows = sorted(active_rows(lane), key=lambda row: row['started_at'])
    assert len(rows) == count and result['total_segments'] == count
    assert result['new_memories'] == sorted(row['id'] for row in rows)
    assert [row['started_at'].timestamp() for row in rows] == [1000 + 150 * i for i in range(count)]
    assert all(row['sync_content_revision'] == 1 for row in rows)
    assert all(row['transcript_segments'][0]['start'] == 0 for row in rows)
    receipt = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert set(receipt['projection_parts']) == {str(i) for i in range(count)}
    assert set(receipt['conversation_ids']) == set(result['new_memories'])
    assert lane.projector.project(batch.ids[0]) == result
    assert len(lane.tasks) == count and lane.loads == [batch.ids[0]]
    assert all(row['sync_content_revision'] == 1 for row in active_rows(lane))
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    usage = list(lane.user.collection('hourly_usage').stream())[0].to_dict()
    assert usage['speech_seconds'] == count


@pytest.mark.parametrize('crash_after', [1, 2])
def test_multipart_crash_resumes_first_uncommitted_group_and_holds_owner_cursor(lane, monkeypatch, crash_after):
    from utils.batch_pipeline import projection
    from utils.batch_pipeline.scheduler import owner_key

    batch = multipart(lane, 3)
    original = projection.build_incoming
    calls = []

    def crash(*args, **kwargs):
        calls.append(args[0].capture_at)
        if len(calls) == crash_after + 1:
            raise RuntimeError('synthetic between groups')
        return original(*args, **kwargs)

    monkeypatch.setattr(projection, 'build_incoming', crash)
    with pytest.raises(RuntimeError, match='between groups'):
        lane.projector.project(batch.ids[0])
    owner = lane.projector.store.ref('owners', owner_key(lane.uid))
    assert owner.get().to_dict().get('projection_watermark') is None
    assert len(active_rows(lane)) == crash_after
    assert not batch.ledger.get().to_dict().get('processed_segment_ids')
    assert not lane.published
    monkeypatch.setattr(projection, 'build_incoming', original)
    result = lane.projector.project(batch.ids[0])
    assert result['total_segments'] == 3 and len(active_rows(lane)) == 3
    assert all(row['sync_content_revision'] == 1 for row in active_rows(lane))
    assert owner.get().to_dict()['projection_watermark'] == batch.ids[0]
    assert len(lane.tasks) == 3


@pytest.mark.parametrize('part_index', [0, 1, 2])
def test_d_purge_finds_every_multipart_conversation_and_scrubs_all_receipts(lane, part_index):
    from database.batch_pipeline_purge import purge_batch_owner

    batch = multipart(lane, 3)
    lane.projector.project(batch.ids[0])
    rows = sorted(active_rows(lane), key=lambda row: row['started_at'])
    cid = rows[part_index]['id']
    lane.user.collection('deleted_conversations').document(cid).set({'deleted': True})
    lane.user.collection('conversations').document(cid).delete()
    purge_batch_owner(
        lane.uid,
        firestore_client=lane.client,
        conversation_id=cid,
        namespaces=[lane.store.namespace],
        delete_uri=lambda *_: None,
    )
    assert not lane.projector.store.ref('jobs', batch.ids[0]).get().exists
    receipt = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert receipt['projection_state'] == 'erased'
    assert 'projection_parts' not in receipt and 'conversation_ids' not in receipt and 'result' not in receipt
    assert len(active_rows(lane)) == 2  # Other user conversations remain intact.


@pytest.mark.parametrize('kind', ['account', 'conversation'])
def test_delete_during_multipart_never_recreates_later_groups(lane, monkeypatch, kind):
    from database.batch_pipeline_purge import purge_batch_owner
    from utils.batch_pipeline import projection

    batch = multipart(lane, 3)
    original = projection.build_incoming
    calls = []

    def delete_after_first(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            cid = active_rows(lane)[0]['id']
            if kind == 'account':
                lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'queued'})
            else:
                lane.user.collection('deleted_conversations').document(cid).set({'deleted': True})
            purge_batch_owner(
                lane.uid,
                firestore_client=lane.client,
                conversation_id=cid if kind == 'conversation' else None,
                namespaces=[lane.store.namespace],
                delete_uri=lambda *_: None,
            )
            # Existing deletion lifecycle owns conversation removal, not C.
            lane.user.collection('conversations').document(cid).delete()
        return original(*args, **kwargs)

    monkeypatch.setattr(projection, 'build_incoming', delete_after_first)
    from database.batch_pipeline_projection import ProjectionBlocked
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    with pytest.raises((ProjectionBlocked, BatchPrivacyBlocked)):
        lane.projector.project(batch.ids[0])
    assert not active_rows(lane) and not lane.published
    receipt = lane.projector.store.ref('results', batch.ids[0]).get().to_dict() or {}
    assert 'projection_parts' not in receipt
    assert batch.ledger.get().to_dict()['status'] == 'processing'


def test_erased_edge_ttl_waits_for_final_multipart_cursor_commit(lane, monkeypatch):
    from database.batch_pipeline_purge import purge_batch_owner
    from database.batch_pipeline_projection import ProjectionSession
    from utils.batch_pipeline.scheduler import owner_key

    first = lane.seed(capture_at=500)
    erased = lane.seed(capture_at=600)
    lane.finish(first)
    lane.finish(erased)
    cid = erased.items[0].conversation_id
    lane.user.collection('deleted_conversations').document(cid).set({'deleted': True})
    purge_batch_owner(
        lane.uid,
        firestore_client=lane.client,
        conversation_id=cid,
        namespaces=[lane.store.namespace],
        delete_uri=lambda *_: None,
    )
    lane.projector.project(first.ids[0])
    batch = multipart(lane, 2)
    stub = lane.projector.store.ref('results', erased.ids[0])
    original = ProjectionSession.persist

    def fail_final(session, transaction, planned=None):
        receipt = original(session, transaction, planned)
        if session.segment_id == batch.ids[0] and session.part_index == 1:
            raise RuntimeError('synthetic before final commit')
        return receipt

    monkeypatch.setattr(ProjectionSession, 'persist', fail_final)
    with pytest.raises(RuntimeError, match='before final commit'):
        lane.projector.project(batch.ids[0])
    owner = lane.projector.store.ref('owners', owner_key(lane.uid))
    assert owner.get().to_dict()['projection_watermark'] == first.ids[0]
    assert 'expires_at' not in stub.get().to_dict()
    monkeypatch.setattr(ProjectionSession, 'persist', original)
    lane.projector.project(batch.ids[0])
    assert owner.get().to_dict()['projection_watermark'] == batch.ids[0]
    assert 'expires_at' in stub.get().to_dict() and 'result' not in stub.get().to_dict()


def test_concurrent_multipart_replay_never_duplicates_parts_or_marks(lane):
    batch = multipart(lane, 3)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lane.projector.project, [batch.ids[0], batch.ids[0]]))
    assert results[0] == results[1]
    assert len(active_rows(lane)) == 3 and len(lane.tasks) == 3
    assert all(row['sync_content_revision'] == 1 for row in active_rows(lane))


def test_multipart_private_playback_slices_each_legacy_group(lane, monkeypatch):
    from dataclasses import asdict
    import io
    import wave
    from utils.sync import merge_audio

    batch = multipart(lane, 2)
    binding = replace(batch.binding, private_cloud_sync_enabled=True)
    lane.projector.store.ref('jobs', batch.ids[0]).update({'projection_binding': asdict(binding)})
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as output:
        output.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        output.writeframes(b'\0' * (32000 * 160))
    lane.projector.fetch_audio = lambda _: audio.getvalue()
    calls = []

    def persist(uid, timestamp, body, protection, survivors, count, enabled, cid):
        with wave.open(io.BytesIO(body)) as decoded:
            assert decoded.getnframes() == 16000  # Only this 1s group, not 160s capture.
        assert survivors[0]['start'] == 0 and survivors[0]['end'] == 1
        calls.append(timestamp)

    monkeypatch.setattr(merge_audio, 'store_intake_audio', persist)
    lane.projector.project(batch.ids[0])
    lane.projector.project(batch.ids[0])
    assert calls == [1000, 1150]


def test_vad_grouping_does_not_split_on_missing_asr_words(lane):
    batch = lane.seed(duration_seconds=200)
    lane.payload.update(
        audio_seconds=200,
        speech_seconds=151.0,
        speech_spans=[{'start': 0, 'end': 151}],
        words=[{'word': 'First.', 'timestamp': [0, 1]}, {'word': 'Later.', 'timestamp': [150, 151]}],
        diarization={'turns': [{'start': 0, 'end': 200, 'speaker': 'SPEAKER_00'}]},
    )
    lane.finish(batch)
    result = lane.projector.project(batch.ids[0])
    assert result['total_segments'] == 1 and len(active_rows(lane)) == 1


def test_crash_after_final_part_commit_resumes_marks_without_loading_result(lane, monkeypatch):
    batch = multipart(lane, 2)
    calls = []

    def lost_final_reply(*_):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError('synthetic lost final part reply')

    monkeypatch.setattr(lane.conversations, '_sync_conversation_search_index', lost_final_reply)
    with pytest.raises(RuntimeError, match='lost final part reply'):
        lane.projector.project(batch.ids[0])
    assert len(active_rows(lane)) == 2 and batch.ledger.get().to_dict()['status'] == 'processing'
    assert len(lane.tasks) == 1 and not lane.published
    monkeypatch.setattr(lane.conversations, '_sync_conversation_search_index', lambda *_: None)
    result = lane.projector.project(batch.ids[0])
    assert result['total_segments'] == 2 and len(lane.tasks) == 2
    assert lane.loads == [batch.ids[0]]
    assert all(row['sync_content_revision'] == 1 for row in active_rows(lane))


def test_live_wal_concurrent_missing_target_replay_has_one_canonical_row(lane, monkeypatch):
    """WAL wins the first race; listen creates its named row during that attempt."""
    from dataclasses import asdict
    from datetime import datetime, timezone
    from utils.sync import assignment
    from utils.sync.assignment_errors import SyncAssignmentConflict

    monkeypatch.setenv('BATCH_PIPELINE_REQUIRE_LIVE_TARGET_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'true')
    batch = lane.seed(device='synthetic-device')
    binding = replace(batch.binding, target_conversation_id='synthetic-live')
    lane.projector.store.ref('jobs', batch.ids[0]).update({'projection_binding': asdict(binding)})
    lane.finish(batch)
    missing, writing = threading.Event(), threading.Event()
    original = assignment.assign_in_transaction

    def observe_missing(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except SyncAssignmentConflict:
            missing.set()
            # Let the writer start; its commit waits for this transaction's
            # read lock to release when the conflict aborts.
            assert writing.wait(10)
            raise

    monkeypatch.setattr(assignment, 'assign_in_transaction', observe_missing)
    live_ref = lane.user.collection('conversations').document('synthetic-live')

    def live_create():
        assert missing.wait(10)
        writing.set()
        live_ref.set(
            {
                'id': 'synthetic-live',
                'source': 'omi',
                'client_device_id': 'synthetic-device',
                'started_at': datetime.fromtimestamp(1000, timezone.utc),
                'finished_at': datetime.fromtimestamp(1004, timezone.utc),
                'created_at': datetime.fromtimestamp(1000, timezone.utc),
                'transcript_segments': [],
                'is_locked': False,
                'status': 'in_progress',
                'structured': {},
                'data_protection_level': 'standard',
            }
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(live_create)
        projection = pool.submit(lane.projector.project, batch.ids[0])
        with pytest.raises(SyncAssignmentConflict, match='not persisted'):
            projection.result(timeout=20)
        writer.result(timeout=20)
    assert len(active_rows(lane)) == 1 and not live_ref.get().to_dict().get('sync_content_revision')
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    result = lane.projector.project(batch.ids[0])
    assert result['updated_memories'] == ['synthetic-live']
    assert len(active_rows(lane)) == 1
    row = active_rows(lane)[0]
    assert row['sync_content_revision'] == 1
    assert all(s['speaker_id_scope'] == f'final:batch:{batch.ids[0]}' for s in row['transcript_segments'])
    assert lane.projector.project(batch.ids[0]) == result
    assert active_rows(lane)[0]['sync_content_revision'] == 1
    assert len(lane.tasks) == 1


def test_authoritative_append_preserves_manual_text_translation_and_ids(lane, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'true')
    first = lane.seed()
    lane.finish(first)
    lane.projector.project(first.ids[0])
    row = active_rows(lane)[0]
    original = row['transcript_segments'][0]
    original.update(
        text='We discussed the project.',
        original_text='We discussed the project.',
        person_id='synthetic-person',
        speaker_label_source='manual',
        translations=[{'lang': 'fr', 'text': 'Synthetic translation.'}],
    )
    lane.user.collection('conversations').document(row['id']).update(
        {
            'transcript_segments': [original],
            'transcript_segments_compressed': False,
            'has_transcript_corrections': True,
            'manual_speaker_assignments': {
                'segments': {original['id']: {'person_id': 'synthetic-person', 'is_user': False}}
            },
            'manual_speaker_assignments_compressed': False,
        }
    )
    from database import review_store
    from utils.agent_capabilities import transcripts

    correction = {
        'segment_id': original['id'],
        'segment_index': 0,
        'start': original['start'],
        'before': 'project',
        'after': 'plan',
        'kind': 'word',
        'source': 'human',
        'change_id': 'synthetic-edit',
        'undone': False,
    }
    overlay = review_store.encode_doc(lane.uid, {'source': [correction]})
    lane.user.collection('transcript_corrections').document(row['id']).set(overlay)
    second = lane.seed(capture_at=1060)
    from dataclasses import asdict

    binding = replace(second.binding, target_conversation_id=row['id'])
    lane.projector.store.ref('jobs', second.ids[0]).update({'projection_binding': asdict(binding)})
    lane.finish(second)
    lane.projector.project(second.ids[0])
    assert len(active_rows(lane)) == 1
    stored = active_rows(lane)[0]['transcript_segments']
    retained = next(s for s in stored if s['id'] == original['id'])
    for field in ('text', 'translations', 'id', 'person_id', 'speaker_label_source'):
        assert retained[field] == original[field]
    assert all(s['speaker_id_scope'].startswith('final:batch:') for s in stored)
    projected = transcripts.project(lane.uid, active_rows(lane)[0], firestore_client=lane.client)
    edited = next(s for s in projected['transcript_segments'] if s['id'] == original['id'])
    assert edited['text'] == 'We discussed the plan.'
    assert edited['original_text'] == original['text']
    assert lane.user.collection('transcript_corrections').document(row['id']).get().to_dict() == overlay


def test_projection_completed_metric_is_one_per_upload_not_replay(lane, monkeypatch):
    from unittest.mock import Mock
    from database import batch_pipeline_projection as module

    metric = Mock()
    monkeypatch.setattr(module, 'record_correctness', metric)
    batch = lane.seed()
    lane.finish(batch)
    lane.projector.project(batch.ids[0])
    lane.projector.project(batch.ids[0])
    metric.assert_called_once_with('projection_completed', seconds=30.0)


def test_authoritative_gap_ids_do_not_inherit_speaker_zero_manual_owner(lane, monkeypatch):
    from utils.manual_speaker_assignments import apply_manual_assignments

    monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'true')
    lane.payload.update(
        words=[
            {'word': 'First.', 'timestamp': [0, 1]},
            {'word': 'Gap.', 'timestamp': [2, 3]},
            {'word': 'Last.', 'timestamp': [4, 5]},
        ],
        diarization={
            'turns': [{'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'}, {'start': 4, 'end': 5, 'speaker': 'SPEAKER_01'}]
        },
    )
    batch = lane.seed()
    lane.finish(batch)
    lane.projector.project(batch.ids[0])
    segments = active_rows(lane)[0]['transcript_segments']
    assert len({s['speaker_id'] for s in segments}) == 3
    first = next(s for s in segments if s['speaker'] == 'SPEAKER_00')
    gap = next(s for s in segments if s['speaker_match_source'] == 'batch_abstention')
    assert gap['speaker_id'] != first['speaker_id']
    labeled = apply_manual_assignments(
        segments, {'speakers': {str(first['speaker_id']): {'is_user': True, 'person_id': None}}}
    )
    gap = next(s for s in labeled if s['id'] == gap['id'])
    assert not gap['is_user'] and gap['person_id'] is None
    assert gap['speaker_match_source'] == 'batch_abstention'


def test_global_recovery_sweep_advances_past_held_pages_without_extra_query(lane, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_DISPATCH_BATCH_SIZE', '10')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASKS_ENABLED', 'false')
    from unittest.mock import Mock
    from utils.batch_pipeline.quarantine_recovery import QuarantineRecovery
    from utils.batch_pipeline import quarantine_recovery as module

    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    for index in range(12):
        lane.projector.store.ref('jobs', f'held-{index:02d}').set(
            {'owner_id': 'synthetic-first' if index < 10 else 'synthetic-other', 'recovery_state': 'prepared'}
        )
    recovery = QuarantineRecovery(lane.store, Mock())
    recovery.recover = Mock(return_value='held')
    original = module.recovery_candidates
    query = Mock(wraps=original)
    monkeypatch.setattr(module, 'recovery_candidates', query)
    assert recovery.sweep() == {'held': 10}
    assert recovery.sweep() == {'held': 2}
    assert query.call_count == 2
    assert query.call_args.kwargs['after_id'] == 'held-09'
    assert recovery.recover.call_args.args == ('held-11', 'synthetic-other')
    assert recovery.sweep() == {}  # Empty tail resets cursor, without an extra query.
    assert query.call_count == 3
    assert recovery.sweep() == {'held': 10}
    assert query.call_args.kwargs['after_id'] is None


def test_multipart_anonymous_gaps_are_distinct_while_pyannote_voice_is_shared(lane, monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_AUTHORITATIVE_LABELS_ENABLED', 'true')
    batch = lane.seed(duration_seconds=600)
    lane.payload.update(
        audio_seconds=600,
        speech_seconds=600,
        speech_spans=[{'start': 0, 'end': 600}],
        words=[{'word': 'Synthetic.', 'timestamp': [start, start + 1]} for start in (0, 2, 299, 300, 302, 599)],
        diarization={
            'turns': [
                {'start': 0, 'end': 1, 'speaker': 'SPEAKER_00'},
                {'start': 299, 'end': 301, 'speaker': 'SPEAKER_00'},
                {'start': 599, 'end': 600, 'speaker': 'SPEAKER_00'},
            ]
        },
    )
    lane.finish(batch)
    lane.projector.project(batch.ids[0])
    rows = active_rows(lane)
    assert len(rows) == 1
    segments = rows[0]['transcript_segments']
    gaps = [s for s in segments if s['speaker_match_source'] == 'batch_abstention']
    voices = [s for s in segments if s['speaker_match_source'] == 'batch_pyannote']
    assert len(gaps) == 2 and len({s['speaker_id'] for s in gaps}) == 2
    assert len({s['speaker_id'] for s in voices}) == 1
    assert not {s['speaker_id'] for s in voices} & {s['speaker_id'] for s in gaps}


def test_three_instance_sweeps_coalesce_owner_and_complete_once(lane, monkeypatch):
    import fakeredis
    from database import batch_pipeline_projection_claim as claims

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', 'true')
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    batch = lane.seed()
    lane.finish(batch)
    monkeypatch.setenv('BATCH_PIPELINE_ENABLED', 'false')
    entered, release = threading.Event(), threading.Event()
    load = lane.projector.load_result

    def paused_load(*args):
        entered.set()
        assert release.wait(20)
        return load(*args)

    monkeypatch.setattr(lane.projector, 'load_result', paused_load)
    # Independent instances sharing only the real emulator and Redis boundary.
    projectors = [
        lane.Projector(lane.store, paused_load, publish=lane.projector.publish, clock=lane.clock) for _ in range(3)
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(projectors[0].sweep)
        assert entered.wait(20)
        try:
            others = [pool.submit(projector.sweep) for projector in projectors[1:]]
            for future in others:
                assert future.result(timeout=20) == {'completed': 0, 'waiting': 1, 'blocked': 0, 'error': 0}
        finally:
            release.set()
        assert first.result(timeout=30) == {'completed': 1, 'waiting': 0, 'blocked': 0, 'error': 0}
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    assert lane.projector.store.ref('results', batch.ids[0]).get().to_dict()['projection_state'] == 'completed'
    assert len(lane.loads) == len(lane.tasks) == len(lane.published) == 1
    assert len(active_rows(lane)) == 1 and active_rows(lane)[0]['sync_content_revision'] == 1


def test_concurrent_empty_receipt_replay_resumes_durable_completion(lane, monkeypatch):
    from database import batch_pipeline_projection_claim as claims
    from unittest.mock import Mock

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', 'true')
    # Advisory coalescing can be unavailable/expired. Durable replay must remain
    # safe without it; all Firestore transaction races below are real.
    redis = Mock()
    redis.set.side_effect = ConnectionError('synthetic Redis unavailable')
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    batch = lane.seed()
    lane.finish(batch, outcome='silence')
    barrier = threading.Barrier(3)
    check = lane.projector.store.check
    seen = set()
    lock = threading.Lock()

    def synchronized_check(session):
        check(session)
        with lock:
            first_check = threading.get_ident() not in seen
            seen.add(threading.get_ident())
        if first_check:
            barrier.wait(timeout=20)

    monkeypatch.setattr(lane.projector.store, 'check', synchronized_check)
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lane.projector.project, [batch.ids[0]] * 3))
    assert all(result['outcome'] == 'expected_silence' for result in results)
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    assert lane.projector.store.ref('results', batch.ids[0]).get().to_dict()['projection_state'] == 'completed'
    assert not active_rows(lane) and not lane.loads and not lane.tasks


@pytest.mark.parametrize('boundary', ['projection', 'assignment'])
@pytest.mark.parametrize('failure', ['contention', 'expired'])
def test_batch_flag_recovers_real_sdk_read_abort_with_fresh_transaction(lane, monkeypatch, boundary, failure):
    from google.api_core.exceptions import Aborted, InvalidArgument

    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', 'true')
    monkeypatch.delenv('SYNC_ASSIGNMENT_CONTENTION_RETRY_ENABLED', raising=False)
    # The emulator does not deterministically emit read-time contention. Inject
    # its explicit envelope at the real BatchGet transport boundary, as in the
    # shared contention qualification script; begin/rollback/retry/commit and
    # every stored receipt/index/conversation remain real emulator operations.
    import fakeredis
    from database import batch_pipeline_projection_claim as claims

    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    batch = lane.seed()
    lane.finish(batch)
    transport = lane.client._firestore_api._transport
    original = transport._wrapped_methods[transport.batch_get_documents]
    assign = lane.conversations.assign_sync_conversation
    inside_assignment = False
    injected = False
    transactions = []

    def assignment(*args, **kwargs):
        nonlocal inside_assignment
        inside_assignment = True
        try:
            return assign(*args, **kwargs)
        finally:
            inside_assignment = False

    def read(request, **kwargs):
        nonlocal injected
        selected = inside_assignment if boundary == 'assignment' else not inside_assignment
        if request.transaction and selected:
            transactions.append(bytes(request.transaction))
            if not injected:
                injected = True
                if failure == 'expired':
                    raise InvalidArgument('The referenced transaction has expired or is no longer valid')
                raise Aborted('synthetic read-time contention')
        return original(request, **kwargs)

    monkeypatch.setattr(lane.conversations, 'assign_sync_conversation', assignment)
    monkeypatch.setitem(transport._wrapped_methods, transport.batch_get_documents, read)
    result = lane.projector.project(batch.ids[0])
    assert result['outcome'] == 'success' and injected
    assert transactions[0] != transactions[1]
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    assert len(active_rows(lane)) == 1 and active_rows(lane)[0]['sync_content_revision'] == 1
    assert len(lane.tasks) == len(lane.published) == len(lane.loads) == 1


def superseded_anchor(lane, item, *, merged=False):
    """Metadata-only fixture: assignment must reject without decoding content."""
    anchor = lane.user.collection('conversations').document(item.conversation_id)
    survivor = lane.user.collection('conversations').document(f'survivor-{item.segment_id}') if merged else anchor
    survivor.set(
        {
            'id': survivor.id,
            'source': 'omi',
            'client_device_id': None,
            'is_locked': False,
            'sync_content_revision': 1,
            'sync_live_target': True,
        }
    )
    if merged:
        anchor.set({'id': anchor.id, 'deleted': True, 'sync_merged_into': survivor.id})
    return {ref: ref.get().to_dict() for ref in {anchor, survivor}}


@pytest.mark.parametrize('merged', [False, True])
@pytest.mark.parametrize('all_superseded', [False, True])
def test_superseded_assignment_settles_siblings_without_content_or_usage(lane, merged, all_superseded):
    batch = lane.seed(('head', 'sibling'))
    before = superseded_anchor(lane, batch.items[0], merged=merged)
    if all_superseded:
        before.update(superseded_anchor(lane, batch.items[1], merged=merged))
    lane.finish(batch, 0)
    lane.finish(batch, 1)
    assert lane.projector.project(batch.ids[0]) is None
    head = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert head['projection']['disposition'] == 'superseded'
    assert head['projection']['state'] == 'ready' and head['projection']['speech_seconds'] == 0
    result = lane.projector.project(batch.ids[1])
    assert result['failed_segments'] == 0 and result['errors'] == [] and result['outcome'] == 'success'
    assert result['superseded_segments'] == (2 if all_superseded else 1)
    assert all(ref.get().to_dict() == row for ref, row in before.items())
    assert len(lane.tasks) == (0 if all_superseded else 1)
    ledger = batch.ledger.get().to_dict()
    assert ledger['status'] == 'completed' and ledger['usage_committed_at']
    assert set(ledger['processed_segment_ids']) == set(batch.ids)
    usage = list(lane.user.collection('hourly_usage').stream())
    assert (not usage) if all_superseded else usage[0].to_dict()['speech_seconds'] == 4
    loads = list(lane.loads)
    assert lane.projector.project(batch.ids[0]) == result
    assert lane.loads == loads
    assert batch.ledger.get().to_dict()['usage_committed_at'] == ledger['usage_committed_at']
    assert all(
        lane.projector.store.ref('results', sid).get().to_dict()['projection_state'] == 'completed' for sid in batch.ids
    )


@pytest.mark.parametrize('superseded_index', [0, 1, 2])
def test_multipart_supersession_excludes_only_rejected_speech_and_replays(lane, superseded_index):
    from utils.sync.capture import chunk_identity

    batch = multipart(lane, 3)
    item = replace(
        batch.items[0], conversation_id=chunk_identity(lane.uid, 'omi', None, False, 1000 + superseded_index * 150)
    )
    before = superseded_anchor(lane, item)
    result = lane.projector.project(batch.ids[0])
    receipt = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    part = receipt['projection_parts'][str(superseded_index)]
    assert part['disposition'] == 'superseded' and part['speech_seconds'] == 0
    assert receipt['projection']['speech_seconds'] == 2
    assert 'disposition' not in receipt['projection']
    assert result['superseded_segments'] == 1 and result['total_segments'] == 3
    assert len(result['new_memories']) == 2 and len(lane.tasks) == 2
    assert all(ref.get().to_dict() == row for ref, row in before.items())
    assert list(lane.user.collection('hourly_usage').stream())[0].to_dict()['speech_seconds'] == 2
    assert lane.projector.project(batch.ids[0]) == result
    assert len(lane.tasks) == 2


@pytest.mark.parametrize('kind', ['account', 'conversation', 'generation', 'ledger'])
def test_superseded_settlement_rechecks_fences_after_failed_assignment(lane, monkeypatch, kind):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked, privacy_owner_key
    from database.batch_pipeline_projection import ProjectionBlocked
    from utils.sync.assignment_errors import SyncAssignmentSuperseded

    batch = lane.seed()
    lane.finish(batch)
    assign = lane.conversations.assign_sync_conversation

    def fail(*args, **kwargs):
        try:
            return assign(*args, **kwargs)
        except SyncAssignmentSuperseded:
            if kind == 'account':
                lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'queued'})
            elif kind == 'conversation':
                lane.user.collection('deleted_conversations').document(batch.items[0].conversation_id).set(
                    {'deleted': True}
                )
            elif kind == 'generation':
                lane.client.collection('batch_pipeline_privacy').document(privacy_owner_key(lane.uid)).set(
                    {'generation': 1}
                )
            else:
                batch.ledger.update({'job_id': 'other-job'})
            raise

    superseded_anchor(lane, batch.items[0])
    monkeypatch.setattr(lane.conversations, 'assign_sync_conversation', fail)
    with pytest.raises((BatchPrivacyBlocked, ProjectionBlocked)):
        lane.projector.project(batch.ids[0])
    assert not lane.projector.store.ref('results', batch.ids[0]).get().to_dict().get('projection')
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.tasks and not lane.published


def test_all_multipart_superseded_lost_settlement_reply_recovers_without_usage(lane, monkeypatch):
    from database.batch_pipeline_projection_session import ProjectionSession
    from utils.sync.capture import chunk_identity

    batch = multipart(lane, 3)
    for index in range(3):
        superseded_anchor(
            lane,
            replace(batch.items[0], conversation_id=chunk_identity(lane.uid, 'omi', None, False, 1000 + index * 150)),
        )
    persist = ProjectionSession.persist_empty
    lost = []

    def crash(session, **kwargs):
        result = persist(session, **kwargs)
        if session.part_index == 1 and not lost:
            lost.append(True)
            raise RuntimeError('synthetic lost superseded receipt reply')
        return result

    monkeypatch.setattr(ProjectionSession, 'persist_empty', crash)
    with pytest.raises(RuntimeError, match='lost superseded'):
        lane.projector.project(batch.ids[0])
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    result = lane.projector.project(batch.ids[0])
    receipt = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert receipt['projection']['disposition'] == 'superseded' and receipt['projection']['speech_seconds'] == 0
    assert result['superseded_segments'] == result['total_segments'] == 3
    assert result['outcome'] == 'success' and not result['new_memories'] and not result['updated_memories']
    assert not list(lane.user.collection('hourly_usage').stream())
    assert not lane.tasks
    assert lane.projector.project(batch.ids[0]) == result


def test_recovery_batch_dispatch_duplicate_start_and_ordered_merge(lane, monkeypatch):
    from unittest.mock import Mock
    from utils.batch_pipeline import intake, quarantine_recovery as module
    from utils.batch_pipeline.quarantine_recovery import QuarantineRecovery

    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_MODE', 'on')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_ALL_ADMITTED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_RECOVERY_TASK_AUDIENCE', 'https://synthetic.invalid')
    batch = lane.seed(names=tuple(f'unit-{i:02}' for i in range(17)))
    for sid in batch.ids:
        assert lane.queue.fail(sid, batch.leases[sid].token, 1, quarantine=True)
    lane.projector.store.ref('intakes', batch.binding.job_id).set(
        {
            'owner_id': lane.uid,
            'content_id': batch.binding.content_id,
            'segment_ids': list(batch.ids),
            'total_files': 1,
            'lane': 'backfill',
        }
    )
    assert intake.durable_status(lane.store, lane.uid, batch.binding.job_id)['status'] == 'processing'
    recovery = QuarantineRecovery(lane.store, Mock(), clock=lambda: 100)
    enqueued = Mock()
    monkeypatch.setattr(module, 'enqueue_named_task', enqueued)
    assert recovery.sweep() == {'queued': 16}
    assert recovery.sweep() == {'queued': 1}
    assert enqueued.call_count == 17
    # Settle in reverse capture order, with racing duplicate deliveries for
    # each token: only one provider-start winner, then capture-ordered merge.
    for sid in reversed(batch.ids):
        job = recovery.protocol.prepare(sid, lane.uid, 100)
        token = job['recovery']['token']
        with ThreadPoolExecutor(max_workers=2) as pool:
            starts = list(pool.map(lambda _: recovery.protocol.start(sid, token, 100), range(2)))
        assert sorted(starts) == [False, True]
        assert recovery.protocol.settle(sid, token, 101, f'gs://synthetic/{sid}')
        assert not recovery.protocol.start(sid, token, 102)
    entries = [lane.merge.commit_next(lane.uid, 103) for _ in batch.ids]
    assert [entry['segment_id'] for entry in entries] == list(batch.ids)
    assert [entry['previous_segment_id'] for entry in entries] == [None, *batch.ids[:-1]]
    assert intake.durable_status(lane.store, lane.uid, batch.binding.job_id)['poll_after_ms'] == 3000
    # Exercise the real HTTP boundary with the emulator's real privacy fence.
    from database.batch_pipeline_privacy import advance_privacy_generation
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import routers.sync as route

    monkeypatch.setattr(intake, 'FirestoreStore', lambda *args, **kwargs: lane.store)
    monkeypatch.setattr(route, 'admit_sync_job_poll', lambda uid: True)
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route.auth.get_current_user_uid] = lambda: lane.uid
    # Public IDs are bp_ prefixed; alias the same durable receipt for the route.
    public_id = 'bp_recovery_test'
    lane.projector.store.ref('intakes', public_id).set(
        lane.projector.store.ref('intakes', batch.binding.job_id).get().to_dict()
    )
    with TestClient(app) as client:
        active = client.get(f'/v2/sync-local-files/{public_id}')
        assert active.status_code == 200
        assert active.json()['status'] == 'processing' and active.json()['poll_after_ms'] > 0
        advance_privacy_generation(lane.client, lane.uid, blocked=True)
        response = client.get(f'/v2/sync-local-files/{public_id}')
    assert response.status_code == 409
    assert response.json()['code'] == 'sync_batch_privacy_blocked'


@pytest.mark.parametrize('order', list(permutations(range(3))))
def test_head_wait_commit_order_converges_to_one_conversation(lane, monkeypatch, order):
    """Fix C permutation proof through real batch projection.

    Three separately uploaded contiguous units, 100 s apart: units 0 and 2 join
    only through unit 1. Each completes in ``order``; the merge drains W=60 s
    later and committed rows project in log order. Every order, including
    newest-first catch-up and a late bridge, ends as the forward-order state.
    """
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_HEAD_WAIT_SECONDS', '60')
    units = [lane.seed((f'u{index}',), capture_at=1000.0 + index * 100) for index in range(3)]
    sids = [unit.ids[0] for unit in units]
    log = []
    for step, index in enumerate(order):
        unit = units[index]
        assert lane.queue.complete(
            lane.WorkResult(sids[index], f'gs://synthetic/results/{sids[index]}#1'),
            unit.leases[sids[index]].token,
            step,
        )
        while entry := lane.merge.commit_next(lane.uid, step + 60):
            log.append(entry)
            lane.projector.project(entry['segment_id'])
    # Model: every ready row has waited W at each drain, so an unready head
    # releases the ready rows in capture order and appends late itself.
    expected, pending, ready = [], set(range(3)), set()
    for index in order:
        ready.add(index)
        while ready:
            head = min(pending)
            pick = head if head in ready else min(ready)
            expected.append((sids[pick], pick != head))
            pending.discard(pick)
            ready.discard(pick)
    assert [(entry['segment_id'], bool(entry.get('head_wait_bypass'))) for entry in log] == expected
    rows = active_rows(lane)
    assert len(rows) == 1
    assert [s['speaker_id_scope'] for s in rows[0]['transcript_segments']] == [f'sync:{sid}' for sid in sids]
    for snapshot in lane.user.collection('conversations').stream():
        row = snapshot.to_dict()
        if row.get('deleted'):
            # A bridged donor redirects to the surviving conversation; none is orphaned.
            assert row.get('sync_merged_into') == rows[0]['id']
    for unit in units:
        assert unit.ledger.get().to_dict()['status'] == 'completed'


def _repair_cli_env(project, owner_env, owner, host):
    env = dict(os.environ)
    env.update(
        GCLOUD_PROJECT=project,
        FIREBASE_PROJECT_ID=project,
        FIRESTORE_EMULATOR_HOST=host,
        NO_PROXY='127.0.0.1,localhost,::1',
        no_proxy='127.0.0.1,localhost,::1',
    )
    env[owner_env] = owner
    return env


def _run_repair_cli(arguments, env):
    script = str(Path(__file__).resolve().parents[2] / 'scripts/batch_pipeline_projection_repair.py')
    return subprocess.run([sys.executable, script, *arguments], env=env, capture_output=True, text=True, timeout=180)


def test_local_repair_cli_dry_run_is_aggregate_only_and_never_writes():
    from utils.batch_pipeline.scheduler import owner_key

    host = os.getenv('FIRESTORE_EMULATOR_HOST', '')
    if not host.startswith(('127.0.0.1:', 'localhost:')):
        pytest.skip('loopback emulator required; no cloud fallback')
    project = f'demo-pr1-c-{uuid4().hex[:12]}'
    namespace_id = uuid4().hex[:12]
    namespace = f'batch_pipeline_test_{namespace_id}'
    owner = f'synthetic-repair-{uuid4().hex[:8]}'
    key = owner_key(owner)
    client = firestore.Client(project=project, credentials=AnonymousCredentials())
    client.collection(f'{namespace}_owners').document(key).set({'projection_watermark': 'old'})
    for sid, previous, state in [('old', None, 'persisted'), ('head', 'old', 'pending'), ('tail', 'head', 'pending')]:
        client.collection(f'{namespace}_results').document(sid).set(
            {
                'segment_id': sid,
                'owner_key': key,
                'previous_segment_id': previous,
                'projection_state': state,
                'committed_at': 1,
                'result': {'uri': f'gs://synthetic/{sid}'},
            }
        )
        client.collection(f'{namespace}_jobs').document(sid).set(
            {'owner_id': owner, 'policy_parts': {'projection': {'pinned': True}}}
        )
    collections_before = sorted(collection.id for collection in client.collections())
    results_before = {doc.id: doc.to_dict() for doc in client.collection(f'{namespace}_results').stream()}
    jobs_before = {doc.id: doc.to_dict() for doc in client.collection(f'{namespace}_jobs').stream()}
    completed = _run_repair_cli(
        ['--stage', 'local', '--local-namespace', namespace_id, '--owner-env', 'W1_OWNER_UID'],
        _repair_cli_env(project, 'W1_OWNER_UID', owner, host),
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout.strip())
    assert payload['planned_units'] == 3 and payload['apply'] is False
    assert payload['states'] == {'persisted': 1, 'pending': 2}
    assert payload['unpinned_units'] == 0
    assert payload['lookback_missing'] is False and len(payload['plan_sha256']) == 64
    # Aggregate output only: no owner identity or storage paths leak.
    assert owner not in completed.stdout and 'gs://' not in completed.stdout
    # Dry-run stays read-only: identical rows, owner watermark untouched.
    assert {doc.id: doc.to_dict() for doc in client.collection(f'{namespace}_results').stream()} == results_before
    assert {doc.id: doc.to_dict() for doc in client.collection(f'{namespace}_jobs').stream()} == jobs_before
    assert client.collection(f'{namespace}_owners').document(key).get().to_dict() == {'projection_watermark': 'old'}
    assert sorted(collection.id for collection in client.collections()) == collections_before


def test_local_repair_cli_refuses_invalid_namespace_non_loopback_and_prod_overrides():
    base = dict(os.environ)
    base.pop('GCP_AGENT_TIER', None)
    base.pop('FIRESTORE_EMULATOR_HOST', None)
    base.update(NO_PROXY='127.0.0.1,localhost,::1', no_proxy='127.0.0.1,localhost,::1')
    loopback = dict(base, FIRESTORE_EMULATOR_HOST='127.0.0.1:8085')

    def refusals(arguments, env, message):
        completed = _run_repair_cli(arguments, env)
        assert completed.returncode == 2, completed.stdout + completed.stderr
        assert message in completed.stderr

    refusals(['--stage', 'local', '--local-namespace', 'Bad-ID'], loopback, 'must match')
    refusals(['--stage', 'local', '--local-namespace', '../batch_pipeline_prod'], loopback, 'must match')
    refusals(
        ['--stage', 'prod', '--local-namespace', 'anything'],
        loopback,
        '--local-namespace applies to --stage local only',
    )
    refusals(['--stage', 'local'], dict(base, FIRESTORE_EMULATOR_HOST='10.9.8.7:8080'), 'loopback emulator')
    refusals(['--stage', 'local'], base, 'loopback emulator')
    refusals(['--stage', 'prod'], base, 'wrong identity')
