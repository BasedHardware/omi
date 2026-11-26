"""Provider-route units as full members of the ordered merge (synthetic only).

2026-11-13: 1.68M transcribed provider units sat in ``result_ready``. Nothing woke their owner's
merge, they had no ``ready_at`` for the head wait, and no merge class for fresh-first.
"""

import asyncio
import logging
import time

import pytest

from database import batch_pipeline_intake
from routers import batch_provider_stt as route
from tests.unit.test_batch_provider_stt import (  # noqa: F401  # world is a fixture
    JA,
    OWNER,
    Artifacts,
    Outbox,
    StubStage,
    Vendor,
    _claim,
    admit,
    item,
    job,
    stage,
    world,
)
from utils.batch_pipeline import provider_stt, provider_stt_admission
from utils.batch_pipeline.contracts import ProjectionBinding
from utils.batch_pipeline.merge import OrderedMerge
from utils.batch_pipeline.provider_drain import HEAD_WAIT_MARGIN_SECONDS, OwnerDrainCoalescer
from utils.batch_pipeline.scheduler import owner_key
from utils.batch_pipeline.serving import Serving

SWITCH = 'BATCH_PIPELINE_PROVIDER_MERGE_MEMBERSHIP_ENABLED'
RELEASE = 'BATCH_PIPELINE_PROVIDER_BACKLOG_RELEASE_ENABLED'
# With the meter on (the default) the legacy switch alone releases nothing; these tests set the
# meter off where they describe the legacy unmetered release.
METER = 'BATCH_PIPELINE_BACKLOG_RELEASE_METER_ENABLED'
# admit() runs at 100.0 with 5 s units, so a capture at 10 is fresh.
FRESH_CAPTURE = 10
STALE = 90_000.0  # More than a day after FRESH_CAPTURE: catch-up under the provider bar.
LAG = 'BATCH_PIPELINE_PROVIDER_FRESH_CAPTURE_LAG_SECONDS'


def settle(store, segment, now=200.0):
    outcome = stage(store, Artifacts(), Vendor(), now=now).run(segment)
    assert (outcome.outcome, outcome.reason) == ('done', 'processed')


def drain(merge, now):
    entries = []
    while entry := merge.commit_next(OWNER, now):
        entries.append(entry)
    return entries


# --- the two stamps -----------------------------------------------------------------------------


def test_provider_admission_stamps_the_merge_class(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('fresh', FRESH_CAPTURE)], 'content-fresh', JA)
    # The same capture admitted more than a day later is catch-up.
    late = item('old', FRESH_CAPTURE)
    binding = ProjectionBinding(OWNER, 'bp_content-old', 'content-old', ('old',), language='ja')
    enqueue = provider_stt_admission.provider_enqueue(JA, Outbox(), {})
    outcome = batch_pipeline_intake.admit(store, [late], binding, STALE, namespace=store.namespace, enqueue=enqueue)
    assert outcome['outcome'] == 'batch'
    assert job(store, 'fresh')['fresh_capture'] is True
    assert job(store, 'old')['fresh_capture'] is False


def _admit_late(store, name, now):
    binding = ProjectionBinding(OWNER, f'bp_content-{name}', f'content-{name}', (name,), language='ja')
    enqueue = provider_stt_admission.provider_enqueue(JA, Outbox(), {})
    batch_pipeline_intake.admit(
        store, [item(name, FRESH_CAPTURE)], binding, now, namespace=store.namespace, enqueue=enqueue
    )
    return job(store, name)


def test_a_provider_upload_within_a_day_of_capture_is_fresh(world, monkeypatch):
    """2026-11-13: 167 late-synced provider uploads since the hold, none committed."""
    _, store = world
    assert _admit_late(store, 'two-hours', 7300.0)['fresh_capture'] is True
    end = FRESH_CAPTURE + item('probe', FRESH_CAPTURE).duration_seconds
    assert _admit_late(store, 'edge', end + 86400.0)['fresh_capture'] is True
    assert _admit_late(store, 'over', end + 86401.0)['fresh_capture'] is False


def test_a_late_fresh_upload_keeps_backfill_conflict_handling(world, monkeypatch):
    """The longer bar changes the merge class only: a writer still missing hours later holds."""
    from utils.batch_pipeline.projection_hold_policy import quarantines_assignment_conflict
    from utils.sync.assignment_errors import SyncAssignmentConflict, SyncAssignmentConflictReason

    _, store = world
    end = FRESH_CAPTURE + item('probe', FRESH_CAPTURE).duration_seconds
    on_time = _admit_late(store, 'on-time', end + 600.0)
    late = _admit_late(store, 'late', end + 7 * 3600.0)
    over = _admit_late(store, 'over', end + 86401.0)
    assert 'late_upload' not in on_time and late['late_upload'] is True and 'late_upload' not in over
    waiting = SyncAssignmentConflict('synthetic', subtype=SyncAssignmentConflictReason.RECORD_FINALIZE_PENDING)
    now = end + 8 * 3600.0
    assert quarantines_assignment_conflict(waiting, late, now=now)
    assert quarantines_assignment_conflict(waiting, {**late, 'fresh_capture': False}, now=now)
    assert not quarantines_assignment_conflict(waiting, {**on_time}, now=now)
    # Under six hours old, every lane keeps waiting, as before.
    assert not quarantines_assignment_conflict(waiting, late, now=end + 3600.0)


def test_the_setting_restores_the_ten_minute_bar_and_is_bounded(world, monkeypatch):
    from config import batch_pipeline

    _, store = world
    monkeypatch.setenv(LAG, '600')
    assert _admit_late(store, 'two-hours', 7300.0)['fresh_capture'] is False
    for raw, want in (('600', 600), ('3600', 3600), ('10', 600), ('999999', 86400), ('junk', 86400)):
        monkeypatch.setenv(LAG, raw)
        assert batch_pipeline.provider_fresh_capture_lag_seconds() == want
    monkeypatch.delenv(LAG)
    assert batch_pipeline.provider_fresh_capture_lag_seconds() == 86400


def test_a_late_provider_upload_commits_ahead_of_the_held_backlog(world, monkeypatch):
    store, names = _legacy_backlog(world, monkeypatch, 3)
    assert _admit_late(store, 'late', 7300.0)['fresh_capture'] is True
    settle(store, 'late', now=7400.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert [e['segment_id'] for e in drain(merge, 7401.0)] == ['late']
    assert [job(store, name)['state'] for name in names] == ['result_ready'] * 3


def test_the_gpu_lane_keeps_its_ten_minute_bar():
    from config.batch_pipeline import FRESH_CAPTURE_LAG_SECONDS

    assert FRESH_CAPTURE_LAG_SECONDS == 600.0


def test_provider_admissions_are_counted_by_class_and_lag(world, monkeypatch):
    _, store = world
    counter = provider_stt_admission.PROVIDER_ADMISSIONS

    def value(merge_class, lag):
        return counter.labels(merge_class=merge_class, lag=lag)._value.get()

    before = {
        key: value(*key) for key in (('fresh', 'lt10m'), ('fresh', 'lt1h'), ('fresh', 'lt24h'), ('catch_up', 'ge24h'))
    }
    end = FRESH_CAPTURE + item('probe', FRESH_CAPTURE).duration_seconds
    _admit_late(store, 'a', end + 60.0)
    _admit_late(store, 'b', end + 1800.0)
    _admit_late(store, 'c', end + 7200.0)
    _admit_late(store, 'd', end + 90000.0)
    assert {key: value(*key) - before[key] for key in before} == dict.fromkeys(before, 1)


def test_provider_settle_stamps_ready_at(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', FRESH_CAPTURE)], 'content-p', JA)
    settle(store, 'p1', now=200.0)
    row = job(store, 'p1')
    assert row['state'] == 'result_ready' and row['ready_at'] == 200.0


def test_switch_off_writes_neither_stamp(world, monkeypatch):
    monkeypatch.setenv(SWITCH, 'false')
    _, store = world
    admit(monkeypatch, store, [item('p1', FRESH_CAPTURE)], 'content-p', JA)
    settle(store, 'p1')
    row = job(store, 'p1')
    assert row['state'] == 'result_ready' and 'ready_at' not in row and 'fresh_capture' not in row


def test_a_failed_unit_gets_no_ready_at(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', FRESH_CAPTURE)], 'content-p', JA)
    failing = stage(store, Artifacts(), Vendor(error=RuntimeError('synthetic vendor outage')))
    assert failing.run('p1').provider_reason == 'provider_failed'
    row = job(store, 'p1')
    assert row['state'] == 'quarantined' and row['merge_pending'] is False and 'ready_at' not in row


# --- the merge ----------------------------------------------------------------------------------


def test_ready_provider_row_commits_past_an_unready_head_after_the_head_wait(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-1', JA)
    admit(monkeypatch, store, [item('p2', 20)], 'content-2', JA)
    settle(store, 'p2', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert merge.commit_next(OWNER, 230.0) is None  # p1 still heads the owner; p2 has waited 30 s
    entry = merge.commit_next(OWNER, 261.0)
    assert entry['segment_id'] == 'p2' and entry['head_wait_bypass'] is True and entry['recovery_version'] == 1
    assert job(store, 'p1')['merge_pending'] is True
    # The bypassed head appends later, marked late.
    settle(store, 'p1', now=300.0)
    late = merge.commit_next(OWNER, 301.0)
    assert late['segment_id'] == 'p1' and late['late_capture'] is True


def test_switch_off_keeps_a_ready_provider_row_behind_its_unready_head(world, monkeypatch):
    monkeypatch.setenv(SWITCH, 'false')
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-1', JA)
    admit(monkeypatch, store, [item('p2', 20)], 'content-2', JA)
    settle(store, 'p2', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert merge.commit_next(OWNER, 10_000.0) is None


def _legacy_backlog(world, monkeypatch, count):
    """``count`` settled provider rows admitted and settled before the stamps existed."""
    _, store = world
    monkeypatch.setenv(SWITCH, 'false')
    names = [f'old{n}' for n in range(count)]
    for n, name in enumerate(names):
        admit(monkeypatch, store, [item(name, 10 + n)], f'content-{name}', JA)
        settle(store, name)
        row = job(store, name)
        assert 'fresh_capture' not in row and 'ready_at' not in row
    monkeypatch.delenv(SWITCH)
    return store, names


def test_unstamped_ready_row_passes_an_unready_head_once_its_settle_is_a_head_wait_old(world, monkeypatch):
    """A row settled before the ready_at stamp has only its intent's settled_at to wait from."""
    monkeypatch.setenv(RELEASE, 'true')
    monkeypatch.setenv(METER, 'false')
    _, store = world
    monkeypatch.setenv(SWITCH, 'false')
    admit(monkeypatch, store, [item('head', 10)], 'content-head', JA)
    admit(monkeypatch, store, [item('old', 20)], 'content-old', JA)
    settle(store, 'old', now=200.0)
    assert 'ready_at' not in job(store, 'old')
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert merge.commit_next(OWNER, 10_000.0) is None  # switch off: stuck behind the unready head
    monkeypatch.delenv(SWITCH)
    assert merge.commit_next(OWNER, 230.0) is None  # settled 30 s ago
    entry = merge.commit_next(OWNER, 261.0)
    assert entry['segment_id'] == 'old' and entry['head_wait_bypass'] is True
    assert job(store, 'head')['merge_pending'] is True and merge.commit_next(OWNER, 262.0) is None


def test_ready_fresh_rows_without_ready_at_pass_an_unready_fresh_row_behind_a_held_backlog(world, monkeypatch):
    """2026-11-13 prod shape: held backlog at the head, then a fresh unit the vendor holds,
    then ready fresh units whose ready_at is missing (settled while the stamp was off, or
    removed). Before, the fresh pick measured the wait only from ready_at: nothing committed."""
    store, names = _legacy_backlog(world, monkeypatch, 2)
    admit(monkeypatch, store, [item('stuck', 80)], 'content-stuck', JA)  # fresh, never settles
    for name, capture in (('ready-a', 85), ('ready-b', 90)):
        admit(monkeypatch, store, [item(name, capture)], f'content-{name}', JA)
    monkeypatch.setenv(SWITCH, 'false')
    for name in ('ready-a', 'ready-b'):
        settle(store, name, now=200.0)
    monkeypatch.delenv(SWITCH)
    assert all(
        job(store, n)['fresh_capture'] is True and 'ready_at' not in job(store, n) for n in ('ready-a', 'ready-b')
    )
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert merge.commit_next(OWNER, 230.0) is None  # settled 30 s ago: inside the wait
    entries = drain(merge, 261.0)
    assert [e['segment_id'] for e in entries] == ['ready-a', 'ready-b']
    assert all(e['fresh_first'] is True for e in entries)
    # The held unit and the backlog stay pending; nothing non-fresh committed.
    assert job(store, 'stuck')['merge_pending'] is True
    assert [job(store, name)['state'] for name in names] == ['result_ready', 'result_ready']


def test_a_full_probe_page_with_no_ready_row_is_logged(world, monkeypatch, caplog):
    """The probe sees 32 rows. A full page of unready fresh rows can hide ready ones: say so."""
    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', 'false')
    store, _ = _legacy_backlog(world, monkeypatch, 1)
    for n in range(32):
        admit(monkeypatch, store, [item(f'stuck{n:02d}', 40 + n)], f'content-stuck{n}', JA)
    admit(monkeypatch, store, [item('ready', 90)], 'content-ready', JA)
    settle(store, 'ready', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    with caplog.at_level(logging.WARNING):
        assert merge.commit_next(OWNER, 261.0) is None
    assert 'outcome=fresh_probe_full_no_ready' in caplog.text


def _project_through(store, segment):
    key = owner_key(OWNER)
    store.run(lambda tx: tx.put('owners', key, {**tx.get('owners', key), 'projection_watermark': segment}))


def test_fresh_provider_row_passes_the_owners_unstamped_backlog(world, monkeypatch):
    monkeypatch.setenv(RELEASE, 'true')
    monkeypatch.setenv(METER, 'false')
    store, names = _legacy_backlog(world, monkeypatch, 6)
    admit(monkeypatch, store, [item('new', 90)], 'content-new', JA)
    settle(store, 'new', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=4)
    entries = drain(merge, 201.0)
    # The backlog commits up to the depth cap, then holds; the fresh row lands right behind it.
    assert [e['segment_id'] for e in entries] == [*names[:4], 'new']
    assert entries[-1]['fresh_first'] is True and entries[-1]['late_capture'] is False
    assert [job(store, name)['state'] for name in names[4:]] == ['result_ready', 'result_ready']
    # The held backlog follows as projection advances, appended as late captures.
    _project_through(store, 'new')
    rest = drain(merge, 202.0)
    assert [e['segment_id'] for e in rest] == names[4:]
    assert all(e['late_capture'] is True for e in rest)


def test_backlog_release_is_off_by_default_and_only_fresh_rows_commit(world, monkeypatch):
    """2026-11-13: owner wakes released 230k backlog rows an hour into projection and delayed
    every user's fresh results. By default the backlog stays ready and only fresh rows commit."""
    store, names = _legacy_backlog(world, monkeypatch, 6)
    admit(monkeypatch, store, [item('new1', 90), item('new2', 95)], 'content-new', JA)
    settle(store, 'new1', now=200.0)
    settle(store, 'new2', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=4)
    entries = drain(merge, 201.0)
    assert [e['segment_id'] for e in entries] == ['new1', 'new2']
    assert all(e['fresh_first'] is True for e in entries)
    assert all(job(store, name)['state'] == 'result_ready' and job(store, name)['merge_pending'] for name in names)
    # Not a depth hold: no durable marker and no in-memory re-offer for maintenance to churn on.
    assert merge.held_owners == set()
    assert not store.run(lambda tx: tx.get('merge_holds', owner_key(OWNER))).get('held')
    # However far projection advances and however long the backlog waits, it stays put.
    _project_through(store, 'new2')
    assert drain(merge, 10_000.0) == []
    # Opting in releases it under the usual depth hold, appended as late captures.
    monkeypatch.setenv(RELEASE, 'true')
    monkeypatch.setenv(METER, 'false')
    rest = drain(merge, 10_001.0)
    assert [e['segment_id'] for e in rest] == names[:4]
    assert all(e['late_capture'] is True for e in rest)


def test_fresh_rows_pass_a_held_backlog_even_with_the_depth_hold_switched_off(world, monkeypatch):
    store, names = _legacy_backlog(world, monkeypatch, 3)
    admit(monkeypatch, store, [item('new', 90)], 'content-new', JA)
    settle(store, 'new', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=0)
    assert [e['segment_id'] for e in drain(merge, 201.0)] == ['new']
    assert [job(store, name)['state'] for name in names] == ['result_ready'] * 3


def test_a_stale_capture_admitted_now_is_backlog_too(world, monkeypatch):
    """A provider row stamped not-fresh at admission waits for the metered release like the rest."""
    _, store = world
    late = item('old', FRESH_CAPTURE)
    binding = ProjectionBinding(OWNER, 'bp_content-old', 'content-old', ('old',), language='ja')
    enqueue = provider_stt_admission.provider_enqueue(JA, Outbox(), {})
    batch_pipeline_intake.admit(store, [late], binding, STALE, namespace=store.namespace, enqueue=enqueue)
    assert job(store, 'old')['fresh_capture'] is False
    settle(store, 'old', now=STALE + 100.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert drain(merge, STALE + 101.0) == []
    monkeypatch.setenv(RELEASE, 'true')
    monkeypatch.setenv(METER, 'false')
    assert [e['segment_id'] for e in drain(merge, STALE + 102.0)] == ['old']


def test_a_ready_backlog_row_does_not_pass_an_unready_head_while_release_is_off(world, monkeypatch):
    _, store = world
    monkeypatch.setenv(SWITCH, 'false')
    admit(monkeypatch, store, [item('head', 10)], 'content-head', JA)
    admit(monkeypatch, store, [item('old', 20)], 'content-old', JA)
    settle(store, 'old', now=200.0)
    monkeypatch.delenv(SWITCH)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=16)
    assert merge.commit_next(OWNER, 10_000.0) is None
    assert merge.held_owners == set() and job(store, 'old')['state'] == 'result_ready'


def test_gpu_catch_up_rows_are_not_held_by_the_provider_backlog_switch(monkeypatch):
    from utils.batch_pipeline.merge import _backlog_held

    assert _backlog_held({'stt_route': {'stt_route': 'provider'}}) is True
    assert _backlog_held({'stt_route': {'stt_route': 'provider'}, 'fresh_capture': False}) is True
    assert _backlog_held({'stt_route': {'stt_route': 'provider'}, 'fresh_capture': True}) is False
    assert _backlog_held({'stt_route': {'stt_route': 'parakeet'}, 'fresh_capture': False}) is False
    assert _backlog_held({'fresh_capture': False}) is False
    # The hold outlives the membership switch: rows it stamped stay eligible after it goes off.
    monkeypatch.setenv(SWITCH, 'false')
    assert _backlog_held({'stt_route': {'stt_route': 'provider'}}) is True
    monkeypatch.setenv(RELEASE, 'true')
    monkeypatch.setenv(METER, 'false')
    assert _backlog_held({'stt_route': {'stt_route': 'provider'}}) is False


def test_membership_switch_off_still_holds_the_backlog(world, monkeypatch):
    """2026-11-13: an hour after membership was switched off, rows it had stamped were still
    committing at 1,700 a minute through the head wait. Off must not mean release."""
    store, names = _legacy_backlog(world, monkeypatch, 6)
    admit(monkeypatch, store, [item('new', 90)], 'content-new', JA)
    settle(store, 'new', now=200.0)
    monkeypatch.setenv(SWITCH, 'false')
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=4)
    assert [e['segment_id'] for e in drain(merge, 10_000.0)] == ['new']
    assert [job(store, name)['state'] for name in names] == ['result_ready'] * 6
    # With release on, switch-off is the old plain order.
    monkeypatch.setenv(RELEASE, 'true')
    monkeypatch.setenv(METER, 'false')
    assert [e['segment_id'] for e in drain(merge, 10_001.0)] == names


def test_a_fresh_row_passes_an_unready_backlog_head_with_the_depth_hold_off(world, monkeypatch):
    """Depth 0, an unready provider head, a ready held row and a fresh row behind it: the head
    wait alone would pick the held row and commit nothing, every drain."""
    _, store = world
    monkeypatch.setenv(SWITCH, 'false')
    admit(monkeypatch, store, [item('head', 10)], 'content-head', JA)
    admit(monkeypatch, store, [item('old', 20)], 'content-old', JA)
    settle(store, 'old', now=200.0)
    monkeypatch.delenv(SWITCH)
    admit(monkeypatch, store, [item('new', 90)], 'content-new', JA)
    settle(store, 'new', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=0)
    assert [e['segment_id'] for e in drain(merge, 10_000.0)] == ['new']
    assert job(store, 'old')['state'] == 'result_ready' and job(store, 'head')['merge_pending']


def test_an_unavailable_fresh_query_keeps_the_backlog_held_and_asks_once(world, monkeypatch):
    from google.api_core.exceptions import FailedPrecondition

    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', 'false')
    store, names = _legacy_backlog(world, monkeypatch, 3)
    admit(monkeypatch, store, [item('new', 90)], 'content-new', JA)
    settle(store, 'new', now=200.0)
    calls = []

    def unavailable(key, limit):
        calls.append(key)
        raise FailedPrecondition('The query requires an index.')

    monkeypatch.setattr(store, 'fresh_pending', unavailable, raising=False)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=4)
    assert merge.commit_next(OWNER, 201.0) is None
    assert merge.commit_next(OWNER, 202.0) is None
    # One failed query, then a backoff: no recursion and no plain-order backlog commit.
    assert len(calls) == 1
    assert [job(store, name)['state'] for name in names] == ['result_ready'] * 3


def test_a_backlog_only_probe_failure_leaves_the_depth_hold_on(world, monkeypatch):
    """With membership off a held head is not catch-up, so only the backlog hold asks for the
    probe. Its failure must not switch the depth hold off for the whole merge instance."""
    from google.api_core.exceptions import FailedPrecondition

    monkeypatch.setenv('BATCH_PIPELINE_MERGE_TX_FRESH_GATE_ENABLED', 'false')
    store, names = _legacy_backlog(world, monkeypatch, 2)
    monkeypatch.setenv(SWITCH, 'false')

    def unavailable(key, limit):
        raise FailedPrecondition('The query requires an index.')

    monkeypatch.setattr(store, 'fresh_pending', unavailable, raising=False)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=4)
    assert merge.commit_next(OWNER, 201.0) is None
    assert merge._catch_up_depth() == 4
    assert [job(store, name)['state'] for name in names] == ['result_ready'] * 2


def test_a_held_backlog_head_at_the_depth_cap_writes_no_marker(world, monkeypatch):
    """A depth marker would have maintenance re-offer an owner whose head can never commit."""
    store, names = _legacy_backlog(world, monkeypatch, 3)
    admit(monkeypatch, store, [item('new1', 90), item('new2', 95)], 'content-new', JA)
    settle(store, 'new1', now=200.0)
    settle(store, 'new2', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=1)
    assert [e['segment_id'] for e in drain(merge, 201.0)] == ['new1', 'new2']
    # Two rows now await projection, past a depth of 1, and the held backlog heads the owner.
    assert merge.commit_next(OWNER, 202.0) is None
    assert merge.held_owners == set()
    assert not store.run(lambda tx: tx.get('merge_holds', owner_key(OWNER))).get('held')


def test_an_unready_backlog_head_at_the_depth_cap_writes_no_marker(world, monkeypatch):
    _, store = world
    monkeypatch.setenv(SWITCH, 'false')
    admit(monkeypatch, store, [item('head', 10)], 'content-head', JA)
    monkeypatch.delenv(SWITCH)
    admit(monkeypatch, store, [item('new1', 90), item('new2', 95)], 'content-new', JA)
    settle(store, 'new1', now=200.0)
    settle(store, 'new2', now=200.0)
    merge = OrderedMerge(store, head_wait_seconds=60, catch_up_depth=1)
    assert [e['segment_id'] for e in drain(merge, 201.0)] == ['new1', 'new2']
    assert merge.commit_next(OWNER, 202.0) is None
    assert merge.held_owners == set()
    assert not store.run(lambda tx: tx.get('merge_holds', owner_key(OWNER))).get('held')


def test_unstamped_gpu_rows_keep_the_plain_order(world, monkeypatch):
    """Only provider rows are reclassified: a record-lane or older GPU row has no class either."""
    from utils.batch_pipeline.merge import _catch_up

    assert _catch_up({'stt_route': {'stt_route': 'provider'}}) is True
    assert _catch_up({'stt_route': {'stt_route': 'parakeet'}}) is False
    assert _catch_up({}) is False
    assert _catch_up({'fresh_capture': True, 'stt_route': {'stt_route': 'provider'}}) is False
    assert _catch_up({'fresh_capture': False}) is True


# --- the coalesced owner drain ------------------------------------------------------------------


class Drains:
    def __init__(self, on_call=None, error=None):
        self.calls: list[str] = []
        self.on_call, self.error = on_call, error

    async def __call__(self, owner_id):
        self.calls.append(owner_id)
        if self.on_call is not None:
            self.on_call(len(self.calls))
        if self.error is not None:
            raise self.error


def coalescer(drains, *, head_wait=60.0, slept=None, **kwargs):
    async def sleep(seconds):
        if slept is not None:
            slept.append(seconds)
        await asyncio.sleep(0)

    return OwnerDrainCoalescer(drains, head_wait=lambda: head_wait, sleep=sleep, **kwargs)


async def _idle(drainer):
    for _ in range(10_000):
        if not drainer.pending():
            return
        await asyncio.sleep(0)
    raise AssertionError('owner drains did not finish')


@pytest.mark.asyncio
async def test_a_burst_for_one_owner_costs_one_round_of_two_drains():
    drains, slept = Drains(), []
    drainer = coalescer(drains, slept=slept)
    assert all(drainer.request('owner-a') for _ in range(50))
    assert drainer.pending() == 1
    await _idle(drainer)
    # One drain after the delay, one after the head wait: 50 settles, 2 drains.
    assert drains.calls == ['owner-a', 'owner-a']
    assert slept == [2.0, 60.0 + HEAD_WAIT_MARGIN_SECONDS]


@pytest.mark.asyncio
async def test_a_request_during_a_round_buys_exactly_one_more_round():
    drainer = None

    def during(call):
        if call == 1:
            for _ in range(10):
                drainer.request('owner-a')

    drains = Drains(on_call=during)
    drainer = coalescer(drains)
    drainer.request('owner-a')
    await _idle(drainer)
    assert drains.calls == ['owner-a'] * 4


@pytest.mark.asyncio
async def test_head_wait_off_drains_once_and_owners_are_independent():
    drains = Drains()
    drainer = coalescer(drains, head_wait=0.0)
    drainer.request('owner-a')
    drainer.request('owner-b')
    assert drainer.pending() == 2
    await _idle(drainer)
    assert sorted(drains.calls) == ['owner-a', 'owner-b']


@pytest.mark.asyncio
async def test_an_owner_past_the_task_bound_waits_its_turn_and_is_never_dropped(caplog):
    drains = Drains()
    drainer = coalescer(drains, head_wait=0.0, max_owners=1)
    assert drainer.request('owner-a') is True
    with caplog.at_level(logging.WARNING):
        # Each of these may be the owner's only settle: none has a later request to rely on.
        assert drainer.request('owner-b') is False
        assert drainer.request('owner-c') is False
        assert drainer.request('owner-b') is False
    assert caplog.text.count('event=batch_provider_drain outcome=queued reason=owner_bound') == 2
    assert drainer.pending() == 3
    await _idle(drainer)
    assert drains.calls == ['owner-a', 'owner-b', 'owner-c']


@pytest.mark.asyncio
async def test_wake_tasks_are_tracked_background_tasks():
    from utils.executors import get_background_task_count

    before = get_background_task_count()
    drainer = coalescer(Drains(), head_wait=0.0)
    drainer.request('owner-a')
    assert get_background_task_count() == before + 1
    await _idle(drainer)
    await asyncio.sleep(0)
    assert get_background_task_count() == before


@pytest.mark.asyncio
async def test_a_failing_drain_is_logged_by_type_and_frees_the_owner(caplog):
    drains = Drains(error=RuntimeError('synthetic private detail'))
    drainer = coalescer(drains)
    with caplog.at_level(logging.WARNING):
        drainer.request('owner-a')
        await _idle(drainer)
    assert drains.calls == ['owner-a', 'owner-a'] and drainer.pending() == 0
    assert 'event=batch_provider_drain outcome=retry exception_type=RuntimeError' in caplog.text
    assert 'synthetic private detail' not in caplog.text and 'owner-a' not in caplog.text


@pytest.mark.asyncio
async def test_drains_run_at_most_the_configured_number_at_once():
    running, peak = 0, 0

    async def drain(owner_id):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0)
        running -= 1

    drainer = coalescer(drain, head_wait=0.0, concurrency=2)
    for n in range(8):
        drainer.request(f'owner-{n}')
    await _idle(drainer)
    assert peak == 2


# --- the wake from a delivery -------------------------------------------------------------------


class AsyncStubStage(StubStage):
    async def run_async(self, segment_id, run_sync):
        return self.run(segment_id)


async def _inline(fn, *args, **kwargs):
    return fn(*args, **kwargs)


@pytest.mark.parametrize(
    'unit,woken',
    [
        (provider_stt.UnitOutcome('done', 'processed'), True),
        # A terminal unit leaves the owner's merge order, which can unblock the rows behind it.
        (provider_stt.UnitOutcome('done', 'processed', provider_reason='provider_failed'), True),
        (provider_stt.UnitOutcome('done', 'superseded'), False),
        (provider_stt.UnitOutcome('deferred', 'not_due', 260.0), False),
        (provider_stt.UnitOutcome('discarded', 'privacy_blocked'), False),
        (provider_stt.UnitOutcome('retry', 'dependency_warming'), False),
    ],
)
@pytest.mark.asyncio
async def test_only_a_processed_delivery_wakes_the_owner_merge(unit, woken):
    seen = []
    consumer = provider_stt.ProviderSttConsumer(lambda: AsyncStubStage(unit), clock=lambda: 100.0, settled=seen.append)
    await consumer.process_async(_claim(), lambda: True, _inline)
    assert seen == ([OWNER] if woken else [])


@pytest.mark.asyncio
async def test_a_failing_wake_never_changes_the_delivery_result(caplog):
    def broken(owner_id):
        raise RuntimeError('synthetic private detail')

    unit = provider_stt.UnitOutcome('done', 'processed')
    consumer = provider_stt.ProviderSttConsumer(lambda: AsyncStubStage(unit), clock=lambda: 100.0, settled=broken)
    with caplog.at_level(logging.WARNING):
        result = await consumer.process_async(_claim(), lambda: True, _inline)
    assert (result.outcome.value, result.reason.value) == ('done', 'processed')
    assert 'action=merge_wake outcome=failed exception_type=RuntimeError' in caplog.text
    assert 'synthetic private detail' not in caplog.text


def test_the_sync_consumer_and_default_construction_have_no_wake():
    unit = provider_stt.UnitOutcome('done', 'processed')
    consumer = provider_stt.ProviderSttConsumer(lambda: StubStage(unit), clock=lambda: 100.0)
    assert consumer.settled is None
    assert consumer.process(_claim(), lambda: True).outcome.value == 'done'


class Requests:
    def __init__(self):
        self.owners = []

    def request(self, owner_id):
        self.owners.append(owner_id)
        return True


def test_route_wake_requests_a_drain_and_the_switch_turns_it_off(monkeypatch):
    requests = Requests()
    monkeypatch.setattr(route, '_owner_drains', requests)
    route.wake_owner_merge(OWNER)
    assert requests.owners == [OWNER]
    monkeypatch.setenv(SWITCH, 'false')
    route.wake_owner_merge(OWNER)
    assert requests.owners == [OWNER]


@pytest.mark.asyncio
async def test_the_serving_route_builds_its_consumer_with_the_wake(monkeypatch):
    built = []

    async def run_push_async(consumer, outbox, row_id, wake_token, *, now, run_sync):
        built.append(consumer)
        return None

    monkeypatch.setattr(route, 'run_push_async', run_push_async)
    await route.run_delivery_async('p1', 'wake', outbox=object())
    assert built[0].settled is route.wake_owner_merge


# --- the drain itself ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_settled_owner_drain_commits_in_capture_order_and_never_skips_the_head_wait(world, monkeypatch):
    _, store = world
    admit(monkeypatch, store, [item('p1', 10)], 'content-1', JA)
    admit(monkeypatch, store, [item('p2', 20)], 'content-2', JA)
    admit(monkeypatch, store, [item('p3', 30)], 'content-3', JA)
    # The drain reads the wall clock, so the rows become ready "now".
    settle(store, 'p1', now=time.time())
    settle(store, 'p3', now=time.time())
    await Serving(store).drain_settled_async(OWNER)
    # p1 commits; p3 is ready behind the unsettled p2 and has not waited out the head wait.
    assert job(store, 'p1')['state'] == 'committed'
    assert job(store, 'p3')['state'] == 'result_ready' and job(store, 'p2')['merge_pending'] is True
