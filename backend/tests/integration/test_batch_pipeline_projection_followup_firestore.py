"""Async follow-up boundaries over real projection/privacy/ledger transactions."""

import pytest

from tests.integration.test_batch_pipeline_projection_firestore import lane, active_rows

import asyncio
from database import batch_pipeline_projection_claim as claims
from database.batch_pipeline_projection import ProjectionBlocked
from utils.batch_pipeline import projection_followup
from utils.sync import reprocess
import fakeredis
from utils.batch_pipeline.projection_followup import ProjectionFollowups
from database import batch_pipeline_projection_claim as claims, sync_jobs
from utils.batch_pipeline.projection import publish_client_completion
from tests.integration.test_batch_pipeline_projection_firestore import superseded_anchor
from unittest.mock import Mock
from database.batch_pipeline_projection_finish_backfill import backfill_ref, BACKFILL_VERSION
from database.batch_pipeline_store import projection_page
from utils.batch_pipeline.serving import Serving
from tests.unit.test_batch_pipeline_scheduler import MemoryStore

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_async_followup_slow_enrichment_keeps_transcript_order_and_atomic_sibling_completion(lane, monkeypatch):

    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', 'true')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    batch = lane.seed(('head', 'later'))
    assert lane.finish(batch, 1) is None
    assert lane.finish(batch, 0)['segment_id'] == batch.ids[0]
    assert lane.merge.commit_next(lane.uid, 2)['segment_id'] == batch.ids[1]
    with pytest.raises(ProjectionBlocked, match='earlier'):
        lane.projector.persist(batch.ids[1])
    lane.projector.persist(batch.ids[0])
    lane.projector.persist(batch.ids[1])
    # Both transcripts are already durably visible, in order, with no
    # enrichment or client completion. No RPC has run under the owner claim.
    assert active_rows(lane)[0]['sync_content_revision'] == 2
    assert len(active_rows(lane)[0]['transcript_segments']) == 2
    assert not lane.tasks and not lane.published
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not redis.keys()
    started, release, later_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real = projection_followup.run_blocking
    mark = lane.projector.store.mark_enrichment

    async def delayed(executor, fn, *args, **kwargs):
        if fn == mark and args[0] == batch.ids[0]:
            started.set()
            await release.wait()
        result = await real(executor, fn, *args, **kwargs)
        if fn == mark and args[0] == batch.ids[1]:
            later_done.set()
        return result

    monkeypatch.setattr(projection_followup, 'run_blocking', delayed)
    runner = projection_followup.ProjectionFollowups(lane.projector)
    try:
        await runner.schedule()
        await asyncio.wait_for(started.wait(), 10)
        await asyncio.wait_for(later_done.wait(), 10)
        # Actual prepare_accounting/complete transactions cannot publish the
        # later sibling while the first receipt is still persisted.
        assert lane.projector.store.prepare_accounting(batch.binding, 10000) is None
        assert batch.ledger.get().to_dict()['status'] == 'processing'
        assert not lane.published
        release.set()
        await asyncio.wait_for(asyncio.gather(*list(runner.tasks.values())), 10)
        completed = batch.ledger.get().to_dict()
        assert completed['status'] == 'completed' and completed['usage_committed_at']
        assert len(lane.published) == 1
        assert all(lane.store.run(lambda tx: tx.get('jobs', sid))['client_status'] == 'completed' for sid in batch.ids)
        outbox = lane.client.collection(reprocess.COLLECTION).document(
            reprocess.key(lane.uid, active_rows(lane)[0]['id'])
        )
        version = outbox.get().to_dict()['version']
        # Lost reply/restart reuses receipts and the already completed ledger.
        await runner.run(batch.ids[0])
        assert batch.ledger.get().to_dict()['usage_committed_at'] == completed['usage_committed_at']
        assert outbox.get().to_dict()['version'] == version
        assert active_rows(lane)[0]['sync_content_revision'] == 2
    finally:
        release.set()
        await asyncio.gather(*list(runner.tasks.values()), return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['account', 'conversation'])
async def test_async_followup_rechecks_deletion_after_assignment(lane, monkeypatch, kind):

    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    monkeypatch.setattr(claims, '_redis_client', lambda: fakeredis.FakeRedis())
    batch = lane.seed()
    lane.finish(batch)
    lane.projector.persist(batch.ids[0])
    if kind == 'account':
        lane.client.collection('account_deletions').document(lane.uid).set({'wipe_status': 'queued'})
    else:
        cid = active_rows(lane)[0]['id']
        lane.user.collection('deleted_conversations').document(cid).set({'deleted': True})
    await ProjectionFollowups(lane.projector).run(batch.ids[0])
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert not lane.published and not lane.tasks
    entry = lane.projector.store.ref('results', batch.ids[0]).get().to_dict()
    assert entry['projection']['state'] == 'persisted'


@pytest.mark.asyncio
@pytest.mark.parametrize('committed', [False, True])
async def test_followup_timeout_replays_enrichment_without_duplicate_debt_or_usage(lane, monkeypatch, committed):

    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    monkeypatch.setattr(projection_followup, 'FOLLOWUP_TIMEOUT_SECONDS', 2)
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_BACKOFF_SECONDS', '120')
    now = [1000.0]
    monkeypatch.setattr(projection_followup, '_monotonic', lambda: now[0])
    batch = lane.seed()
    client_redis = fakeredis.FakeRedis()
    monkeypatch.setattr(sync_jobs, 'r', client_redis)
    sync_jobs.create_sync_job(lane.uid, 1, 1, batch.binding.job_id, content_id=batch.binding.content_id)
    lane.projector.publish = publish_client_completion
    lane.finish(batch)
    sid = batch.ids[0]
    lane.projector.persist(sid)
    runner = projection_followup.ProjectionFollowups(lane.projector)
    real = projection_followup.run_blocking
    mark = lane.projector.store.mark_enrichment
    cancelled = asyncio.Event()

    async def interrupted(executor, fn, *args, **kwargs):
        if fn == mark:
            if committed:
                await real(executor, fn, *args, **kwargs)
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return await real(executor, fn, *args, **kwargs)

    monkeypatch.setattr(projection_followup, 'run_blocking', interrupted)
    await runner.schedule()
    await asyncio.wait_for(asyncio.gather(*list(runner.tasks.values())), 5)
    await asyncio.sleep(0)
    assert cancelled.is_set() and not runner.closed and not runner.tasks
    assert not redis.keys()
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert sync_jobs.get_sync_job(batch.binding.job_id)['status'] == 'queued'
    entry = lane.projector.store.ref('results', sid).get().to_dict()
    assert entry['projection']['state'] == ('ready' if committed else 'persisted')
    outbox = lane.client.collection(reprocess.COLLECTION).document(reprocess.key(lane.uid, active_rows(lane)[0]['id']))
    version = outbox.get().to_dict()['version'] if committed else None
    loads = list(lane.loads)
    monkeypatch.setattr(projection_followup, 'run_blocking', real)
    monkeypatch.setattr(projection_followup, 'FOLLOWUP_TIMEOUT_SECONDS', 120)
    # A timeout deliberately backs this receipt off. Discovery must preserve
    # it without retrying before the deadline, then resume both persisted and
    # ready-but-not-completed receipts from the actual durable outbox.
    retry_at, _ = runner.backoff[sid]
    now[0] = retry_at - 0.001
    await runner.schedule()
    assert not runner.tasks
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    assert lane.loads == loads
    now[0] = retry_at
    await runner.schedule()
    await asyncio.wait_for(asyncio.gather(*list(runner.tasks.values())), 10)
    completed = batch.ledger.get().to_dict()
    assert completed['status'] == 'completed'
    client_job = sync_jobs.get_sync_job(batch.binding.job_id)
    assert client_job['status'] == 'completed'
    replay_version = outbox.get().to_dict()['version']
    if committed:
        assert replay_version == version
    await runner.run(sid)
    assert outbox.get().to_dict()['version'] == replay_version
    assert batch.ledger.get().to_dict()['usage_committed_at'] == completed['usage_committed_at']
    assert sync_jobs.get_sync_job(batch.binding.job_id) == client_job
    assert lane.loads == loads
    assert active_rows(lane)[0]['sync_content_revision'] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('silence_skip', ['false', 'true'])
async def test_projection_discovery_drains_beyond_101_ready_rows_without_reprojection(lane, monkeypatch, silence_skip):
    """The old first page pins forever; both real scanners must escape it."""

    monkeypatch.setenv('BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED', silence_skip)

    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    # Isolate paginated discovery. Newer owner-chain walking and pending-only
    # assignment pages intentionally bypass the legacy mixed-page stall.
    monkeypatch.setenv('BATCH_PIPELINE_SWEEP_OWNER_CHAIN_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PENDING_PAGE_ENABLED', 'false')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', 'true')
    monkeypatch.setattr(claims, '_redis_client', lambda: fakeredis.FakeRedis())
    # All commit timestamps tie. Document-ID ordering must still cross pages.
    batch = lane.seed(tuple(f'a{i:03}' for i in range(101)) + ('z-sibling',))
    for i in range(len(batch.ids)):
        assert lane.finish(batch, i, outcome='silence')['segment_id'] == batch.ids[i]
    for sid in batch.ids[:-1]:
        lane.projector.persist(sid)
        lane.projector.store.ready(sid, batch.binding, lane.clock())
    assert lane.projector.store.prepare_accounting(batch.binding, lane.clock()) is None
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    later = lane.seed(('zz-actionable',), capture_at=10000, owner_id=lane.uid + '-other')
    lane.finish(later, outcome='silence')
    legacy = lane.store.projection_pending()
    assert len(legacy) == 100 and all(sid in batch.ids[:-1] for sid in legacy)
    assert batch.ids[-1] not in legacy and later.ids[0] not in legacy
    # Rollback reproduces the original stall without changing a fence.
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', 'false')
    for _ in range(2):
        lane.projector.sweep()
    assert not lane.projector.store.ref('results', batch.ids[-1]).get().to_dict().get('projection')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_PAGINATION_ENABLED', 'true')
    lane.projector.sweep()
    lane.projector.sweep()
    assert lane.projector.store.ref('results', batch.ids[-1]).get().to_dict()['projection']
    assert lane.projector.store.ref('results', later.ids[0]).get().to_dict()['projection']
    # The follow-up cursor starts at the head. Enabled silence assignment is
    # already ready, so the first page can complete the whole upload. Rollback
    # retains the old persisted sibling and independent cursor boundary.
    runner = projection_followup.ProjectionFollowups(lane.projector)
    await runner.schedule()
    while runner.tasks:
        await asyncio.gather(*list(runner.tasks.values()))
        await asyncio.sleep(0)
    assert batch.ledger.get().to_dict()['status'] == ('completed' if silence_skip == 'true' else 'processing')
    assert later.ledger.get().to_dict()['status'] == 'processing'
    await runner.schedule()
    while runner.tasks:
        await asyncio.gather(*list(runner.tasks.values()))
        await asyncio.sleep(0)
    assert later.ledger.get().to_dict()['status'] == 'completed'
    # Restart resets only hints. Completed rows have left the discovery query.
    restarted = projection_followup.ProjectionFollowups(lane.projector)
    await restarted.schedule()
    while restarted.tasks:
        await asyncio.gather(*list(restarted.tasks.values()))
        await asyncio.sleep(0)
    completed = batch.ledger.get().to_dict()
    assert completed['status'] == 'completed'
    assert not lane.loads  # No STT/result reload, including across replay/restart.
    assert not lane.tasks  # Silence creates no enrichment obligation.
    published = len(lane.published)
    assert published >= 2
    for _ in range(3):
        lane.projector.sweep()
        await restarted.schedule()
        while restarted.tasks:
            await asyncio.gather(*list(restarted.tasks.values()))
    assert batch.ledger.get().to_dict() == completed
    assert len(lane.published) == published


@pytest.mark.asyncio
async def test_async_assignment_supersession_drains_all_sibling_receipts(lane, monkeypatch):

    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    batch = lane.seed(('head', 'sibling'))
    for item in batch.items:
        superseded_anchor(lane, item, merged=True)
    lane.finish(batch, 0)
    lane.finish(batch, 1)
    for sid in batch.ids:
        lane.projector.persist(sid)
    assert batch.ledger.get().to_dict()['status'] == 'processing'
    runner = ProjectionFollowups(lane.projector)
    await runner.run(batch.ids[0])
    assert batch.ledger.get().to_dict()['status'] == 'completed'
    assert lane.published[0]['superseded_segments'] == 2
    assert not lane.tasks and not list(lane.user.collection('hourly_usage').stream())
    assert all(
        lane.projector.store.ref('results', sid).get().to_dict()['projection_state'] == 'completed' for sid in batch.ids
    )


@pytest.mark.asyncio
async def test_excluded_async_finish_rows_still_schedule_and_complete(lane, monkeypatch):

    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PROJECTION_FINISH_ASYNC_SKIP_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    monkeypatch.setattr(claims, '_redis_client', lambda: fakeredis.FakeRedis())
    batch = lane.seed()
    lane.finish(batch)
    sid = batch.ids[0]
    lane.projector.persist(sid)
    row = lane.projector.store.ref('results', sid).get().to_dict()
    assert row['projection_finish_due_at'] == -1.0
    # The independently stamped follow-up query must still discover async rows
    # excluded from finish discovery, on the real loopback Firestore engine.
    assert row['projection_followup_due_at'] == lane.clock()
    assert sid not in projection_page(lane.client, lane.store.namespace, due_before=lane.clock(), exclude_async=True)[0]
    assert (
        sid
        in projection_page(lane.client, lane.store.namespace, followup_due_before=lane.clock(), exclude_async=True)[0]
    )
    backfill_ref(lane.client, lane.store.namespace).set({'version': BACKFILL_VERSION, 'complete': True})
    read = lane.projector.store.read
    lane.projector.store.read = Mock(wraps=read)
    counts = lane.projector.sweep()
    assert counts == {'completed': 0, 'waiting': 0, 'blocked': 0, 'error': 0}
    lane.projector.store.read.assert_not_called()
    assert lane.projector.has_async_followups
    # Exercise the serving dispatch gate, real discovery, fenced receipt reads,
    # enrichment, accounting, client publish and durable completion.
    service = Serving(MemoryStore(), projector=lane.projector)
    service.reconcile = lambda **_: []
    try:
        await service.reconcile_async()
        runner = lane.projector.followups
        assert runner is not None
        await asyncio.wait_for(asyncio.gather(*list(runner.tasks.values())), 10)
        assert batch.ledger.get().to_dict()['status'] == 'completed'
        assert lane.projector.store.ref('results', sid).get().to_dict()['projection_state'] == 'completed'
        assert len(lane.published) == 1
    finally:
        if lane.projector.followups:
            await asyncio.gather(*list(lane.projector.followups.tasks.values()), return_exceptions=True)
