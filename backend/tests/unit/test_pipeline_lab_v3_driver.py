"""v3 replay: arrival plan, loopback Cloud Tasks and the event loop (pure, with fake ops)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from testing.pipeline_lab.v3.driver import V3Driver, default_horizon, next_sweep
from testing.pipeline_lab.v3.feed import arrival_instant, plan_arrivals, pre_v3_row
from testing.pipeline_lab.v3.tasks import RECONCILE_PATH, LoopbackTasks

T0 = datetime(2026, 3, 14, 9, 0, tzinfo=timezone.utc)


def rec(rid, start, minutes=3, **extra):
    row = {
        'id': rid,
        'started_at': start.isoformat(),
        'finished_at': (start + timedelta(minutes=minutes)).isoformat(),
        'status': 'completed',
        'source': 'omi',
        'transcript_segments': [{'text': 'hello there friend', 'start': 0, 'end': 2}],
    }
    row.update(extra)
    return row


# ---- feed -------------------------------------------------------------------------------


def test_arrival_instant_prefers_terminal_then_sealed_then_finished():
    terminal = (T0 + timedelta(minutes=9)).isoformat()
    row = rec('r', T0, terminal_family_at=terminal, record_sealed_at=(T0 + timedelta(minutes=4)).timestamp())
    assert arrival_instant(row) == (T0 + timedelta(minutes=9), 'terminal_family_at')
    del row['terminal_family_at']
    assert arrival_instant(row) == (T0 + timedelta(minutes=5), 'record_sealed_at+lag')
    del row['record_sealed_at']
    assert arrival_instant(row) == (T0 + timedelta(minutes=4), 'finished_at+lag')
    row['terminal_family_at'] = terminal
    assert arrival_instant(row, mode='finish') == (T0 + timedelta(minutes=4), 'finished_at+lag')
    with pytest.raises(ValueError):
        arrival_instant(row, mode='bogus')


def test_plan_orders_by_instant_and_skips_unusable_rows():
    rows = [
        rec('late', T0 + timedelta(hours=1)),
        rec('early', T0),
        rec('gone', T0, deleted=True),
        rec('merged', T0, sync_merged_into='x'),
        rec('live', T0, status='in_progress', transcript_segments=[]),
        rec('donor', T0 + timedelta(minutes=30), v3_backfill_run='run-1', v3_manual_end=True),
    ]
    plan = plan_arrivals(rows)
    assert [a.recording_id for a in plan.arrivals] == ['early', 'donor', 'late']
    assert plan.skipped == {'deleted': ['gone'], 'merged_away': ['merged'], 'in_progress_no_speech': ['live']}
    donor = plan.arrivals[1]
    assert donor.backfill_donor and donor.manual_end and donor.words == 3
    summary = plan.summary()
    assert summary['arrivals'] == 3 and summary['backfill_donors'] == 1 and summary['skipped']['deleted'] == 1


def test_pre_v3_row_keeps_capture_facts_only():
    row = rec(
        'r',
        T0,
        recording=True,
        v3_pending=True,
        claims=[{'conversation_id': 'x'}],
        v3_backfill_run='run',
        home_hidden=True,
        kind='background',
        audio_files=[{'id': 'a'}],
        recorded_start=T0.isoformat(),
        structured={'title': 'old'},
    )
    out = pre_v3_row(row)
    assert out['status'] == 'in_progress' and out['structured'] == {} and out['discarded'] is False
    assert out['audio_files'] == [{'id': 'a'}] and out['recorded_start'] == T0.isoformat()
    for gone in ('recording', 'v3_pending', 'claims', 'v3_backfill_run', 'home_hidden', 'kind'):
        assert gone not in out


# ---- loopback tasks ------------------------------------------------------------------------


class Clock:
    def __init__(self, now):
        self._now = now
        self.history = []

    def set(self, instant):
        self.history.append(instant)
        self._now = instant

    def now(self):
        return self._now


def test_loopback_tasks_dedupe_names_and_keep_schedule():
    clock = Clock(T0)
    log = []
    tasks = LoopbackTasks(clock.now, log=log.append)
    url = 'http://lab.invalid' + RECONCILE_PATH
    tasks.enqueue('q', url, 'n1', {'uid': 'u'}, schedule_at=int((T0 + timedelta(minutes=5)).timestamp()))
    tasks.enqueue('q', url, 'n1', {'uid': 'u'})
    tasks.enqueue('q', url, 'n0', {'uid': 'u'})
    assert (tasks.created, tasks.duplicates) == (2, 1)
    assert [row['outcome'] for row in log] == ['created', 'duplicate', 'created']
    assert tasks.pop_due(T0.timestamp()).name == 'n0'
    assert tasks.pop_due(T0.timestamp()) is None
    task = tasks.pop_due((T0 + timedelta(minutes=5)).timestamp())
    assert task.name == 'n1' and task.path == RECONCILE_PATH and task.payload == {'uid': 'u'}


def test_next_sweep_is_the_next_five_minute_grid_point():
    assert next_sweep(T0) == T0 + timedelta(minutes=5)
    assert next_sweep(T0 + timedelta(minutes=7, seconds=3)) == T0 + timedelta(minutes=10)


# ---- driver ------------------------------------------------------------------------------


class FakeOps:
    """Arrival -> enqueue a reconcile now; reconcile -> one continuation 5 minutes later, once."""

    def __init__(self, tasks, clock, *, pending_after=0, fail_on=None):
        self.tasks, self.clock = tasks, clock
        self.calls = []
        self.pending_after = pending_after
        self.fail_on = fail_on
        self.continued = False

    def _enqueue(self, at, suffix=''):
        name = f'v3-{int(at.timestamp()) // 60}{suffix}'
        self.tasks.enqueue(
            'q', 'http://lab.invalid' + RECONCILE_PATH, name, {'uid': 'u'}, schedule_at=int(at.timestamp())
        )

    async def arrive(self, uid, arrival):
        self.calls.append(('arrive', arrival.recording_id, self.clock.now()))
        if arrival.recording_id == self.fail_on:
            raise RuntimeError('boom')
        self._enqueue(self.clock.now())
        return {'outcome': 'recording', 'disposition': 'completed'}

    async def reconcile(self, uid):
        self.calls.append(('reconcile', None, self.clock.now()))
        if not self.continued:
            self.continued = True
            self._enqueue(self.clock.now() + timedelta(minutes=5))
        return 'committed'

    async def sweep(self):
        self.calls.append(('sweep', None, self.clock.now()))
        return 0

    def pending(self, uid):
        # True for the first ``pending_after`` checks (one check follows every event).
        if self.pending_after > 0:
            self.pending_after -= 1
            return True
        return False

    async def settle(self):
        return {'left': 0}


def run_driver(rows, *, horizon=None, **ops_kwargs):
    plan = plan_arrivals(rows)
    clock = Clock(T0 - timedelta(hours=1))
    tasks = LoopbackTasks(clock.now)
    ops = FakeOps(tasks, clock, **ops_kwargs)
    driver = V3Driver(
        uid='u',
        ops=ops,
        tasks=tasks,
        clock=clock,
        horizon=horizon or default_horizon(plan.arrivals, T0 + timedelta(hours=3)),
    )
    report = asyncio.run(driver.run(plan.arrivals))
    return report, ops, clock, tasks


def test_driver_runs_arrivals_and_due_tasks_in_virtual_time():
    rows = [rec('a', T0), rec('b', T0 + timedelta(minutes=30))]
    report, ops, clock, _ = run_driver(rows)
    kinds = [(k, rid) for k, rid, _ in ops.calls]
    assert kinds == [('arrive', 'a'), ('reconcile', None), ('reconcile', None), ('arrive', 'b'), ('reconcile', None)]
    times = [at for _, _, at in ops.calls]
    assert times == sorted(times)  # the virtual clock never runs backwards
    assert times[2] - times[1] == timedelta(minutes=5)  # the continuation ran at its schedule
    assert report.summary()['status'] == 'ok' and report.summary()['counts']['task'] == {'committed': 3}
    assert clock.history == sorted(clock.history)


def test_driver_records_failures_and_keeps_going():
    rows = [rec('a', T0), rec('b', T0 + timedelta(minutes=30))]
    report, ops, _, _ = run_driver(rows, fail_on='a')
    first = report.events[0]
    assert first.kind == 'arrival' and first.outcome == 'error' and first.error == 'RuntimeError'
    assert [c[1] for c in ops.calls if c[0] == 'arrive'] == ['a', 'b']
    assert report.summary()['status'] == 'partial'


def test_driver_never_moves_clock_backwards_when_work_overruns():
    class SlowClock(Clock):
        def set(self, instant):
            super().set(instant)
            self._now = instant + timedelta(minutes=20)  # every event "takes" 20 virtual minutes

    plan = plan_arrivals([rec('a', T0), rec('b', T0 + timedelta(minutes=1))])
    clock = SlowClock(T0 - timedelta(hours=1))
    tasks = LoopbackTasks(clock.now)
    ops = FakeOps(tasks, clock)
    asyncio.run(
        V3Driver(uid='u', ops=ops, tasks=tasks, clock=clock, horizon=T0 + timedelta(hours=5)).run(plan.arrivals)
    )
    starts = [at for _, _, at in ops.calls]
    assert starts == sorted(starts)


def test_driver_sweeps_only_while_pending_and_stops_at_horizon():
    rows = [rec('a', T0)]
    report, ops, _, _ = run_driver(rows, pending_after=100, horizon=T0 + timedelta(minutes=30))
    sweeps = [at for kind, _, at in ops.calls if kind == 'sweep']
    assert sweeps and all(at.minute % 5 == 0 and at.second == 0 for at in sweeps)
    assert all(at <= T0 + timedelta(minutes=30) for at in sweeps)
    assert report.stopped == 'drained'
    quiet, ops2, _, _ = run_driver(rows, pending_after=0, horizon=T0 + timedelta(minutes=30))
    assert not [c for c in ops2.calls if c[0] == 'sweep']


def test_driver_reports_tasks_it_does_not_run():
    clock = Clock(T0)
    tasks = LoopbackTasks(clock.now)
    tasks.enqueue('q', 'http://lab.invalid/v1/conversations-v3/backfill', 'b1', {'uid': 'u'})
    ops = FakeOps(tasks, clock)
    report = asyncio.run(V3Driver(uid='u', ops=ops, tasks=tasks, clock=clock, horizon=T0 + timedelta(hours=1)).run([]))
    assert report.events[0].outcome == 'unsupported' and report.warnings


def test_driver_stops_at_max_events():
    rows = [rec(f'r{i}', T0 + timedelta(minutes=10 * i)) for i in range(5)]
    plan = plan_arrivals(rows)
    clock = Clock(T0)
    tasks = LoopbackTasks(clock.now)
    ops = FakeOps(tasks, clock)
    report = asyncio.run(
        V3Driver(uid='u', ops=ops, tasks=tasks, clock=clock, horizon=T0 + timedelta(hours=5), max_events=3).run(
            plan.arrivals
        )
    )
    assert report.stopped == 'max_events' and len(report.events) == 3
