"""Slow post-persist work cannot own assignment; durable receipts own completion."""

import asyncio
from contextlib import contextmanager
from dataclasses import asdict
from config.policy import BatchUnitPolicy, ProjectionPolicy, resolve_batch_policy, resolve_stage_policy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay
from utils.batch_pipeline import projection, projection_followup
from utils.batch_pipeline.contracts import WorkItem, Priority, ProjectionBinding
from utils.batch_pipeline.serving import Serving
from tests.unit.test_batch_pipeline_scheduler import MemoryStore


@pytest.fixture
def owner_claim(monkeypatch):
    held = set()

    @contextmanager
    def claim(namespace, key):
        if (namespace, key) in held:
            yield False
        else:
            held.add((namespace, key))
            try:
                yield True
            finally:
                held.remove((namespace, key))

    monkeypatch.setattr(projection, 'projection_claim', claim)
    monkeypatch.setattr(projection_followup, 'projection_claim', claim)
    return held


@pytest.mark.parametrize('enabled', [False, True])
def test_owner_claim_covers_assignment_but_not_slow_followup_when_enabled(monkeypatch, owner_claim, enabled):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_CONTENTION_ENABLED', 'true')
    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', str(enabled).lower())
    projector = projection.Projector(Mock(namespace='synthetic'), Mock())
    binding = ProjectionBinding('owner', 'job', 'content', ('head', 'later'))
    projector.store.read = Mock(
        return_value=(
            {'policy_parts': {'projection': resolve_stage_policy('owner', 'projection').to_dict()}},
            {},
            binding,
        )
    )
    projector._assign = Mock(side_effect=lambda *a, **k: assert_claim())

    def assert_claim():
        assert owner_claim

    def slow_followup(*_):
        if enabled:
            assert not owner_claim
            projector.persist('later')
        else:
            assert owner_claim
            with pytest.raises(ProjectionBlocked, match='claim busy'):
                projector.persist('later')
        return {'outcome': 'success'}

    projector._finish = slow_followup
    assert projector.project('head') == {'outcome': 'success'}
    assert projector._assign.call_count == (2 if enabled else 1)
    assert not owner_claim


@pytest.fixture
def followup(monkeypatch, owner_claim):
    projector = projection.Projector(Mock(namespace='synthetic'), Mock())
    binding = ProjectionBinding('owner', 'job', 'content', ('head', 'later'), native_record=True)
    jobs = {
        sid: {
            **asdict(WorkItem(sid, 'owner', i, 'gs://synthetic/audio', 1, Priority.DEEP)),
            'policy_parts': {'projection': ProjectionPolicy(async_projection=True).to_dict()},
        }
        for i, sid in enumerate(binding.segment_ids)
    }
    receipts = {
        sid: {
            'state': 'persisted',
            'conversation_id': sid,
            'enrichment_required': True,
            'language': 'en',
            'audio_required': False,
        }
        for sid in jobs
    }
    projector.store.policy = Mock(return_value=ProjectionPolicy(async_projection=True))
    projector.store.mark_enrichment = Mock()
    projector.store.ready = Mock()
    projector.store.read = Mock(side_effect=lambda sid: (jobs[sid], {'projection': receipts[sid]}, binding))
    projector.store.session = Mock(
        side_effect=lambda sid, *_: SimpleNamespace(job=jobs[sid], entry={'projection': receipts[sid]})
    )
    projector.store.check = Mock(side_effect=ProjectionReplay({'state': 'persisted'}))
    projector.store.store.projection_pending = Mock(return_value=list(jobs))
    projector.store.store.projection_page = Mock(
        side_effect=lambda **kw: (projector.store.store.projection_pending(), None)
    )
    projector.store.ref = Mock(
        side_effect=lambda _, sid: SimpleNamespace(
            get=lambda: SimpleNamespace(to_dict=lambda: {'projection': receipts[sid]})
        )
    )
    projector.complete_content = Mock()
    runner = projection_followup.ProjectionFollowups(projector)
    from utils.sync import bridge

    monkeypatch.setattr(bridge, 'finish_sync_bridges', lambda _, cid, **kw: cid)
    return SimpleNamespace(**locals())


@pytest.mark.asyncio
async def test_slow_enrichment_does_not_block_later_followup_or_next_serving_pass(followup, monkeypatch):
    f = followup
    started, release, later_done = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real = projection_followup.run_blocking

    async def blocking(executor, fn, *args, **kwargs):
        if fn is f.projector.store.mark_enrichment:
            if args[0] == 'head':
                started.set()
                await release.wait()
            f.receipts[args[0]]['state'] = 'ready'
            if args[0] == 'later':
                later_done.set()
            return
        return await real(executor, fn, *args, **kwargs)

    monkeypatch.setattr(projection_followup, 'run_blocking', blocking)
    await f.runner.schedule()
    await asyncio.wait_for(started.wait(), 2)
    await asyncio.wait_for(later_done.wait(), 2)
    # The sibling is ready, but accounting/completion still sees the slow head.
    assert f.receipts['head']['state'] == 'persisted'
    assert f.receipts['later']['state'] == 'ready'
    assert not any(key[0] == 'synthetic' for key in f.owner_claim)
    monkeypatch.setenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', 'true')
    service = Serving(MemoryStore(), projector=f.projector)
    f.projector.start_followups = AsyncMock()
    await asyncio.wait_for(service.reconcile_async(), 2)
    f.projector.store.store.projection_pending.assert_called()
    f.projector.start_followups.assert_awaited_once()
    release.set()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
    await asyncio.sleep(0)
    assert not f.runner.tasks
    assert f.receipts['head']['state'] == 'ready'


@pytest.mark.asyncio
async def test_failed_followup_stays_durable_and_resumes_with_same_receipt(followup):
    f = followup
    f.projector.store.mark_enrichment.side_effect = RuntimeError('synthetic interrupted enqueue')
    await f.runner.run('head')
    assert f.receipts['head']['state'] == 'persisted'
    f.projector.complete_content.assert_not_called()
    f.projector.store.mark_enrichment.side_effect = None
    await f.runner.run('head')
    assert f.projector.store.mark_enrichment.call_count == 2
    f.projector.complete_content.assert_called_once_with('head', f.binding)
    f.projector.load_result.assert_not_called()


@pytest.mark.asyncio
async def test_privacy_fence_prevents_every_followup_effect(followup):
    f = followup
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    f.projector.store.check.side_effect = BatchPrivacyBlocked('synthetic deletion')
    await f.runner.run('head')
    f.projector.store.mark_enrichment.assert_not_called()
    f.projector.complete_content.assert_not_called()


@pytest.mark.asyncio
async def test_followups_are_bounded_and_duplicate_sweeps_coalesce(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    release = asyncio.Event()
    f.runner.run = AsyncMock()

    async def wait(_):
        await release.wait()

    f.runner.run.side_effect = wait
    await f.runner.schedule()
    await f.runner.schedule()
    assert list(f.runner.tasks) == ['head']
    release.set()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))


@pytest.mark.asyncio
async def test_async_flag_off_preserves_synchronous_serving_without_followup_task(monkeypatch):
    monkeypatch.delenv('BATCH_PIPELINE_ASYNC_PROJECTION_ENABLED', raising=False)
    projector = Mock(has_async_followups=False)
    projector.start_followups = AsyncMock(side_effect=AssertionError('dark async task launched'))
    await Serving(MemoryStore(), projector=projector).reconcile_async()
    projector.sweep.assert_called_once()
    projector.start_followups.assert_not_called()


@pytest.mark.asyncio
async def test_private_playback_follows_concurrent_bridge_before_enrichment(followup, monkeypatch):
    from dataclasses import replace
    from utils.sync import bridge

    f = followup
    binding = replace(f.binding, native_record=False, private_cloud_sync_enabled=True)
    receipt = {**f.receipts['head'], 'audio_required': True}
    calls = []

    def finish(owner, cid, **kwargs):
        calls.append(('bridge', cid, kwargs))
        return 'survivor' if kwargs.get('audio_source_id') else 'head'

    monkeypatch.setattr(bridge, 'finish_sync_bridges', finish)
    f.projector.playback = lambda _, cid: calls.append(('playback', cid))
    f.projector.store.mark_enrichment.side_effect = lambda *args, **kwargs: calls.append(('enrichment', args[3]))
    await f.runner.finish_part(
        WorkItem(**{k: v for k, v in f.jobs['head'].items() if k in WorkItem.__dataclass_fields__}),
        binding,
        receipt,
        None,
    )
    assert calls == [
        ('bridge', 'head', {}),
        ('playback', 'head'),
        ('bridge', 'head', {'audio_source_id': 'head'}),
        ('enrichment', 'survivor'),
    ]


@pytest.mark.asyncio
async def test_partial_assignments_do_not_take_slots_and_failed_front_rotates(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    f.projector.store.store.projection_pending.return_value = ['partial', 'head', 'later']
    f.projector.store.ref.side_effect = lambda _, sid: SimpleNamespace(
        get=lambda: SimpleNamespace(to_dict=lambda: {} if sid == 'partial' else {'projection': f.receipts[sid]})
    )
    f.runner.run = AsyncMock()
    await f.runner.schedule()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
    assert [call.args[0] for call in f.runner.run.await_args_list] == ['head', 'later']


@pytest.mark.asyncio
async def test_shutdown_cancellation_does_not_launch_remaining_outbox_wakeups(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    started = asyncio.Event()

    async def wait(_):
        started.set()
        await asyncio.Event().wait()

    f.runner.run = AsyncMock(side_effect=wait)
    await f.runner.schedule()
    await started.wait()
    tasks = list(f.runner.tasks.values())
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.sleep(0)
    assert not f.runner.tasks and not f.runner.pending
    assert f.runner.run.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('phase', ['bridge', 'playback', 'enrichment', 'complete'])
async def test_followup_deadline_cancels_stuck_step_refills_and_retries_same_receipt(followup, monkeypatch, phase):
    from dataclasses import replace
    from utils.sync import bridge

    f = followup
    f.binding = replace(f.binding, native_record=False)
    f.projector.store.read.side_effect = lambda sid: (f.jobs[sid], {'projection': f.receipts[sid]}, f.binding)
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    # Leave enough startup headroom for executor-backed claim/read phases to
    # reach the deliberately stalled step under xdist contention.
    monkeypatch.setattr(projection_followup, 'FOLLOWUP_TIMEOUT_SECONDS', 2)
    f.receipts['head']['audio_required'] = True
    f.projector.playback = Mock()
    target = {
        'bridge': bridge.finish_sync_bridges,
        'playback': f.projector.playback,
        'enrichment': f.projector.store.mark_enrichment,
        'complete': f.projector.complete_content,
    }[phase]
    real = projection_followup.run_blocking
    cancelled = asyncio.Event()
    stalled_started = asyncio.Event()
    stalled = True

    async def blocking(executor, fn, *args, **kwargs):
        nonlocal stalled
        is_head = args and (args[0] == 'head' or getattr(args[0], 'segment_id', None) == 'head')
        is_head = is_head or (phase == 'bridge' and len(args) > 1 and args[1] == 'head')
        if stalled and fn is target and is_head:
            stalled = False
            stalled_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()
        return await real(executor, fn, *args, **kwargs)

    monkeypatch.setattr(projection_followup, 'run_blocking', blocking)
    await f.runner.schedule()
    await asyncio.wait_for(stalled_started.wait(), 3)

    async def drain():
        while f.runner.tasks:
            await asyncio.gather(*list(f.runner.tasks.values()))
        await asyncio.sleep(0)

    await asyncio.wait_for(drain(), 3)
    assert cancelled.is_set()
    assert not f.runner.closed
    assert not f.owner_claim
    assert [call.args[0] for call in f.projector.complete_content.call_args_list] == ['later']
    # Timeout did not settle or remove the receipt. A subsequent sweep retries
    # the same segment, without reloading STT or inventing another assignment.
    assert f.receipts['head']['state'] == 'persisted'
    f.projector.store.store.projection_pending.return_value = ['head']
    await f.runner.schedule()
    await asyncio.wait_for(drain(), 2)
    assert [call.args[0] for call in f.projector.complete_content.call_args_list] == ['later', 'head']
    f.projector.load_result.assert_not_called()


@pytest.mark.asyncio
async def test_followup_claim_release_is_also_bounded(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'CLAIM_RELEASE_TIMEOUT_SECONDS', 0.02)
    real = projection_followup.run_blocking

    async def blocking(executor, fn, *args, **kwargs):
        if getattr(fn, '__name__', '') == '__exit__':
            try:
                await asyncio.Event().wait()
            finally:
                # Model a release which eventually runs after the caller gave up.
                fn(*args, **kwargs)
        return await real(executor, fn, *args, **kwargs)

    monkeypatch.setattr(projection_followup, 'run_blocking', blocking)
    await asyncio.wait_for(f.runner.run('head'), 1)
    assert not f.owner_claim


@pytest.mark.asyncio
async def test_four_stuck_followups_timeout_without_closing_process_drain(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'FOLLOWUP_TIMEOUT_SECONDS', 0.02)
    segments = ['stuck-1', 'stuck-2', 'stuck-3', 'stuck-4', 'next']
    f.runner.candidates = Mock(return_value=segments)
    cancelled = []
    completed = []

    async def work(sid):
        if sid != 'next':
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.append(sid)
        else:
            completed.append(sid)

    f.runner._run = work
    await f.runner.schedule()
    assert len(f.runner.tasks) == 4

    async def drain():
        while f.runner.tasks:
            await asyncio.gather(*list(f.runner.tasks.values()))
        await asyncio.sleep(0)

    await asyncio.wait_for(drain(), 1)
    assert set(cancelled) == set(segments[:4])
    assert completed == ['next']
    assert not f.runner.closed
    f.runner._run = AsyncMock()
    await f.runner.schedule()
    await asyncio.wait_for(drain(), 1)
    assert {call.args[0] for call in f.runner._run.await_args_list} == set(segments)


@pytest.mark.asyncio
@pytest.mark.parametrize('after_playback', [False, True])
async def test_deleted_bridge_keeps_existing_supersession_contract(followup, monkeypatch, after_playback):
    from dataclasses import replace
    from utils.sync import bridge
    from utils.sync.assignment_errors import SyncAssignmentSuperseded

    f = followup
    binding = replace(f.binding, native_record=False, private_cloud_sync_enabled=True)
    receipt = {**f.receipts['head'], 'audio_required': True}
    failure = SyncAssignmentSuperseded('deleted fixture target')
    finish = Mock(side_effect=['head', failure] if after_playback else failure)
    monkeypatch.setattr(bridge, 'finish_sync_bridges', finish)
    f.projector.playback = Mock()
    with pytest.raises(SyncAssignmentSuperseded):
        await f.runner.finish_part(
            WorkItem(**{k: v for k, v in f.jobs['head'].items() if k in WorkItem.__dataclass_fields__}),
            binding,
            receipt,
            None,
        )
    assert f.projector.playback.call_count == int(after_playback)
    f.projector.store.mark_enrichment.assert_not_called()
    f.projector.store.ready.assert_not_called()


@pytest.mark.asyncio
async def test_slow_followup_keeps_unlaunched_page_before_advancing(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    release = asyncio.Event()
    launched = []
    f.runner.candidates = Mock(side_effect=[['head', 'later'], ['next-page']])

    async def run(sid):
        launched.append(sid)
        await release.wait()

    f.runner.run = run
    await f.runner.schedule()
    await asyncio.sleep(0)
    await f.runner.schedule()
    assert launched == ['head']
    assert list(f.runner.pending) == ['later']
    f.runner.candidates.assert_called_once()
    release.set()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
        await asyncio.sleep(0)
    assert launched == ['head', 'later']
    await f.runner.schedule()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
        await asyncio.sleep(0)
    assert launched == ['head', 'later', 'next-page']


@pytest.mark.asyncio
async def test_split_rollover_followup_stores_playback_for_every_part(followup):
    from dataclasses import replace

    f = followup
    binding = replace(f.binding, native_record=False, record_origin=True, private_cloud_sync_enabled=True)
    receipt = {
        **f.receipts['head'],
        'audio_required': True,
        'size_rollover_outputs': [{'conversation_id': cid, 'created': True} for cid in ['head', 'extra']],
    }
    calls = []
    f.projector.playback = lambda _, cid: calls.append(('playback', cid))
    f.projector.store.mark_enrichment.side_effect = lambda *args, **kwargs: calls.append(('enrich', args[3]))
    await f.runner.finish_part(
        WorkItem(**{k: v for k, v in f.jobs['head'].items() if k in WorkItem.__dataclass_fields__}),
        binding,
        receipt,
        None,
    )
    assert calls == [('playback', 'head'), ('playback', 'extra'), ('enrich', 'head')]
