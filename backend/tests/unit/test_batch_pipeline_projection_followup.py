"""Slow post-persist work cannot own assignment; durable receipts own completion."""

import asyncio
from contextlib import contextmanager
from dataclasses import asdict
from config.policy import BatchUnitPolicy, ProjectionPolicy, resolve_batch_policy, resolve_stage_policy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import hashlib
import logging

import pytest

from database.batch_pipeline_projection import ProjectionBlocked, ProjectionReplay, ProjectionStore
from utils.batch_pipeline import projection, projection_followup
from utils.batch_pipeline.contracts import WorkItem, Priority, ProjectionBinding
from utils.batch_pipeline.serving import Serving
from utils.batch_pipeline.scheduler import owner_key as binding_owner_key
from tests.unit.test_batch_pipeline_scheduler import MemoryStore


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['projection', 'privacy', 'unknown_privacy', 'retry'])
async def test_followup_failure_logs_correlate_without_source_or_exception_content(followup, caplog, kind):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    private = 'private-owner@example.test/private-recording-content'
    errors = {
        'projection': ProjectionBlocked(private),
        'privacy': BatchPrivacyBlocked('account_deleted', conversation_id=private),
        'unknown_privacy': BatchPrivacyBlocked(private, conversation_id=private),
        'retry': RuntimeError(private),
    }
    error = errors[kind]
    error.block_reason = private  # An unregistered reason must never enter a log.
    followup.runner.read_persisted = Mock(side_effect=error)
    with caplog.at_level(logging.INFO, logger=projection_followup.__name__):
        await followup.runner.run(private)
    messages = [r.getMessage() for r in caplog.records if r.name == projection_followup.__name__]
    assert len(messages) == 1
    message = messages[0]
    assert f'unit={hashlib.sha256(private.encode()).hexdigest()[:16]}' in message
    assert private not in message and 'private-owner' not in message
    assert ' site=' in message
    assert f'outcome={"retry" if kind == "retry" else "blocked"}' in message
    if kind != 'retry':
        assert 'block_reason=other' in message
    if kind == 'privacy':
        assert 'fence_reason=account_deleted' in message
    if kind == 'unknown_privacy':
        assert 'fence_reason=unknown' in message
    assert not followup.owner_claim
    followup.projector.store.mark_enrichment.assert_not_called()
    followup.projector.complete_content.assert_not_called()


@pytest.mark.asyncio
async def test_followup_timeout_uses_same_private_safe_unit_key(followup, monkeypatch, caplog):
    segment = 'private-recording@example.test'
    followup.runner._run = AsyncMock(side_effect=TimeoutError('private audio URI'))
    with caplog.at_level(logging.WARNING, logger=projection_followup.__name__):
        await followup.runner.run(segment)
    assert f'outcome=timeout unit={hashlib.sha256(segment.encode()).hexdigest()[:16]}' in caplog.text
    assert segment not in caplog.text and 'private audio URI' not in caplog.text
    assert not followup.runner.closed


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
        side_effect=lambda table, sid: SimpleNamespace(
            get=lambda: SimpleNamespace(to_dict=lambda: jobs[sid] if table == 'jobs' else {'projection': receipts[sid]})
        )
    )
    projector.complete_content = Mock()
    runner = projection_followup.ProjectionFollowups(projector)
    from utils.sync import bridge

    monkeypatch.setattr(bridge, 'finish_sync_bridges', lambda _, cid, **kw: cid)
    return SimpleNamespace(**locals())


@pytest.mark.asyncio
@pytest.mark.parametrize('state', ['ready', 'quarantined'])
async def test_terminal_followup_part_performs_no_policy_read_or_write(followup, state):
    f = followup
    f.projector.store.policy.side_effect = AssertionError('terminal receipt performed a policy read')
    item = WorkItem(**{key: value for key, value in f.jobs['head'].items() if key in WorkItem.__dataclass_fields__})
    receipt = {**f.receipts['head'], 'state': state}

    await f.runner.finish_part(item, f.binding, receipt, None)

    f.projector.store.policy.assert_not_called()
    f.projector.store.mark_enrichment.assert_not_called()
    f.projector.store.ready.assert_not_called()
    f.projector.complete_content.assert_not_called()


@pytest.mark.asyncio
async def test_unfinished_followup_part_retains_policy_refusal_before_side_effects(followup):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    f = followup
    f.projector.store.policy.side_effect = BatchPrivacyBlocked('account_deleted')
    item = WorkItem(**{key: value for key, value in f.jobs['head'].items() if key in WorkItem.__dataclass_fields__})

    with pytest.raises(BatchPrivacyBlocked):
        await f.runner.finish_part(item, f.binding, f.receipts['head'], None)

    f.projector.store.policy.assert_called_once_with('head')
    f.projector.store.mark_enrichment.assert_not_called()
    f.projector.store.ready.assert_not_called()
    f.projector.complete_content.assert_not_called()


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
@pytest.mark.parametrize('outcome', [None, 'success', 'silence'])
@pytest.mark.parametrize('enabled', [False, True])
async def test_completion_uses_validated_outcome_and_honors_silence_switch(followup, monkeypatch, outcome, enabled):
    from dataclasses import replace

    f = followup
    monkeypatch.setenv('BATCH_PIPELINE_SILENCE_READ_SKIP_ENABLED', str(enabled).lower())
    f.projector.clock = lambda: 10000
    f.binding = replace(f.binding, native_record=False)
    f.receipts['head'].update(state='ready', enrichment_required=False)
    # The discovery fetch is only a hint; the validated session is authoritative.
    f.projector.store.read.side_effect = lambda sid: (
        f.jobs[sid],
        {'projection': f.receipts[sid], 'result': {'outcome': 'success' if outcome == 'silence' else 'silence'}},
        f.binding,
    )
    f.projector.store.session.side_effect = lambda sid, *_: SimpleNamespace(
        job=f.jobs[sid],
        entry={'projection': f.receipts[sid], **({'result': {'outcome': outcome}} if outcome else {})},
    )
    # Exercise the real completion selector, rather than only asserting a mock call.
    f.projector.complete_content = projection.Projector.complete_content.__get__(f.projector)
    result = {'outcome': 'expected_silence'}
    f.projector.store.complete = Mock(return_value=result)
    f.projector.store.prepare_accounting = Mock(return_value=None)
    f.projector.store.completion_entries = Mock(
        return_value={
            sid: {'result': {'outcome': outcome}, 'projection': {**f.receipts[sid], 'state': 'ready'}}
            for sid in f.binding.segment_ids
        }
    )
    f.projector.store.hold_for_quarantine = Mock()
    f.projector.publish_completion = Mock(return_value=result)

    assert await f.runner._run('head') == ('completed' if enabled and outcome == 'silence' else 'incomplete')
    if enabled and outcome == 'silence':
        f.projector.store.complete.assert_called_once_with(
            'head', f.binding, f.projector.clock(), None, policy=f.projector.store.policy.return_value
        )
        f.projector.store.prepare_accounting.assert_not_called()
        f.projector.publish_completion.assert_called_once()
    else:
        f.projector.store.prepare_accounting.assert_called_once()
        f.projector.store.complete.assert_not_called()
        f.projector.publish_completion.assert_not_called()


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
    f.projector.complete_content.assert_called_once_with('head', f.binding, silence=False)
    f.projector.load_result.assert_not_called()


@pytest.mark.asyncio
async def test_real_claim_released_across_run_blocking_leaves_never_fails_the_task(followup, monkeypatch):
    # The follow-up enters the real advisory claim in one run_blocking leaf and
    # releases it in a later leaf; each leaf runs in its own contextvars copy,
    # so the claim's retry-deadline scope created its ContextVar token in a
    # different Context than the one resetting it. Before the scope learned to
    # tolerate that split, every release raised "Token was created in a
    # different Context" and the background task was reported failed after its
    # work had already committed. The stubbed owner_claim fixture hides this
    # seam, so this test restores the real claim against a fake Redis.
    import fakeredis

    from database import batch_pipeline_projection_claim as claims

    redis = fakeredis.FakeRedis()
    redis.eval('return 1', 0)  # Load the Lua emulator for the token-fenced release.
    monkeypatch.setattr(claims, '_redis_client', lambda: redis)
    monkeypatch.setattr(projection_followup, 'projection_claim', claims.projection_claim)

    f = followup
    await asyncio.wait_for(f.runner.run('head'), 5)
    f.projector.complete_content.assert_called_once_with('head', f.binding, silence=False)
    # The release ran to completion: the advisory lease is gone, not left to its TTL.
    assert not redis.keys('batch_projection:*')


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
        ('bridge', 'head', {'require_python_owner': True}),
        ('playback', 'head'),
        ('bridge', 'head', {'audio_source_id': 'head', 'require_python_owner': True}),
        ('enrichment', 'survivor'),
    ]


@pytest.mark.asyncio
async def test_partial_assignments_do_not_take_slots_and_failed_front_rotates(followup, monkeypatch):
    f = followup
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED', 'false')
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
async def test_finish_page_checks_pinned_sync_policy_before_any_side_effect(followup):
    f = followup
    f.jobs['head']['policy_parts']['projection'] = ProjectionPolicy(async_projection=False).to_dict()
    await f.runner.run('head')
    f.projector.store.mark_enrichment.assert_not_called()
    f.projector.store.ready.assert_not_called()
    f.projector.complete_content.assert_not_called()
    assert not f.owner_claim


@pytest.mark.asyncio
async def test_unchanged_ready_receipt_retries_when_external_sibling_unblocks(followup, monkeypatch):
    # Immediate retry is the kill-switch path; desync retries after a bounded
    # backoff (test_batch_pipeline_followup_desync.py).
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_BACKOFF_SECONDS', '0')
    f = followup
    f.runner.backoff_ceiling, f.runner.seeded = 0, True
    f.receipts['head']['state'] = 'ready'
    f.projector.store.store.projection_pending.return_value = ['head']
    sibling_ready = False
    completed = []

    def complete(segment, binding, *, silence):
        if sibling_ready:
            completed.append(segment)

    f.projector.complete_content.side_effect = complete

    async def pass_once():
        await f.runner.schedule()
        while f.runner.tasks:
            await asyncio.gather(*list(f.runner.tasks.values()))
        await asyncio.sleep(0)

    await pass_once()
    assert not completed
    # Nothing about head's receipt changes: only the external sibling does.
    sibling_ready = True
    await pass_once()
    assert completed == ['head']
    assert f.projector.complete_content.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled,expected_probes', [('true', 1), ('false', 100)])
async def test_ready_backlog_scans_sibling_accounting_once_per_page(followup, monkeypatch, enabled, expected_probes):
    from contextvars import ContextVar
    from dataclasses import replace

    f = followup
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_FOLLOWUP_PAGE_ENABLED', enabled)
    segments = tuple(f'synthetic-{index:03}' for index in range(100))
    binding = replace(f.binding, segment_ids=segments + ('synthetic-blocker',))
    for segment in segments:
        f.jobs[segment] = {**f.jobs['head'], 'segment_id': segment}
        f.receipts[segment] = {**f.receipts['head'], 'state': 'ready', 'speech_seconds': 1}
    f.jobs['synthetic-blocker'] = {**f.jobs['head'], 'segment_id': 'synthetic-blocker'}
    f.receipts['synthetic-blocker'] = {'state': 'persisted'}
    f.projector.store.store.projection_pending.return_value = list(segments)
    f.projector.store.read.side_effect = lambda sid: (f.jobs[sid], {'projection': f.receipts[sid]}, binding)
    f.projector.store.session.side_effect = lambda sid, *_: SimpleNamespace(
        job=f.jobs[sid], entry={'projection': f.receipts[sid]}
    )
    probe_reads = ContextVar('synthetic_accounting_reads', default=None)

    def ref(table, segment):
        def get():
            if probe_reads.get() is not None:
                probe_reads.get().append(table)
            row = f.jobs[segment] if table == 'jobs' else {'projection': f.receipts[segment]}
            return SimpleNamespace(to_dict=lambda: row)

        return SimpleNamespace(get=get)

    f.projector.store.ref.side_effect = ref
    accounting_reads = []

    def complete(segment, binding, *, silence):
        reads = []
        token = probe_reads.set(reads)
        try:
            assert ProjectionStore.prepare_accounting(f.projector.store, binding, 100) is None
            accounting_reads.append(len(reads))
        finally:
            probe_reads.reset(token)

    f.projector.complete_content.side_effect = complete
    await f.runner.schedule()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
    assert len(accounting_reads) == expected_probes
    assert sum(accounting_reads) == 201 * expected_probes


@pytest.mark.asyncio
async def test_ready_probe_failure_does_not_suppress_next_queued_sibling(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    for receipt in f.receipts.values():
        receipt['state'] = 'ready'
    f.projector.complete_content.side_effect = [RuntimeError('synthetic retry'), None]
    await f.runner.schedule()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
    assert f.projector.complete_content.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('next_page', [[], ['head']])
async def test_next_discovery_keeps_running_pages_probe_and_starts_a_fresh_one(followup, monkeypatch, next_page):
    # Pins the full path's same-page interleaving; the claimed-sibling skip has its own tests.
    monkeypatch.setenv('BATCH_PIPELINE_FOLLOWUP_CLAIMED_SIBLING_SKIP_ENABLED', 'false')
    f = followup
    for receipt in f.receipts.values():
        receipt['state'] = 'ready'
    started, release = asyncio.Event(), asyncio.Event()
    finish = f.runner.finish_part

    async def delayed(item, *args, **kwargs):
        if item.segment_id == 'later':
            started.set()
            await release.wait()
        await finish(item, *args, **kwargs)

    f.runner.finish_part = delayed
    try:
        await f.runner.schedule()
        head = f.runner.tasks['head']
        await asyncio.wait_for(started.wait(), 2)
        await head
        await asyncio.sleep(0)
        assert f.projector.complete_content.call_count == 1
        assert 'later' in f.runner.tasks
        f.projector.store.store.projection_pending.return_value = next_page
        await f.runner.schedule()
        if next_page:
            await f.runner.tasks['head']
            await asyncio.sleep(0)
        release.set()
        while f.runner.tasks:
            await asyncio.gather(*list(f.runner.tasks.values()))
        assert f.projector.complete_content.call_count == 1 + bool(next_page)
        assert not f.runner.pages and not f.runner.completion_attempts
    finally:
        release.set()
        while f.runner.tasks:
            await asyncio.gather(*list(f.runner.tasks.values()))


@pytest.mark.asyncio
async def test_owed_row_also_discovered_still_probes_completion(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    for receipt in f.receipts.values():
        receipt['state'] = 'ready'
    await f.runner.schedule(tail=('later',))
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
    assert f.projector.complete_content.call_count == 2
    assert not f.runner.pages and not f.runner.completion_attempts


@pytest.mark.asyncio
async def test_owed_running_row_bypasses_its_existing_pages_probe(followup, monkeypatch):
    # Pins the full path's same-page interleaving; the claimed-sibling skip has its own tests.
    monkeypatch.setenv('BATCH_PIPELINE_FOLLOWUP_CLAIMED_SIBLING_SKIP_ENABLED', 'false')
    f = followup
    for receipt in f.receipts.values():
        receipt['state'] = 'ready'
    started, release = asyncio.Event(), asyncio.Event()
    finish = f.runner.finish_part

    async def delayed(item, *args, **kwargs):
        if item.segment_id == 'later':
            started.set()
            await release.wait()
        await finish(item, *args, **kwargs)

    f.runner.finish_part = delayed
    try:
        await f.runner.schedule()
        head = f.runner.tasks['head']
        await asyncio.wait_for(started.wait(), 2)
        await head
        await asyncio.sleep(0)
        assert f.projector.complete_content.call_count == 1
        f.projector.store.store.projection_pending.return_value = []
        await f.runner.schedule(tail=('later',))
        release.set()
        while f.runner.tasks:
            await asyncio.gather(*list(f.runner.tasks.values()))
        assert f.projector.complete_content.call_count == 2
        assert not f.runner.pages and not f.runner.completion_attempts
    finally:
        release.set()
        while f.runner.tasks:
            await asyncio.gather(*list(f.runner.tasks.values()))


@pytest.mark.asyncio
@pytest.mark.parametrize('wake', ['priority', 'owed'])
async def test_recovery_wake_bypasses_same_page_ready_probe_hint(followup, wake):
    f = followup
    for receipt in f.receipts.values():
        receipt['state'] = 'ready'

    async def drain():
        while f.runner.tasks:
            await asyncio.gather(*list(f.runner.tasks.values()))
        await asyncio.sleep(0)

    await f.runner.schedule()
    await drain()
    assert f.projector.complete_content.call_count == 1
    if wake == 'priority':
        await f.runner.schedule(priority=('later',))
    else:
        f.projector.store.store.projection_pending.return_value = []
        await f.runner.schedule(tail=('later',))
    await drain()
    assert f.projector.complete_content.call_count == 2
    f.projector.complete_content.assert_called_with('later', f.binding, silence=False)


@pytest.mark.asyncio
async def test_owner_only_recovery_clears_stale_page_marker_before_completion_probe(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'projection_followup_page_enabled', lambda: True)
    f.receipts['later']['state'] = 'ready'
    f.runner.pending.append('later')
    f.runner.pages.update({'head': 1, 'later': 1})
    f.runner.completion_attempts.add((1, f.binding))

    await f.runner.schedule(priority=('later',), discover=False)
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))

    assert 'later' not in f.runner.pages
    assert (1, f.binding) in f.runner.completion_attempts
    f.projector.complete_content.assert_called_once_with('later', f.binding, silence=False)


@pytest.mark.asyncio
async def test_ready_completion_probes_do_not_coalesce_different_run_bindings(followup):
    from dataclasses import replace

    f = followup
    for receipt in f.receipts.values():
        receipt['state'] = 'ready'
    later = replace(f.binding, run_token='synthetic-next', run_epoch=2)
    f.projector.store.read.side_effect = lambda sid: (
        f.jobs[sid],
        {'projection': f.receipts[sid]},
        later if sid == 'later' else f.binding,
    )
    await f.runner.schedule()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
    assert f.projector.complete_content.call_count == 2


@pytest.mark.asyncio
async def test_persisted_sibling_unblocks_content_after_ready_probe_in_same_page(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    f.receipts['head']['state'] = 'ready'
    completed = []

    def complete(segment, binding, *, silence):
        if all(receipt['state'] == 'ready' for receipt in f.receipts.values()):
            completed.append(segment)

    f.projector.complete_content.side_effect = complete
    f.projector.store.mark_enrichment.side_effect = lambda sid, *_args, **_kw: f.receipts[sid].update(state='ready')
    await f.runner.schedule()
    while f.runner.tasks:
        await asyncio.gather(*list(f.runner.tasks.values()))
    assert f.projector.complete_content.call_count == 2
    assert completed == ['later']


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
    # Kill-switch path: the timed-out row is rediscovered on the very next pass.
    f.runner.backoff_ceiling, f.runner.seeded = 0, True
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


@pytest.mark.asyncio
async def test_source_deleted_followup_is_terminal_without_backoff_or_content_work(followup):
    f = followup
    f.receipts['head'].update(
        state='ready',
        disposition='source_deleted',
        conversation_id=None,
        audio_required=False,
        enrichment_required=False,
    )
    f.projector.complete_content.return_value = {
        'reason_code': 'source_deleted',
        'new_memories': [],
        'updated_memories': [],
    }
    f.runner.desync = True
    f.runner.backoff['head'] = (float('inf'), 60)
    counter = projection_followup.OUTCOMES.labels('source_deleted')._value.get()
    await f.runner.run('head')
    assert projection_followup.OUTCOMES.labels('source_deleted')._value.get() == counter + 1
    assert 'head' not in f.runner.backoff
    assert 'source_deleted' not in projection_followup.BACKOFF_OUTCOMES
    f.projector.store.mark_enrichment.assert_not_called()
    f.projector.store.ready.assert_not_called()
    f.projector.load_result.assert_not_called()


@pytest.mark.asyncio
async def test_tail_handoff_waits_behind_discovery_and_reaches_complete_content(followup, monkeypatch):
    f = followup
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    for receipt in f.receipts.values():
        receipt['state'] = 'ready'
    f.projector.followups = f.runner
    f.projector.store.store.projection_pending.return_value = ['head']
    f.projector.owe_followups(['later'])
    f.projector.owe_followups(['later'])
    assert f.projector.chain_followups == ['later']
    await f.projector.start_followups()
    while f.runner.tasks:
        await asyncio.wait_for(asyncio.gather(*list(f.runner.tasks.values())), 2)
    assert [call.args[0] for call in f.projector.complete_content.call_args_list] == ['head', 'later']
    assert not f.runner.owed and not f.projector.chain_followups


@pytest.fixture
def ready_followup(followup, monkeypatch):
    from datetime import datetime, timezone

    from database import batch_pipeline_privacy
    from database.batch_pipeline_privacy import PRIVACY_COLLECTION, privacy_owner_key
    from database.batch_privacy_attempt import with_batch_privacy_attempt
    from database.sync_ledger import sync_content_ledger_ref
    from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore, StrictFirestoreDocument

    f = followup
    monkeypatch.setenv('OMI_ENV_STAGE', 'local')
    monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_generation_memo":100}')
    monkeypatch.setattr(batch_pipeline_privacy, 'ttl_disabled', lambda: False)
    monkeypatch.delenv('BATCH_PIPELINE_FOLLOWUP_EARLY_COALESCE_ENABLED', raising=False)
    # These cases pin C1's same-page proof path; the claimed-sibling skip (SCA-3508)
    # runs ahead of it and has its own tests below.
    monkeypatch.setenv('BATCH_PIPELINE_FOLLOWUP_CLAIMED_SIBLING_SKIP_ENABLED', 'false')
    client = StrictFirestore()
    store = ProjectionStore(SimpleNamespace(client=client, namespace='synthetic'))
    f.projector.store = store
    store.policy = Mock(return_value=ProjectionPolicy(async_projection=True))
    store.check = Mock(wraps=store.check)
    client.collection('users').document(f.binding.owner_id).create({'data_protection_level': 'standard'})
    authority = client.collection(PRIVACY_COLLECTION).document(privacy_owner_key(f.binding.owner_id))
    authority.create({'memo_token': '1' * 32, 'memo_schema': 1, 'generation': 0})
    original_get = StrictFirestoreDocument.get

    def read(ref, *args, **kwargs):
        snapshot = original_get(ref, *args, **kwargs)
        if ref.path == authority.path:
            snapshot.update_time = datetime(2026, 11, 19, tzinfo=timezone.utc)
        return snapshot

    monkeypatch.setattr(StrictFirestoreDocument, 'get', read)
    for segment in f.binding.segment_ids:
        # Synthetic older rows sharing a capture anchor. Distinct anchors below
        # demonstrate that binding equality alone cannot cover a sibling.
        job = {
            **f.jobs[segment],
            'capture_at': 1000,
            'projection_binding': asdict(f.binding),
            'privacy_generation': 0,
            'result': {'outcome': 'success'},
        }
        store.ref('jobs', segment).create(job)
        store.ref('results', segment).create(
            {
                'protocol_version': 1,
                'owner_key': binding_owner_key(f.binding.owner_id),
                'segment_id': segment,
                'capture_at': 1000,
                'previous_segment_id': None,
                'result': job['result'],
                'projection_state': 'ready',
                'projection': {'state': 'ready'},
            }
        )
    sync_content_ledger_ref(client, f.binding.owner_id, f.binding.content_id).create(
        {
            'dispatch_protocol': 'batch_v1',
            'status': 'processing',
            'job_id': f.binding.job_id,
            'batch_pipeline': {'protocol_version': 1, 'namespace': 'synthetic', 'segment_ids': ['head', 'later']},
        }
    )
    f.projector.complete_content.return_value = {'outcome': 'success'}
    f.runner.pages.update({'head': 1, 'later': 1})
    f.run = with_batch_privacy_attempt(f.runner._run)
    return f, authority


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case',
    [
        'same_page',
        'different_page',
        'invalidation',
        'distinct_input',
        'distinct_output',
        'kill',
        'targeted',
        'expired',
        'expired_during_read',
    ],
)
async def test_early_followup_checks_fresh_privacy_version_and_covered_conversations(ready_followup, monkeypatch, case):
    f, authority = ready_followup
    store = f.projector.store
    assert await f.run('head') == 'completed'
    assert f.runner.completed_probes[1][f.binding].ids

    if case == 'different_page':
        f.runner.pages['later'] = 2
    elif case == 'invalidation':
        store.client.rows[authority.path]['memo_token'] = '2' * 32
        store.client.collection('account_deletions').document(f.binding.owner_id).create({'wipe_status': 'pending'})
    elif case == 'distinct_input':
        store.client.rows[store.ref('jobs', 'later').path]['capture_at'] = 1001
        store.client.rows[store.ref('results', 'later').path]['capture_at'] = 1001
    elif case == 'distinct_output':
        store.client.rows[store.ref('jobs', 'later').path]['conversation_ids'] = ['unverified-output']
        store.client.rows[store.ref('results', 'later').path]['projection']['conversation_id'] = 'unverified-output'
    elif case == 'kill':
        monkeypatch.setenv('BATCH_PIPELINE_FOLLOWUP_EARLY_COALESCE_ENABLED', 'false')
    elif case == 'targeted':
        f.runner.forget_page('later')
    elif case in {'expired', 'expired_during_read'}:
        expiry = f.runner.completed_probes[1][f.binding].expires_at
        times = [expiry] if case == 'expired' else [expiry - 0.5, expiry]
        monkeypatch.setattr(projection_followup, 'time', SimpleNamespace(monotonic=Mock(side_effect=times)))

    result = await f.run('later')
    assert store.check.call_count == (1 if case == 'same_page' else 2)
    assert result == (
        'blocked' if case == 'invalidation' else 'completed' if case in {'targeted', 'different_page'} else 'coalesced'
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case', ['missing', 'error', 'refusal', 'first_walk_refusal', 'no_proof', 'memo_only', 'token_error', 'inflight']
)
async def test_early_followup_falls_back_when_first_probe_is_unproven(ready_followup, monkeypatch, case):
    from database.batch_pipeline_privacy import BatchPrivacyBlocked

    f, authority = ready_followup
    store = f.projector.store
    if case == 'inflight':
        f.runner.completion_attempts.add((1, f.binding))
    elif case == 'missing':
        f.projector.complete_content.side_effect = [None, {'outcome': 'success'}]
        assert await f.run('head') == 'incomplete'
    elif case == 'error':
        f.projector.complete_content.side_effect = [RuntimeError('synthetic'), {'outcome': 'success'}]
        assert await f.run('head') == 'retry'
    elif case == 'refusal':
        f.projector.complete_content.side_effect = [
            BatchPrivacyBlocked('account_deleted'),
            {'outcome': 'success'},
        ]
        assert await f.run('head') == 'blocked'
    elif case == 'first_walk_refusal':
        store.client.collection('account_deletions').document(f.binding.owner_id).create({'wipe_status': 'pending'})
        assert await f.run('head') == 'blocked'
    elif case == 'no_proof':
        store.client.rows[authority.path]['memo_schema'] = 0
        assert await f.run('head') == 'completed'
    elif case == 'memo_only':
        from database import batch_pipeline_privacy
        from database.batch_privacy_attempt import batch_privacy_attempt

        monkeypatch.setenv('FIRESTORE_READ_LEVERS', '{"bpp_generation_memo":100,"bpp_owner_memo_enforce":100}')
        monkeypatch.setattr(batch_pipeline_privacy, 'PROCESS_OWNERS', batch_pipeline_privacy.BoundedTTLCache())
        with batch_privacy_attempt(), pytest.raises(ProjectionReplay):
            store.check(store.session('head', f.binding, 1000))
        assert await f.run('head') == 'completed'
        assert not f.runner.completed_probes
    else:
        assert await f.run('head') == 'completed'
        from database import batch_pipeline_privacy

        original = batch_pipeline_privacy.metrics.read_snapshot

        def read_snapshot(family, reference, **kwargs):
            if 'transaction' not in kwargs:
                raise RuntimeError('synthetic')
            return original(family, reference, **kwargs)

        monkeypatch.setattr(batch_pipeline_privacy.metrics, 'read_snapshot', read_snapshot)
    before = store.check.call_count
    await f.run('later')
    assert store.check.call_count == before + 1


@pytest.mark.asyncio
async def test_failed_first_claim_release_does_not_publish_proof(ready_followup, monkeypatch):
    f, _ = ready_followup
    previous_claim = projection_followup.projection_claim

    @contextmanager
    def failed_release(*_):
        yield True
        raise RuntimeError('synthetic release failure')

    monkeypatch.setattr(projection_followup, 'projection_claim', failed_release)
    with pytest.raises(RuntimeError, match='release failure'):
        await f.run('head')
    assert not f.runner.completed_probes
    monkeypatch.setattr(projection_followup, 'projection_claim', previous_claim)
    assert await f.run('later') == 'coalesced'
    assert f.projector.store.check.call_count == 2


# --- claimed-sibling skip (SCA-3508) -------------------------------------------------------------
# A ready sibling may coalesce behind its same-page claimant only on the claimant's
# live privacy proof, verified exactly as C1 verifies a completed proof.

SKIP = 'BATCH_PIPELINE_FOLLOWUP_CLAIMED_SIBLING_SKIP_ENABLED'


def _skips():
    return projection_followup.OUTCOMES.labels('claimed_sibling_skipped')._value.get()


def _requeues():
    return projection_followup.OUTCOMES.labels('claimed_sibling_requeued')._value.get()


async def _claimant_holding_completion(f, *, fail=False):
    """Start head and hold it inside complete_content once its proof is published."""
    import threading

    release = threading.Event()

    def complete(*_args, **_kwargs):
        assert release.wait(10)
        if fail:
            raise RuntimeError('synthetic completion failure')
        return {'outcome': 'success'}

    f.projector.complete_content.side_effect = complete
    head = asyncio.create_task(f.run('head'))
    for _ in range(500):
        claim = f.runner.sibling_claims.get((1, f.binding))
        if claim is not None and claim.ready.is_set():
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError('claimant never published its proof')
    return head, release


@pytest.mark.asyncio
async def test_ready_sibling_coalesces_on_the_claimants_live_privacy_proof(ready_followup, monkeypatch):
    f, _authority = ready_followup
    monkeypatch.setenv(SKIP, 'true')
    store = f.projector.store
    before = _skips()
    head, release = await _claimant_holding_completion(f)
    assert f.runner.sibling_claims[(1, f.binding)].proof is not None

    assert await f.run('later') == 'coalesced'
    assert store.check.call_count == 1  # only the claimant paid the session check
    assert _skips() == before + 1

    release.set()
    assert await head == 'completed'
    assert not f.runner.sibling_claims


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'case', ['uncovered_input', 'uncovered_output', 'privacy_changed', 'switch_off', 'page_cleared']
)
async def test_sibling_takes_its_own_privacy_check_unless_the_proof_covers_it(ready_followup, monkeypatch, case):
    """Panel F1: a sibling-only privacy change must never be skipped."""
    f, authority = ready_followup
    monkeypatch.setenv(SKIP, 'false' if case == 'switch_off' else 'true')
    store = f.projector.store
    before = _skips()
    if case == 'switch_off':
        # Concurrent siblings with the switch off: C1 refuses an in-flight probe,
        # so the sibling pays its own check (today's behaviour).
        import threading

        release = threading.Event()
        f.projector.complete_content.side_effect = lambda *_a, **_k: release.wait(10) and {'outcome': 'success'}
        head = asyncio.create_task(f.run('head'))
        for _ in range(500):
            if (1, f.binding) in f.runner.completion_attempts:
                break
            await asyncio.sleep(0.01)
        await f.run('later')
        release.set()
        await head
        assert store.check.call_count == 2
        assert _skips() == before and not f.runner.sibling_claims
        return
    head, release = await _claimant_holding_completion(f)
    if case == 'uncovered_input':
        store.client.rows[store.ref('jobs', 'later').path]['capture_at'] = 1001
        store.client.rows[store.ref('results', 'later').path]['capture_at'] = 1001
    elif case == 'uncovered_output':
        store.client.rows[store.ref('jobs', 'later').path]['conversation_ids'] = ['unverified-output']
        store.client.rows[store.ref('results', 'later').path]['projection']['conversation_id'] = 'unverified-output'
    elif case == 'privacy_changed':
        store.client.rows[authority.path]['memo_token'] = '2' * 32
        store.client.collection('account_deletions').document(f.binding.owner_id).create({'wipe_status': 'pending'})
    elif case == 'page_cleared':
        f.runner.forget_page('later')
        release.set()  # this run reaches its own completion attempt; don't make it wait

    result = await f.run('later')
    release.set()
    await head
    assert _skips() == before
    assert store.check.call_count == 2  # the sibling paid its own session and privacy check
    if case == 'privacy_changed':
        assert result == 'blocked'


@pytest.mark.asyncio
async def test_sibling_skipped_behind_a_failed_claimant_is_requeued(ready_followup, monkeypatch):
    f, _authority = ready_followup
    monkeypatch.setenv(SKIP, 'true')
    before = _requeues()
    head, release = await _claimant_holding_completion(f, fail=True)
    assert await f.run('later') == 'coalesced'
    release.set()
    assert await head == 'retry'
    # The claimant's attempt failed (key discarded): the skipped sibling runs again.
    assert f.runner.pending[0] == 'later'
    assert 'later' in f.runner.prioritized
    assert _requeues() == before + 1
    assert not f.runner.sibling_claims


@pytest.mark.asyncio
async def test_still_running_skipped_sibling_is_requeued_when_it_finishes(followup):
    f = followup
    claim = projection_followup.SiblingClaim(waiting=['synthetic-sibling'])
    f.runner.tasks['synthetic-sibling'] = object()
    f.runner.sibling_claims[(1, f.binding)] = claim
    before = _requeues()

    f.runner.release_sibling_claim((1, f.binding))
    assert claim.ready.is_set()
    assert 'synthetic-sibling' not in f.runner.pending
    assert _requeues() == before

    f.runner.launch = lambda: None
    f.runner.finished('synthetic-sibling', SimpleNamespace(cancelled=lambda: False))
    assert f.runner.pending[0] == 'synthetic-sibling'
    assert _requeues() == before + 1


def test_released_claim_after_a_completion_attempt_requeues_nothing(followup):
    f = followup
    f.runner.completion_attempts.add((1, f.binding))
    f.runner.sibling_claims[(1, f.binding)] = projection_followup.SiblingClaim(waiting=['x'], attempted=True)
    before = _requeues()
    f.runner.release_sibling_claim((1, f.binding))
    assert not f.runner.pending and _requeues() == before


@pytest.mark.parametrize(
    'hints',
    [
        None,
        ({'policy_parts': {}}, {'projection': {'state': 'ready'}}, 'binding'),
        (
            {'policy_parts': {'projection': ProjectionPolicy(async_projection=False).to_dict()}},
            {'projection': {'state': 'ready'}},
            'b',
        ),
        (
            {'policy_parts': {'projection': ProjectionPolicy(async_projection=True).to_dict()}},
            {'projection': {'state': 'ready'}, 'projection_parts': {'0': {'state': 'persisted'}}},
            'b',
        ),
        (
            {'policy_parts': {'projection': ProjectionPolicy(async_projection=True).to_dict()}},
            {'projection': {'state': 'ready'}},
            ['unhashable'],
        ),
    ],
)
def test_ready_sibling_key_refuses_anything_the_legacy_path_would_not_coalesce(hints):
    assert projection_followup.ProjectionFollowups.ready_sibling_key(3, hints) is None


def test_ready_sibling_key_matches_the_legacy_coalesce_key():
    hints = (
        {'policy_parts': {'projection': ProjectionPolicy(async_projection=True).to_dict()}},
        {'projection': {'state': 'ready'}, 'projection_parts': {'0': {'state': 'ready'}}},
        'b',
    )
    assert projection_followup.ProjectionFollowups.ready_sibling_key(3, hints) == (3, 'b')


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['claimant_refused_before_proof', 'proof_wait_timeout'])
async def test_sibling_without_a_published_proof_pays_its_own_privacy_check(ready_followup, monkeypatch, case):
    """Confirmation panel F1: the no-proof and timeout branches never coalesce unverified."""
    f, _authority = ready_followup
    monkeypatch.setenv(SKIP, 'true')
    store = f.projector.store
    claim = projection_followup.SiblingClaim()
    if case == 'claimant_refused_before_proof':
        claim.ready.set()  # claimant ended without publishing a proof
    else:
        monkeypatch.setattr(projection_followup, 'CLAIM_PROOF_WAIT_SECONDS', 0.05)
    f.runner.sibling_claims[(1, f.binding)] = claim
    store.client.collection('account_deletions').document(f.binding.owner_id).create({'wipe_status': 'pending'})
    before = _skips()

    assert await f.run('later') == 'blocked'
    assert store.check.call_count == 1  # the sibling's own session and privacy check
    assert _skips() == before
    assert not claim.waiting


def test_release_requeues_unless_the_claimant_itself_attempted_completion(followup):
    """Confirmation panel F2: a foreign in-flight attempt must not suppress the re-queue."""
    f = followup
    f.runner.completion_attempts.add((1, f.binding))
    claim = projection_followup.SiblingClaim(waiting=['x'])
    f.runner.sibling_claims[(1, f.binding)] = claim
    before = _requeues()
    f.runner.release_sibling_claim((1, f.binding))
    assert f.runner.pending[0] == 'x' and _requeues() == before + 1


@pytest.mark.asyncio
async def test_failed_claimant_does_not_duplicate_a_queued_targeted_recovery(followup, monkeypatch):
    """lead2 custody review: a re-queue must not race a targeted wake into two tasks."""
    f = followup
    runner = f.runner
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 1)
    started = []

    class Task:
        def __init__(self, segment):
            self.segment, self.callbacks = segment, []

        def add_done_callback(self, cb):
            self.callbacks.append(cb)

    def start(coro, name=None):
        coro.close()
        task = Task(started[-1] if started else None)
        return task

    def run(segment):
        started.append(segment)

        async def noop():
            return None

        return noop()

    monkeypatch.setattr(projection_followup, 'start_background_task', start)
    monkeypatch.setattr(runner, 'run', run)
    runner.tasks['busy'] = object()  # the only slot is taken
    await runner.schedule(['later'], discover=False)
    assert list(runner.targeted_pending) == ['later'] and not started

    # The claimant fails before its completion attempt; the sibling already skipped.
    runner.sibling_claims[(1, f.binding)] = projection_followup.SiblingClaim(waiting=['later'])
    runner.release_sibling_claim((1, f.binding))
    assert 'later' not in runner.pending

    runner.tasks.pop('busy')
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 4)
    runner.launch()
    assert started == ['later']
    assert list(runner.tasks) == ['later'] and not runner.pending and not runner.targeted_pending


def test_ordinary_launch_never_overwrites_a_running_segment(followup, monkeypatch):
    f = followup
    runner = f.runner
    monkeypatch.setattr(projection_followup, 'MAX_FOLLOWUPS', 4)
    owner = object()
    runner.tasks['later'] = owner
    runner.pending.append('later')
    runner.prioritized.add('later')
    monkeypatch.setattr(projection_followup, 'start_background_task', lambda *a, **k: pytest.fail('duplicate launch'))
    runner.launch()
    assert runner.tasks['later'] is owner and not runner.pending and 'later' not in runner.prioritized


@pytest.mark.asyncio
@pytest.mark.parametrize('case', ['released_after_attempt', 'released_without_attempt', 'page_cleared_during_check'])
async def test_claim_state_changes_during_the_proof_check(ready_followup, monkeypatch, case):
    """Exact-head panel F1: pin the non-live coalesce branch and the post-await page re-checks."""
    f, _authority = ready_followup
    monkeypatch.setenv(SKIP, 'true')
    key = (1, f.binding)
    head, release = await _claimant_holding_completion(f)
    original = f.runner.read_persisted

    def read_persisted(segment, *, prior=None, hints=None):
        result = original(segment, prior=prior, hints=hints)
        if segment == 'later' and prior:
            if case == 'released_after_attempt':
                f.runner.sibling_claims.pop(key)  # claimant released; its attempt stays registered
            elif case == 'released_without_attempt':
                f.runner.sibling_claims.pop(key)
                f.runner.completion_attempts.discard(key)
            else:
                f.runner.pages.pop('later')
            if case != 'released_after_attempt':
                release.set()  # this sibling reaches its own completion; don't make it wait
        return result

    monkeypatch.setattr(f.runner, 'read_persisted', read_persisted)
    before = _skips()
    result = await f.run('later')
    release.set()
    await head
    if case == 'released_after_attempt':
        assert result == 'coalesced' and _skips() == before + 1
    else:
        assert _skips() == before


def test_cancelled_task_does_not_count_a_dropped_requeue(followup):
    """Exact-head panel F2: shutdown drops the queue, so it must not count a requeue."""
    f = followup
    f.runner.sibling_requeue.add('x')
    before = _requeues()
    f.runner.finished('x', SimpleNamespace(cancelled=lambda: True))
    assert _requeues() == before and not f.runner.pending and f.runner.closed
