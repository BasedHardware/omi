"""Recovery requests own publication; periodic reconciliation owns global work."""

import asyncio
from contextlib import contextmanager
import time
from unittest.mock import AsyncMock, Mock

import pytest

from config.policy.kill_switches import KILL_SWITCHES
from config.policy import ProjectionPolicy
from tests.unit.test_batch_pipeline_merge_head_wait import admitted
from tests.unit.test_batch_pipeline_recovered_release import recovered
from tests.unit.test_batch_pipeline_owner_chain_projection import BURST, ResultLog, chain, projector_for
from tests.unit.test_batch_pipeline_scheduler import MemoryStore
from utils.batch_pipeline import projection, projection_followup
from utils.batch_pipeline.serving import Serving

SWITCH = 'BATCH_PIPELINE_RECOVERY_OWNER_ONLY_ENABLED'


@pytest.fixture(autouse=True)
def recovery_scope(monkeypatch):
    monkeypatch.delenv(SWITCH, raising=False)

    @contextmanager
    def claim(*_):
        yield True

    monkeypatch.setattr(projection, 'projection_claim', claim)
    monkeypatch.setattr(projection_followup, 'projection_claim', claim)


@pytest.mark.asyncio
@pytest.mark.parametrize('enabled', [True, False])
async def test_recovery_scope_skips_all_global_work_and_kill_switch_restores_it(monkeypatch, enabled):
    assert KILL_SWITCHES[SWITCH] is True
    if not enabled:
        monkeypatch.setenv(SWITCH, 'false')
    projector = Mock(has_async_followups=True)
    projector.project_owner.return_value = ['recovered']
    projector.start_followups = AsyncMock()
    projector.owes_drains = True
    projector.start_drains = Mock()
    service = Serving(MemoryStore(), projector=projector, metrics=Mock(), leader=Mock())
    service._maintain = Mock()
    service.drain_owner = Mock()
    service.merge.held_owners.add('unrelated-owner')
    await service.reconcile_async(owner_id=BURST, recovered='recovered', owner_only=True)
    service.drain_owner.assert_any_call(BURST, recovered='recovered')
    projector.project_owner.assert_called_once_with(BURST, recovered='recovered')
    if enabled:
        service._maintain.assert_not_called()
        service.leader.acquire.assert_not_called()
        projector.sweep.assert_not_called()
        service.metrics.refresh.assert_not_called()
        assert service.drain_owner.call_count == 1
        projector.start_followups.assert_awaited_once_with(['recovered'], discover=False)
        projector.start_drains.assert_not_called()
    else:
        service._maintain.assert_called_once_with(recover_quarantine=False)
        projector.sweep.assert_called_once()
        service.metrics.refresh.assert_called_once()
        projector.start_followups.assert_awaited_once_with(['recovered'])
        projector.start_drains.assert_called_once_with()


@pytest.mark.asyncio
async def test_owner_wake_leaves_process_wide_drain_queue_for_periodic_owner():
    projector = projector_for(ResultLog())
    projector.drain_requests = {'unrelated-owner': None}
    projector.index.defer(BURST, 'synthetic-conversation', [])
    projector.schedule_index_flush = Mock()

    def project(owner_id, *, recovered):
        projector.request_drain(owner_id)
        return [recovered]

    projector.project_owner = Mock(side_effect=project)
    projector.start_followups = AsyncMock()
    service = Serving(MemoryStore(), projector=projector)

    await service.reconcile_async(owner_id=BURST, recovered='recovered', owner_only=True)

    assert projector.drains is None
    assert projector.drain_requests == {'unrelated-owner': None, BURST: None}
    projector.start_followups.assert_awaited_once_with(['recovered'], discover=False)
    projector.schedule_index_flush.assert_called_once_with(BURST)


def test_owner_scope_commits_recovered_unit_before_projection_without_global_work():
    store, _, _ = admitted({'head': 1, 'recovered': 2})
    recovered(store, 'recovered', time.time())
    projector = Mock()

    def project(owner, recovered):
        assert store.rows['results', recovered]['recovered_release'] is True
        assert store.rows['jobs', 'head']['merge_pending'] is True
        return [recovered]

    projector.project_owner.side_effect = project
    service = Serving(store, projector=projector)
    service._maintain = Mock(side_effect=AssertionError('request entered global maintenance'))
    assert service.reconcile(owner_id='heavy', recovered='recovered', owner_only=True) == ['recovered']
    projector.sweep.assert_not_called()


def test_periodic_retry_after_failure_between_owner_merge_commits(monkeypatch):
    now = 500.0
    monkeypatch.setattr(time, 'time', lambda: now)
    store, _, _ = admitted({'head': 1, 'recovered': 2, 'sibling': 3})
    recovered(store, 'recovered', now, siblings=('sibling',))
    recovered(store, 'sibling', now)
    service = Serving(store)
    commit = service.merge.commit_next
    attempts = 0

    def fail_mid_drain(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 2:
            raise RuntimeError('synthetic interruption between commits')
        return commit(*args, **kwargs)

    monkeypatch.setattr(service.merge, 'commit_next', fail_mid_drain)
    service.reconcile(owner_id='heavy', recovered='recovered', owner_only=True)
    assert ('results', 'recovered') in store.rows
    assert ('results', 'sibling') not in store.rows
    assert store.rows['jobs', 'sibling']['merge_pending'] is True
    # The periodic owner rediscovers the durable job after process loss. Its
    # ordinary head wait can apply when the targeted release hint was lost.
    now += 61
    restarted = Serving(store, cleanup=Mock())
    restarted.reconcile(periodic=True)
    restarted.cleanup.assert_called_once()
    assert store.rows['jobs', 'sibling']['merge_pending'] is False
    assert store.rows['results', 'sibling']['previous_segment_id'] == 'recovered'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['before_assignment', 'after_assignment'])
async def test_periodic_restart_finishes_durable_publication_after_request_failure(monkeypatch, failure):
    monkeypatch.setattr(projection_followup, 'projection_followup_page_enabled', lambda: True)
    log = ResultLog()
    ids = chain(log, BURST, 'recovered-content', 3)
    # Extend the assignment-only ResultLog model with the follow-up snapshot
    # and policy seams. Receipt readiness still runs through the real runner.
    session_for = log.session

    def session(segment, *args, **kwargs):
        result = session_for(segment, *args, **kwargs)
        result.job, result.entry = log.jobs[segment], log.results[segment]
        return result

    monkeypatch.setattr(log, 'session', session)
    policy = ProjectionPolicy.from_dict(log.policy)
    monkeypatch.setattr(log, 'policy', lambda _: policy)
    projector = projector_for(log)
    service = Serving(MemoryStore(), projector=projector)
    if failure == 'before_assignment':
        projector.project_owner = Mock(side_effect=RuntimeError('synthetic request failure'))
        await service.reconcile_async(owner_id=BURST, recovered=ids[-1], owner_only=True)
        assert all(log.results[sid]['projection_state'] == 'pending' for sid in ids)
    else:
        projector.start_followups = AsyncMock(side_effect=RuntimeError('synthetic request failure'))
        with pytest.raises(RuntimeError, match='synthetic request failure'):
            await service.reconcile_async(owner_id=BURST, recovered=ids[-1], owner_only=True)
        assert all(log.results[sid]['projection_state'] == 'persisted' for sid in ids)
    # A new process has no callbacks, owner wakes, cursors or owed lists.
    restarted = projector_for(log)
    restarted.complete_content = Mock()
    assert not restarted.owes_followups and not restarted.owes_drains
    periodic = Serving(MemoryStore(), projector=restarted)
    periodic._maintain = Mock()
    try:
        await periodic.reconcile_async(periodic=True, recover_quarantine=True)
        periodic._maintain.assert_called_once_with(recover_quarantine=True)
        # The first pass can hand the pending chain to the process drain;
        # its walk-owed follow-ups launch on the next independent tick.
        if restarted.drains and restarted.drains.tasks:
            await asyncio.gather(*list(restarted.drains.tasks.values()))
        # Settle this discovery page before the next tick. Otherwise a ready
        # receipt's rediscovery depends on the executor's scheduling speed.
        while restarted.followups and restarted.followups.tasks:
            await asyncio.gather(*list(restarted.followups.tasks.values()))
        initial_probes = restarted.complete_content.call_count
        assert initial_probes == (1 if failure == 'before_assignment' else len(ids))
        await periodic.reconcile_async(periodic=True, recover_quarantine=True)
        while restarted.followups and restarted.followups.tasks:
            await asyncio.gather(*list(restarted.followups.tasks.values()))
        assert all(log.results[sid]['projection_state'] == 'ready' for sid in ids)
        assert log.persist_order == ids
        # Mocked completion leaves ready receipts discoverable. The first
        # probe for each unit plus one ready-content probe on the next page
        # are required; page coalescing is not a process-wide suppression.
        assert restarted.complete_content.call_count == len(ids) + 1
    finally:
        tasks = [
            task for runner in (restarted.drains, restarted.followups) if runner for task in list(runner.tasks.values())
        ]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_owner_followups_never_discover_global_rows_even_with_other_owed_work(monkeypatch):
    projector = projector_for(ResultLog())
    runner = projection_followup.ProjectionFollowups(projector)
    projector.followups = runner
    runner.pending.extend(['unrelated-pending-unit'])
    runner.owed['other-owner-unit'] = None
    projector.owe_followups(['other-walk-unit'])
    runner.candidates = Mock(side_effect=AssertionError('request scanned global follow-ups'))
    started = []

    async def finish(segment):
        started.append(segment)

    monkeypatch.setattr(runner, 'run', finish)
    try:
        await projector.start_followups(['recovered'], discover=False)
        while runner.tasks:
            await asyncio.gather(*list(runner.tasks.values()))
        assert started == ['recovered']
        assert list(runner.pending) == ['unrelated-pending-unit']
        assert list(runner.owed) == ['other-owner-unit']
        assert projector.chain_followups == ['other-walk-unit']
        runner.candidates.assert_not_called()
    finally:
        tasks = list(runner.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def test_owner_chain_kill_switch_defers_generic_sweep_to_periodic_owner(monkeypatch):
    from utils.batch_pipeline import serving

    monkeypatch.setattr(serving, 'owner_chain_projection_enabled', lambda: False)
    receipt = {'state': 'persisted'}
    projector = Mock()
    projector.project_owner = Mock(side_effect=AssertionError('disabled owner-chain walk ran'))

    def periodic_sweep():
        assert receipt['state'] == 'persisted'
        receipt['state'] = 'ready'

    projector.sweep.side_effect = periodic_sweep
    service = Serving(MemoryStore(), projector=projector)

    service.reconcile(owner_id=BURST, recovered='recovered', owner_only=True)
    assert receipt['state'] == 'persisted'
    projector.sweep.assert_not_called()

    service.reconcile(periodic=True)
    assert receipt['state'] == 'ready'
    projector.sweep.assert_called_once_with()


@pytest.mark.asyncio
async def test_owner_scope_with_no_priority_defers_owed_discovery_to_periodic_pass():
    projector = Mock(has_async_followups=True, owes_followups=True)
    projector.project_owner.return_value = []
    projector.start_followups = AsyncMock()
    await Serving(MemoryStore(), projector=projector).reconcile_async(
        owner_id=BURST, recovered='recovered', owner_only=True
    )
    projector.start_followups.assert_not_awaited()
    projector.sweep.assert_not_called()
