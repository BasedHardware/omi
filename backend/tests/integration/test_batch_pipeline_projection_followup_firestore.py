"""Async follow-up boundaries over real projection/privacy/ledger transactions."""

import pytest

from tests.integration.test_batch_pipeline_projection_firestore import lane, active_rows

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_async_followup_slow_enrichment_keeps_transcript_order_and_atomic_sibling_completion(lane, monkeypatch):
    import asyncio
    from database import batch_pipeline_projection_claim as claims
    from database.batch_pipeline_projection import ProjectionBlocked
    from utils.batch_pipeline import projection_followup
    from utils.sync import reprocess
    import fakeredis

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
    from database import batch_pipeline_projection_claim as claims
    from utils.batch_pipeline.projection_followup import ProjectionFollowups
    import fakeredis

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
    import asyncio
    from database import batch_pipeline_projection_claim as claims, sync_jobs
    from utils.batch_pipeline.projection import publish_client_completion
    from utils.batch_pipeline import projection_followup
    from utils.sync import reprocess
    import fakeredis

    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    redis = fakeredis.FakeRedis()
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    monkeypatch.setattr(projection_followup, 'FOLLOWUP_TIMEOUT_SECONDS', 2)
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
    # Re-query the actual durable outbox, including ready-but-not-completed rows.
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
