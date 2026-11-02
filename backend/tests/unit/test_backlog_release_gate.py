"""Automatic held-audio release limits (David, 2026-11-02; synthetic only)."""

from unittest.mock import Mock

import pytest

from config.backlog_release import IDLE_MAX_DEEP_READY, IDLE_MAX_FRESH_RECENT_READY, OWNER_HOURS_PER_DAY, PRIORITY_HOURS
from config.batch_pipeline import Priority
from config.rate_card import recording_units_per_hour
from database import backlog_release_budget as budget
from utils import backlog_release as release

RATE = float(recording_units_per_hour('batch'))
NOW = 1_793_664_000.0  # a fixed UTC moment; only the day string is derived from it
DAY = '2026-11-03'


def decide(job, hours=1.0, *, idle=True, fleet=True, batch=True, kind='audio'):
    return release.decide(
        'synthetic',
        job,
        hours * RATE,
        kind=kind,
        now=NOW,
        batch_serving=lambda uid: batch,
        idle_now=lambda: idle,
        reserve_fleet=lambda seconds: fleet,
    )


def test_kill_switch_stops_everything_including_priority_hours(monkeypatch):
    monkeypatch.setenv('BACKLOG_RELEASE_ENABLED', 'false')
    decision = decide({'release_priority_units': PRIORITY_HOURS * RATE})
    assert (decision.allowed, decision.reason) == (False, 'kill_switch')


def test_kill_switch_is_on_unless_set_off(monkeypatch):
    monkeypatch.delenv('BACKLOG_RELEASE_ENABLED', raising=False)
    assert decide({}).allowed


def test_priority_hours_ignore_idle_and_spend_down():
    decision = decide({'release_priority_units': PRIORITY_HOURS * RATE}, idle=False)
    assert decision.allowed and decision.normal_priority
    assert decision.updates['release_priority_units'] == pytest.approx((PRIORITY_HOURS - 1) * RATE)


def test_after_priority_hours_a_busy_fleet_refuses():
    decision = decide({'release_priority_units': 0}, idle=False)
    assert (decision.allowed, decision.reason) == (False, 'not_idle')


def test_after_priority_hours_idle_runs_deep():
    decision = decide({}, idle=True)
    assert decision.allowed and not decision.normal_priority
    assert decision.updates == {'release_day': DAY, 'release_day_units': pytest.approx(RATE)}


def test_owner_daily_limit_refuses_and_resets_next_day():
    spent = {'release_day': DAY, 'release_day_units': OWNER_HOURS_PER_DAY * RATE}
    assert decide(spent).reason == 'owner_day'
    assert decide({**spent, 'release_day': '2026-11-02'}).allowed


def test_one_long_recording_can_run_alone_on_an_unspent_day():
    assert decide({}, hours=OWNER_HOURS_PER_DAY + 1).allowed


def test_fleet_budget_refusal_changes_nothing():
    decision = decide({}, fleet=False)
    assert (decision.allowed, decision.reason, decision.updates) == (False, 'fleet_budget', {})


def test_a_refusal_earlier_in_line_spends_no_fleet_budget():
    fleet = Mock(return_value=True)
    release.decide(
        'synthetic', {}, RATE, now=NOW, batch_serving=lambda uid: True, idle_now=lambda: False, reserve_fleet=fleet
    )
    fleet.assert_not_called()


def test_while_legacy_serves_the_owner_nothing_is_released_not_even_priority_hours():
    """Legacy recovery runs on the live Parakeet pool or a vendor, which the idle gate cannot see."""
    fleet = Mock(return_value=True)
    decision = release.decide(
        'synthetic',
        {'release_priority_units': PRIORITY_HOURS * RATE},
        RATE,
        now=NOW,
        batch_serving=lambda uid: False,
        idle_now=lambda: True,
        reserve_fleet=fleet,
    )
    assert (decision.allowed, decision.reason, decision.updates) == (False, 'legacy_route', {})
    fleet.assert_not_called()


def test_batch_serves_reads_the_owners_legacy_mode(monkeypatch):
    from utils.sync import legacy_dark

    modes = {'on-owner': legacy_dark.LegacySyncMode.ON, 'dark-owner': legacy_dark.LegacySyncMode.DARK}
    monkeypatch.setattr(legacy_dark, 'current_mode', lambda uid=None: modes[uid])
    assert release.batch_serves('on-owner') is False
    assert release.batch_serves('dark-owner') is True


def test_a_deferred_summary_skips_the_gpu_checks_but_spends_the_day_and_fleet():
    decision = decide({'release_priority_units': PRIORITY_HOURS * RATE}, kind='text', idle=False, batch=False)
    assert decision.allowed and not decision.normal_priority
    assert 'release_priority_units' not in decision.updates
    assert decision.updates['release_day_units'] == pytest.approx(RATE)
    assert decide({}, kind='text', fleet=False).reason == 'fleet_budget'
    spent = {'release_day': DAY, 'release_day_units': OWNER_HOURS_PER_DAY * RATE}
    assert decide(spent, kind='text').reason == 'owner_day'


def counts(fresh=0, recent=0, deep=0):
    table = {int(Priority.FRESH): fresh, int(Priority.RECENT): recent, int(Priority.DEEP): deep}
    return lambda priority, now: table[priority]


@pytest.mark.parametrize(
    'fresh,recent,deep,expected',
    [
        (0, 0, 0, True),
        (IDLE_MAX_FRESH_RECENT_READY - 1, 0, IDLE_MAX_DEEP_READY - 1, True),
        (IDLE_MAX_FRESH_RECENT_READY, 0, 0, False),
        (32, 32, 0, False),
        (0, 0, IDLE_MAX_DEEP_READY, False),
    ],
)
def test_idle_is_the_ready_count_below_the_replica_floor(fresh, recent, deep, expected):
    assert release.IdleGate(counts(fresh, recent, deep), clock=lambda: NOW).idle() is expected


def test_idle_bound_cannot_scale_the_four_replica_floor():
    assert IDLE_MAX_FRESH_RECENT_READY + IDLE_MAX_DEEP_READY < 4 * 32


def test_idle_sample_failure_with_no_history_is_not_idle():
    def broken(priority, now):
        raise RuntimeError('no index')

    assert release.IdleGate(broken, clock=lambda: NOW).idle() is False


def test_idle_sample_is_cached_between_reads():
    count = Mock(return_value=0)
    gate = release.IdleGate(count, clock=lambda: NOW)
    assert gate.idle() and gate.idle()
    assert count.call_count == 3


def test_idle_keeps_a_recent_answer_through_a_failure_then_closes():
    clock = {'now': NOW}
    healthy = {'ok': True}

    def count(priority, now):
        if not healthy['ok']:
            raise RuntimeError('unavailable')
        return 0

    gate = release.IdleGate(count, clock=lambda: clock['now'])
    assert gate.idle()
    healthy['ok'] = False
    clock['now'] = NOW + 60
    assert gate.idle() is True
    clock['now'] = NOW + 600
    assert gate.idle() is False


def test_budget_fails_closed_when_redis_fails():
    redis = Mock()
    redis.eval.side_effect = RuntimeError('down')
    assert budget.reserve(60.0, redis_client=redis) is False


def test_budget_grants_only_on_an_exact_one():
    redis = Mock()
    redis.eval.return_value = 1
    assert budget.reserve(60.0, redis_client=redis) is True
    redis.eval.return_value = 0
    assert budget.reserve(60.0, redis_client=redis) is False


def test_budget_rejects_a_bad_cost_without_calling_redis():
    redis = Mock()
    assert budget.reserve(float('nan'), redis_client=redis) is False
    redis.eval.assert_not_called()


async def test_held_audio_takes_normal_priority_only_when_granted_and_never_the_vendor_table(monkeypatch, tmp_path):
    from pathlib import Path
    from types import SimpleNamespace
    from utils.batch_pipeline import cap_hold_admission as admission, intake
    from utils.sync import cap_hold

    seen = []

    async def accept(**kwargs):
        seen.append(kwargs)
        return None

    async def immediate(pool, fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(intake, 'accept_upload', accept)
    monkeypatch.setattr('utils.executors.run_blocking', immediate)
    monkeypatch.setattr(admission, 'eligible', lambda row: True)
    monkeypatch.setattr(admission, 'held_content_id', lambda uid, hold: 'c' * 40, raising=False)
    monkeypatch.setattr(cap_hold, 'metadata', lambda uid, row: {'timestamp': 1.0, 'source': 'omi'})
    monkeypatch.setattr(
        cap_hold, 'recovery_directory', lambda uid: SimpleNamespace(name=str(tmp_path), cleanup=lambda: None)
    )
    monkeypatch.setattr(cap_hold, 'read_audio', lambda uid, row, path: Path(path).touch())
    snapshot = SimpleNamespace(id='hold')

    await admission.admit_held('synthetic', snapshot, {})
    token = release.normal_priority.set(True)
    source = release.source.set('trial')
    try:
        await admission.admit_held('synthetic', snapshot, {})
    finally:
        release.source.reset(source)
        release.normal_priority.reset(token)

    assert [row['recording_age_seconds'] for row in seen] == [None, 0]
    assert [row['vendor_table'] for row in seen] == [False, False]
    # A manual tap is untagged; an automatic release carries its source to the batch rows.
    assert [row['release'] for row in seen] == [None, 'trial']


def test_admission_tags_every_released_row_and_leaves_others_untagged():
    from database import batch_pipeline_intake
    from utils.batch_pipeline.contracts import ProjectionBinding, WorkItem

    def admitted(intake):
        rows = {}

        class Tx:
            def get(self, collection, key):
                return dict(rows.get((collection, key), {}))

            def put(self, collection, key, value):
                rows[(collection, key)] = dict(value)

            def patch(self, collection, key, value):
                rows.setdefault((collection, key), {}).update(value)

        class Store:
            def run(self, fn):
                return fn(Tx())

        items = [
            WorkItem(
                f'seg-{index}',
                'synthetic',
                1.0 + index,
                f'gs://bucket/{index}',
                30.0,
                Priority.DEEP,
                privacy_generation=0,
            )
            for index in range(2)
        ]
        binding = ProjectionBinding(
            owner_id='synthetic',
            job_id='job',
            content_id='content',
            segment_ids=tuple(item.segment_id for item in items),
            source='omi',
        )

        def enqueue(tx, item, now, *, policy):
            tx.put('jobs', item.segment_id, {'state': 'ready', 'policy': {}})
            return True

        policy = Mock(batch_enabled=True, provider_reason=None)
        batch_pipeline_intake.admit(
            Store(), items, binding, 10.0, namespace='ns', intake=intake, policy=policy, enqueue=enqueue
        )
        return [row for (collection, _), row in rows.items() if collection == 'jobs']

    assert [row.get('release') for row in admitted({'lane': 'backfill', 'release': 'trial'})] == ['trial', 'trial']
    assert [row.get('release') for row in admitted({'lane': 'backfill'})] == [None, None]
