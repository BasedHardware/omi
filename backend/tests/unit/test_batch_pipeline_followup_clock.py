"""Durable incomplete-follow-up scheduling must never become a completion fence."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from database.batch_pipeline_projection_followup_clock import DUE_FIELD, defer_unchanged, state_fields
from database.batch_pipeline_projection_followup_backfill import backfill_ref, backfill_complete, stamp_page
from database.batch_pipeline_projection_finish import projection_finish_entry_fields, projection_finish_state_fields
from database.batch_pipeline_store import projection_page
from tests.unit.fixtures.strict_firestore_transaction import StrictFirestore
from utils.batch_pipeline.projection_followup_clock import FollowupClock
from utils.batch_pipeline.projection_discovery import ProjectionDiscovery
from utils.batch_pipeline.projection_followup import ProjectionFollowups
from utils.batch_pipeline import projection_followup


def store_fixture():
    row = {'segment_id': 'a', 'projection_state': 'ready', 'projection': {'state': 'ready'}, DUE_FIELD: 1.0}
    client = StrictFirestore({('batch_pipeline_dev_results', 'a'): row})
    store = SimpleNamespace(
        client=client,
        store=SimpleNamespace(namespace='batch_pipeline_dev'),
        ref=lambda kind, sid: client.collection(f'batch_pipeline_dev_{kind}').document(sid),
    )
    return store, deepcopy(row)


def test_only_an_unchanged_incomplete_preimage_is_deferred_and_never_slides():
    store, before = store_fixture()
    assert defer_unchanged(store, 'a', before, 100.0, 900.0)
    ref = store.ref('results', 'a')
    after = ref.get().to_dict()
    assert after == {**before, DUE_FIELD: 160.0}
    assert not defer_unchanged(store, 'a', before, 110.0, 900.0)
    assert not defer_unchanged(store, 'a', after, 110.0, 900.0)
    assert ref.get().to_dict()[DUE_FIELD] == 160.0


@pytest.mark.parametrize(
    'change',
    [
        {'projection_state': 'completed'},
        {'projection': {'state': 'ready', 'conversation_id': 'new'}},
        {'projection_parts': {'0': {'state': 'ready'}}},
        {DUE_FIELD: 101.0},
        {'projection_privacy_refusal': {'reason': 'account_deleted'}},
    ],
)
def test_racing_receipt_privacy_state_or_wake_write_cannot_be_overwritten(change):
    store, before = store_fixture()
    store.client.rows[('batch_pipeline_dev_results', 'a')].update(change)
    assert not defer_unchanged(store, 'a', before, 100.0, 60.0)
    assert store.ref('results', 'a').get().to_dict() == {**before, **change}


@pytest.mark.parametrize('due', [None, float('nan'), True, '1'])
def test_invalid_or_unstamped_rows_are_not_written(due):
    store, before = store_fixture()
    before[DUE_FIELD] = due
    store.client.rows[('batch_pipeline_dev_results', 'a')] = before
    assert not defer_unchanged(store, 'a', before, 100.0, 60.0)


def test_every_receipt_state_move_stamps_or_removes_the_independent_clock():
    for state in ('persisted', 'ready'):
        assert projection_finish_state_fields(state, 40.0)[DUE_FIELD] == 40.0
        assert projection_finish_entry_fields(state, 40.0)[DUE_FIELD] == 40.0
    assert state_fields('pending', 40.0, entry=True) == {}
    assert DUE_FIELD in projection_finish_state_fields('completed', 40.0)
    assert DUE_FIELD not in projection_finish_entry_fields('completed', 40.0)


def test_backfill_legacy_coverage_is_resumable_and_preserves_existing_due_dates():
    store, _ = store_fixture()
    db = store.client
    db.rows[('batch_pipeline_dev_results', 'a')].pop(DUE_FIELD)
    db.rows[('batch_pipeline_dev_results', 'b')] = {'projection_state': 'persisted', DUE_FIELD: 500.0}
    page_store = SimpleNamespace(
        client=db, namespace='batch_pipeline_dev', projection_page=Mock(return_value=(['a'], (1, 'a')))
    )
    assert stamp_page(page_store, 100.0)['missing'] == 1
    assert not backfill_complete(db, page_store.namespace)
    assert stamp_page(page_store, 100.0, apply=True)['stamped'] == 1
    assert not backfill_complete(db, page_store.namespace)
    page_store.projection_page.return_value = (['b'], None)
    assert stamp_page(page_store, 101.0, apply=True)['complete']
    assert backfill_complete(db, page_store.namespace)
    assert db.rows[('batch_pipeline_dev_results', 'b')][DUE_FIELD] == 500.0
    assert stamp_page(page_store, 102.0, apply=True)['scanned'] == 0


def test_marker_is_checked_once_per_minute_until_complete_and_disabled_mode_never_reads():
    projector = Mock()
    projector.clock.return_value = 100.0
    marker = projector.store.store.projection_followup_backfill_complete
    marker.return_value = False
    clock = FollowupClock(projector)
    clock.monotonic = Mock(return_value=0.0)
    assert clock.before(False) is None
    marker.assert_not_called()
    assert clock.before(True) is None
    assert clock.before(True) is None
    assert marker.call_count == 1
    marker.return_value = True
    clock.monotonic.return_value = 60.0
    assert clock.before(True) == 100.0
    assert clock.before(True) == 100.0
    assert marker.call_count == 2
    assert clock.before(False) is None


def test_marker_failure_keeps_legacy_discovery_and_outcome_failure_never_defers():
    projector = Mock()
    projector.store.store.projection_followup_backfill_complete.side_effect = RuntimeError('unavailable')
    clock = FollowupClock(projector)
    assert clock.before(True) is None
    clock.active = True
    for outcome in ('blocked', 'retry', 'timeout', 'claim_busy', 'completed', 'coalesced'):
        clock.observe('a', {'projection_state': 'ready'})
        assert not clock.settle('a', outcome, 900.0)
        assert not clock.entries
    projector.store.ref.assert_not_called()


def test_ordering_switch_drops_incompatible_cursor_but_keeps_bounded_page(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    store = Mock()
    store.projection_page.return_value = (['a'], (10.0, 2.0, 'a'))
    discovery = ProjectionDiscovery(store, states=('persisted', 'ready'))
    discovery.after = (2.0, 'legacy')
    assert discovery.next(limit=20, followup_due_before=100.0) == ['a']
    store.projection_page.assert_called_once_with(
        limit=20, after=None, states=('persisted', 'ready'), followup_due_before=100.0
    )
    discovery.next(limit=20, due_before=100.0)
    assert store.projection_page.call_args.kwargs['after'] is None
    discovery.next(limit=20)
    assert store.projection_page.call_args.kwargs['after'] is None


def test_finish_and_followup_clocks_cannot_be_combined():
    with pytest.raises(ValueError):
        projection_page(Mock(), 'batch_pipeline_dev', due_before=1.0, followup_due_before=1.0)


def test_durable_due_discovery_bypasses_a_stale_process_local_sleep(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    projector = Mock()
    projector.clock.return_value = 100.0
    projector.store.store.projection_followup_backfill_complete.return_value = True
    projector.store.store.projection_page.return_value = (['a'], None)
    runner = ProjectionFollowups(projector)
    runner.backoff['a'] = (1e20, 900.0)
    assert runner.discovered() == ['a']
    projector.store.store.projection_page.assert_called_once_with(limit=100, after=None, followup_due_before=100.0)


@pytest.mark.asyncio
async def test_targeted_wake_does_not_consult_due_clock_or_discovery():
    projector = Mock()
    runner = ProjectionFollowups(projector)
    runner.launch_targeted = Mock()
    await runner.schedule(priority=('future-due',), discover=False)
    assert list(runner.targeted_pending) == ['future-due']
    projector.store.store.projection_followup_backfill_complete.assert_not_called()
    projector.store.store.projection_page.assert_not_called()


@pytest.mark.asyncio
async def test_cancelled_followup_drops_its_defer_snapshot_without_a_write():
    projector = Mock()
    runner = ProjectionFollowups(projector)
    runner.due_clock.entries['a'] = {'projection_state': 'ready'}
    runner._run = AsyncMock(side_effect=asyncio.CancelledError)
    with pytest.raises(asyncio.CancelledError):
        await runner.run('a')
    assert not runner.due_clock.entries
    projector.store.ref.assert_not_called()


def test_due_pass_uses_a_fixed_cutoff_until_wrap_so_new_tail_cannot_starve_old_rows(monkeypatch):
    monkeypatch.setenv('BATCH_PIPELINE_PROJECTION_STRIPING_ENABLED', 'off')
    projector = Mock()
    projector.clock.side_effect = [100.0, 200.0, 300.0]
    store = projector.store.store
    store.projection_followup_backfill_complete.return_value = True
    store.projection_page.side_effect = [(['a'], (10.0, 1.0, 'a')), (['b'], None), (['c'], None)]
    runner = ProjectionFollowups(projector)
    assert runner.discovered() == ['a']
    assert runner.discovered() == ['b']
    assert runner.discovered() == ['c']
    assert [call.kwargs['followup_due_before'] for call in store.projection_page.call_args_list] == [
        100.0,
        100.0,
        300.0,
    ]


@pytest.mark.asyncio
async def test_hint_persistence_shares_the_existing_attempt_timeout(monkeypatch):
    # Patch a deterministic timeout boundary; do not race a tiny real-clock budget.
    class Boundary:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            assert seen == ['attempt', 'settle']

    seen = []
    monkeypatch.setattr(projection_followup.asyncio, 'timeout', lambda seconds: Boundary())
    projector = Mock()
    runner = ProjectionFollowups(projector)

    async def work(segment):
        seen.append('attempt')
        runner.due_clock.entries[segment] = {'projection_state': 'ready'}
        return 'incomplete'

    async def blocking(_executor, function, *args):
        seen.append('settle')
        return function(*args)

    runner._run = work
    runner.due_clock.settle = Mock(return_value=True)
    monkeypatch.setattr(projection_followup, 'run_blocking', blocking)
    await runner.run('a')
    assert not runner.due_clock.entries
