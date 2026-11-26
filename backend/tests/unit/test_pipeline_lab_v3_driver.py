"""v3 replay: arrival plan, loopback Cloud Tasks and the event loop (pure, with fake ops)."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from testing.pipeline_lab.v3.driver import V3Driver, default_horizon, next_sweep
from testing.pipeline_lab.v3.feed import arrival_instant, partial_points, plan_arrivals, pre_v3_row
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
    # a late lifecycle stamp (a backfill donor's re-finalization) is not the arrival
    late = rec('d', T0, terminal_family_at=(T0 + timedelta(hours=10)).isoformat())
    assert arrival_instant(late) == (T0 + timedelta(minutes=4), 'finished_at+lag')


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


def live_rec(rid, start, *, segments, minutes=4, **extra):
    fields = {
        'created_at': start.isoformat(),
        'transcript_segments': [{'text': f'words {i}', 'start': a, 'end': b} for i, (a, b) in enumerate(segments)],
    }
    fields.update(extra)
    return rec(rid, start, minutes=minutes, **fields)


def test_partial_points_land_each_segment_after_its_end_at_most_once_per_step():
    row = live_rec('a', T0, segments=[(200, 210), (0, 2), (30, 32)])  # out of order on purpose
    final = T0 + timedelta(minutes=5)
    points = partial_points(row, final, step=timedelta(seconds=60), lag=timedelta(seconds=60))
    # lands at +62 s, +92 s (inside the step: waits for the +122 s slot) and +270 s.
    assert points == [
        (T0 + timedelta(seconds=62), 1),
        (T0 + timedelta(seconds=122), 2),
        (T0 + timedelta(seconds=270), 3),
    ]


def test_partial_points_skip_offline_uploads_and_speech_landing_after_the_arrival():
    offline = live_rec('a', T0, segments=[(0, 2)], created_at=(T0 + timedelta(hours=1)).isoformat())
    assert partial_points(offline, T0 + timedelta(hours=2), step=timedelta(seconds=60)) == []
    late = live_rec('b', T0, segments=[(0, 2), (200, 230)])
    assert partial_points(late, T0 + timedelta(seconds=100), step=timedelta(seconds=60)) == [
        (T0 + timedelta(seconds=62), 1)
    ]


def test_plan_with_partials_feeds_them_before_the_finished_capture():
    rows = [live_rec('a', T0, segments=[(0, 2), (120, 125)]), rec('b', T0 + timedelta(minutes=1))]
    plain = plan_arrivals(rows)
    assert [a.partial for a in plain.arrivals] == [False, False]
    plan = plan_arrivals(rows, partial_step=timedelta(seconds=60))
    a_events = [x for x in plan.arrivals if x.recording_id == 'a']
    assert [x.segments for x in a_events] == [1, 2, None]
    assert a_events[-1].instant > a_events[-2].instant and not a_events[-1].partial
    assert a_events[0].words == 2 and a_events[-1].words == 4
    summary = plan.summary()
    assert summary['arrivals'] == 2 and summary['partial_updates'] == 2 and summary['recordings_with_partials'] == 1
    assert 'partial' not in summary['instant_sources']


def test_replay_counts_unspaced_speech_in_partial_and_final_arrivals():
    row = live_rec('a', T0, segments=[(0, 2), (120, 125)])
    row['transcript_segments'][0]['text'] = '日本語の録音'
    row['transcript_segments'][1]['text'] = 'mixed內容'

    arrivals = plan_arrivals([row], partial_step=timedelta(seconds=60)).arrivals

    assert [arrival.words for arrival in arrivals] == [6, 9, 9]


@pytest.mark.asyncio
@pytest.mark.parametrize(('characters', 'visible'), [(149, False), (150, True)])
async def test_fake_replay_and_fate_use_script_aware_count(monkeypatch, characters, visible):
    from testing.pipeline_lab.v3 import fake
    from testing.pipeline_lab.v3.run import recording_fate

    monkeypatch.setattr(fake, 'ask', lambda *a, **kw: {'kind': 'conversation'})
    clock = fake._Clock(T0 + timedelta(minutes=10))
    ops = fake.FakeV3Ops(tasks=LoopbackTasks(clock.now), clock=clock, proxy_url='http://unused.invalid')
    row = rec('r', T0, transcript_segments=[{'text': '話' * characters, 'start': 0, 'end': 2}])
    await ops.arrive('u', plan_arrivals([row]).arrivals[0])

    assert await ops.reconcile('u') == 'committed'
    derived = list(ops.conversations.values())
    assert derived[0]['home_hidden'] is not visible
    assert recording_fate([row], derived)['rows'][0]['words'] == characters


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


def test_replayed_rows_keep_only_conversations_this_replay_planned():
    from testing.pipeline_lab.v3.run import replayed_rows

    rows = [
        {'id': 'old', 'started_at': (T0 - timedelta(days=1)).isoformat(), 'v3_recording_ids': ['prev']},
        {'id': 'spans', 'started_at': (T0 - timedelta(minutes=5)).isoformat(), 'v3_recording_ids': ['prev', 'a']},
        {'id': 'today', 'started_at': T0.isoformat(), 'v3_recording_ids': ['b']},
    ]
    assert [r['id'] for r in replayed_rows(rows, {'a'}, T0)] == ['spans', 'today']


def test_replayed_rows_leave_next_day_conversations_out_like_the_production_baseline():
    # A recording running past midnight: production's baseline keeps only conversations starting in
    # the day, so the replay's next-day part must not show up as replay-only.
    from testing.pipeline_lab.v3.run import replayed_rows

    end = T0 + timedelta(hours=8)
    rows = [
        {'id': 'before', 'started_at': (end - timedelta(minutes=20)).isoformat(), 'v3_recording_ids': ['late']},
        {'id': 'after', 'started_at': (end + timedelta(minutes=7)).isoformat(), 'v3_recording_ids': ['late']},
    ]
    assert [r['id'] for r in replayed_rows(rows, {'late'}, T0, end)] == ['before']
    assert [r['id'] for r in replayed_rows(rows, {'late'}, T0)] == ['before', 'after']


def test_seeded_recording_claims_get_datetimes_back():
    from datetime import datetime

    from testing.pipeline_lab.seed.writer import revive_claim_times

    row = revive_claim_times(
        {'claims': [{'conversation_id': 'c', 'start': '2026-03-14T09:00:00+00:00', 'end': '2026-03-14T09:05:00Z'}]}
    )
    assert all(isinstance(row['claims'][0][k], datetime) for k in ('start', 'end'))
    assert revive_claim_times({'id': 'x'}) == {'id': 'x'}


def test_seeded_v3_time_fields_without_at_suffix_get_datetimes_back():
    from datetime import datetime

    from testing.pipeline_lab.seed.writer import revive_claim_times

    row = revive_claim_times(
        {
            'summary_covers_through': '2026-03-14T09:05:00Z',
            'v3_pending_since': '2026-03-14T09:00:00+00:00',
            'title': '2026-03-14T09:00:00Z',
        }
    )
    assert isinstance(row['summary_covers_through'], datetime) and isinstance(row['v3_pending_since'], datetime)
    assert row['title'] == '2026-03-14T09:00:00Z'
