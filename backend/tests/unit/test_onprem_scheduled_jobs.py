"""The on-prem scheduled-job runner: dispatch, hour alignment, failure surfacing, and no Firebase.

Until this runner existed our stack ran no scheduled work at all, so two product surfaces were absent:
daily summaries (a persisted document, not just a push) and the canonical memory outbox drain (each
memory write queues two events that nothing consumed). Upstream's own entrypoints could not be reused
because they begin with ``firebase_admin.initialize_app()`` — a Google dependency in a process we run
with OIDC and no service account. That is the assertion this suite exists to hold.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from jobs import onprem_scheduled


def test_every_job_is_dispatchable():
    """Upstream's two hourly jobs, plus the conversation-search indexer that is ours (ADR-0064)."""
    assert sorted(onprem_scheduled.JOBS) == [
        'conversation-search-index',
        'memory-maintenance',
        'notifications',
    ]


def test_run_once_dispatches_the_named_job(monkeypatch):
    called: list[str] = []

    async def fake():
        called.append('ran')

    monkeypatch.setitem(onprem_scheduled.JOBS, 'notifications', fake)
    assert onprem_scheduled.run_once('notifications') == 0
    assert called == ['ran']


def test_a_failing_tick_exits_non_zero(monkeypatch):
    """A CronJob decides success from the exit code; swallowing the error would make a broken queue
    look healthy for as long as nobody reads the logs."""

    async def boom():
        raise RuntimeError('mongo unreachable')

    monkeypatch.setitem(onprem_scheduled.JOBS, 'memory-maintenance', boom)
    assert onprem_scheduled.run_once('memory-maintenance') == 1


def test_the_loop_keeps_ticking_after_a_failure(monkeypatch):
    """One bad hour must not stop every later hour."""
    attempts: list[int] = []

    async def flaky():
        attempts.append(len(attempts))
        if len(attempts) == 1:
            raise RuntimeError('transient')

    monkeypatch.setitem(onprem_scheduled.JOBS, 'notifications', flaky)
    slept: list[float] = []
    exit_code = onprem_scheduled.run_loop('notifications', sleeper=slept.append, ticks=3)
    assert len(attempts) == 3, 'the loop stopped at the first failure'
    assert len(slept) == 3
    assert exit_code == 1, 'a failed tick must still be reported'


@pytest.mark.parametrize(
    'now,expected',
    [
        (datetime(2026, 8, 21, 8, 0, 0, tzinfo=timezone.utc), 3600.0),
        (datetime(2026, 8, 21, 8, 59, 30, tzinfo=timezone.utc), 30.0),
        (datetime(2026, 8, 21, 23, 59, 59, tzinfo=timezone.utc), 1.0),
    ],
)
def test_the_loop_aligns_to_the_top_of_the_hour(now, expected):
    """Upstream's schedule is ``0 * * * *`` and the notifications job buckets users by local hour, so
    a fixed 3600s sleep (which drifts by the run duration every tick) is not equivalent."""
    assert onprem_scheduled.seconds_to_next_hour(now) == pytest.approx(expected, abs=0.01)


def test_the_delay_is_never_zero():
    """Exactly on the boundary the loop must wait an hour, not spin."""
    assert onprem_scheduled.seconds_to_next_hour(datetime(2026, 8, 21, 8, 0, tzinfo=timezone.utc)) > 0


def test_the_runner_never_initialises_firebase(monkeypatch):
    """The whole reason this module exists instead of reusing backend/modal/job.py.

    Behavioural, not a source grep: it drives the real wrapper (only the upstream work body is stubbed)
    and asserts ``firebase_admin.initialize_app`` was never called. The distinction that matters is
    initialisation, not import — the FCM transport imports the SDK either way; what an on-prem process
    with OIDC and no service account cannot do is initialise an app.
    """
    import firebase_admin

    calls: list[object] = []
    monkeypatch.setattr(firebase_admin, 'initialize_app', lambda *a, **k: calls.append(a))

    import utils.other.jobs as upstream_jobs

    ran: list[str] = []

    async def fake_start_job():
        ran.append('body')

    monkeypatch.setattr(upstream_jobs, 'start_job', fake_start_job)

    import asyncio

    asyncio.run(onprem_scheduled._run_notifications())
    assert ran == ['body'], 'the runner did not reach the upstream work body'
    assert calls == [], 'the runner initialised Firebase'


def test_cli_rejects_an_unknown_job():
    with pytest.raises(SystemExit):
        onprem_scheduled.main(['--job', 'not-a-job'])


def test_cli_runs_once_by_default(monkeypatch):
    seen: list[tuple[str, bool]] = []
    monkeypatch.setattr(onprem_scheduled, 'run_once', lambda job: seen.append((job, False)) or 0)
    monkeypatch.setattr(onprem_scheduled, 'run_loop', lambda job, **_kw: seen.append((job, True)) or 0)
    assert onprem_scheduled.main(['--job', 'notifications']) == 0
    assert seen == [('notifications', False)]
    assert onprem_scheduled.main(['--job', 'notifications', '--loop']) == 0
    assert seen[-1] == ('notifications', True)


def test_memory_maintenance_refuses_to_report_success_when_its_switch_is_off(monkeypatch):
    """A scheduled tick that drains nothing must not exit 0.

    MEMORY_CANONICAL_MAINTENANCE_ENABLED defaults to "false" and the upstream run then returns early
    with user_count=0 and errors=0. Found on a live stack: the memory outbox stayed at 2 pending across
    a tick the scheduler reported as successful, which is how a broken queue looks healthy.
    """
    monkeypatch.delenv('MEMORY_CANONICAL_MAINTENANCE_ENABLED', raising=False)
    assert onprem_scheduled.run_once('memory-maintenance') == 1


def test_memory_maintenance_proceeds_when_its_switch_is_on(monkeypatch):
    """The legacy-principal half: the guard must not block a correctly configured deployment."""
    monkeypatch.setenv('MEMORY_CANONICAL_MAINTENANCE_ENABLED', 'true')

    import utils.memory.canonical_short_term_maintenance_cron as cron_mod

    class _Summary:
        user_count = 1
        outbox_delivered_total = 2
        outbox_retryable_failures_total = 0
        outbox_dead_letters_total = 0
        dreamed_users = 1
        errors: list[str] = []

    async def fake_cron(**_kwargs):
        return _Summary()

    monkeypatch.setattr(cron_mod, 'run_canonical_short_term_maintenance_cron', fake_cron)
    assert onprem_scheduled.run_once('memory-maintenance') == 0


def test_the_conversation_search_index_job_is_dispatchable():
    """Ours, not upstream's: the missing writer for the Typesense conversations collection."""
    assert 'conversation-search-index' in onprem_scheduled.JOBS


def test_a_fixed_interval_replaces_the_hour_alignment():
    """Search freshness is user-visible, so that job must not wait up to an hour."""
    slept: list[float] = []

    async def noop():
        return None

    import pytest as _pytest

    monkey = _pytest.MonkeyPatch()
    monkey.setitem(onprem_scheduled.JOBS, 'conversation-search-index', noop)
    try:
        onprem_scheduled.run_loop('conversation-search-index', sleeper=slept.append, ticks=2, interval_seconds=300)
    finally:
        monkey.undo()
    assert slept == [300.0, 300.0]


def test_the_default_cadence_is_still_the_top_of_the_hour():
    slept: list[float] = []

    async def noop():
        return None

    import pytest as _pytest

    monkey = _pytest.MonkeyPatch()
    monkey.setitem(onprem_scheduled.JOBS, 'notifications', noop)
    try:
        onprem_scheduled.run_loop('notifications', sleeper=slept.append, ticks=1)
    finally:
        monkey.undo()
    assert 0 < slept[0] <= 3600


def test_a_nonsense_interval_is_refused():
    with pytest.raises(SystemExit):
        onprem_scheduled.main(['--job', 'notifications', '--loop', '--interval-seconds', '0'])


# --- one process, several cadences (the compose driver) -----------------------------------------


@pytest.mark.parametrize(
    'spec,expected',
    [
        ('notifications=hourly', ('notifications', None)),
        ('notifications', ('notifications', None)),
        ('conversation-search-index=300', ('conversation-search-index', 300)),
        ('memory-maintenance = hourly ', ('memory-maintenance', None)),
    ],
)
def test_a_schedule_spec_parses(spec, expected):
    assert onprem_scheduled.parse_schedule(spec) == expected


@pytest.mark.parametrize('spec', ['nope=hourly', 'notifications=soon', 'notifications=0', 'notifications=-5'])
def test_a_bad_schedule_spec_is_refused_with_the_offending_text(spec):
    """A typo in a compose command must be a startup failure with a readable message, not a job that
    silently never runs."""
    with pytest.raises(ValueError, match='schedule'):
        onprem_scheduled.parse_schedule(spec)


def test_the_scheduler_runs_every_job_on_its_own_cadence():
    import asyncio

    ran: list[str] = []
    slept: list[tuple[str, float]] = []

    def _body(name):
        async def run():
            ran.append(name)

        return run

    monkey = pytest.MonkeyPatch()
    for name in ('notifications', 'conversation-search-index'):
        monkey.setitem(onprem_scheduled.JOBS, name, _body(name))
    current = {'job': None}

    async def sleeper(delay):
        slept.append((current['job'], delay))

    # Wrap _schedule_one so the fake sleeper can attribute each sleep to its job.
    original = onprem_scheduled._schedule_one

    async def traced(job, interval, **kw):
        current['job'] = job
        return await original(job, interval, **kw)

    monkey.setattr(onprem_scheduled, '_schedule_one', traced)
    try:
        code = asyncio.run(
            onprem_scheduled.run_scheduler(
                {'notifications': None, 'conversation-search-index': 300}, sleeper=sleeper, ticks=1
            )
        )
    finally:
        monkey.undo()

    assert code == 0
    assert sorted(ran) == ['conversation-search-index', 'notifications']
    assert 300.0 in [delay for _job, delay in slept], 'the fixed cadence was not used'
    assert any(0 < delay <= 3600 for _job, delay in slept), 'the hourly cadence was not used'


def test_one_failing_job_does_not_stop_the_others():
    """Per-job isolation is the whole reason a single process is acceptable."""
    import asyncio

    ran: list[str] = []

    async def boom():
        raise RuntimeError('typesense down')

    async def fine():
        ran.append('ok')

    monkey = pytest.MonkeyPatch()
    monkey.setitem(onprem_scheduled.JOBS, 'conversation-search-index', boom)
    monkey.setitem(onprem_scheduled.JOBS, 'notifications', fine)

    async def sleeper(_delay):
        return None

    try:
        code = asyncio.run(
            onprem_scheduled.run_scheduler(
                {'conversation-search-index': 1, 'notifications': 1}, sleeper=sleeper, ticks=2
            )
        )
    finally:
        monkey.undo()

    assert ran == ['ok', 'ok'], 'the healthy job stopped ticking'
    assert code == 1, 'the failing job was not reported'


def test_the_cli_refuses_both_or_neither():
    with pytest.raises(SystemExit):
        onprem_scheduled.main([])
    with pytest.raises(SystemExit):
        onprem_scheduled.main(['--job', 'notifications', '--schedule', 'notifications=hourly'])


# --- one process, three jobs: the log must still be readable per job (BACKLOG L39, point 3) ---------


def test_the_tag_filter_stamps_the_running_job_onto_any_record():
    """The filter itself. `_running` is what a tick installs; the filter is what carries it onto a record
    emitted by code that knows nothing about jobs."""
    import logging

    from jobs import onprem_scheduled as jobs

    record = logging.LogRecord('some.library.deep.inside', logging.INFO, __file__, 1, 'work', None, None)

    with jobs._running('memory-maintenance'):
        assert jobs._JobTag().filter(record) is True

    assert record.job == 'memory-maintenance'


def test_the_filter_is_attached_to_the_root_handlers_not_just_this_module():
    """Where it is attached IS the fix. The runner already wrote `job=<name>` into its own lines; the
    work logs through the modules that do it — `utils.other.jobs`, the maintenance planner, the search
    reconciler — and those lines had no marker, so `docker logs` on a process running three jobs was one
    interleaved stream nobody could split. Attaching to this module's logger would have changed nothing.

    An earlier version of this test computed the tag inside its own sink instead of reading what the
    filter had put there, so removing the attachment entirely left it green.
    """
    import logging

    from jobs import onprem_scheduled as jobs

    handlers = logging.getLogger().handlers
    assert handlers, 'no root handler — the format and the filter both hang off it'
    # `any`, not `all`: under pytest the root also carries the framework's own capture handlers, which
    # are not what this pins. What it pins is that the handler this module configured got the filter —
    # delete the attachment loop and nothing on the root has it.
    assert any(
        isinstance(f, jobs._JobTag) for handler in handlers for f in handler.filters
    ), 'no root handler carries the job tag — records from the work itself go out unattributed'


def test_outside_a_tick_the_tag_is_not_some_other_job():
    """A stale tag is worse than none: it attributes a line to a job that is not running.

    Both ticks run inside ONE event loop and one context. An earlier version called `asyncio.run` per
    tick, which starts a fresh context — the variable could never have leaked, so the test passed with
    the reset deleted.
    """
    from jobs import onprem_scheduled as jobs

    seen: list = []

    async def watcher():
        pass

    async def scenario():
        with patch.dict(jobs.JOBS, {'first': watcher, 'second': watcher}):
            await jobs.run_once_async('first')
            seen.append(jobs._current_job.get())
            await jobs.run_once_async('second')
            seen.append(jobs._current_job.get())

    asyncio.run(scenario())

    assert seen == ['-', '-'], f'the tag outlived its tick: {seen}'


def test_a_job_that_blocks_the_shared_loop_is_named(caplog):
    """THE CONSTRAINT MADE MECHANICAL (point 5). Three jobs share one loop, so a body doing synchronous
    I/O in the loop stops the other two from ticking — and nothing reported it. The three current bodies
    are clean; this is what stops a fourth from breaking it silently."""
    import logging
    import time as real_time

    from jobs import onprem_scheduled as jobs

    async def blocking_body():
        real_time.sleep(jobs._LOOP_STALL_WARNING_SECONDS + jobs._LOOP_STALL_PROBE_SECONDS + 0.3)

    with caplog.at_level(logging.WARNING), patch.dict(jobs.JOBS, {'greedy': blocking_body}):
        assert asyncio.run(jobs.run_once_async('greedy')) == 0

    stalls = [r for r in caplog.records if 'blocked the shared event loop' in r.getMessage()]
    assert stalls, 'a body that blocked the loop for over a second was not reported'
    assert 'job=greedy' in stalls[0].getMessage()


def test_a_well_behaved_job_is_not_accused():
    """An alarm that fires on a job doing its work properly gets muted, and then it protects nothing."""
    import logging

    from jobs import onprem_scheduled as jobs

    async def polite_body():
        await asyncio.sleep(jobs._LOOP_STALL_PROBE_SECONDS * 3)

    warnings: list = []

    class _Sink(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.WARNING:
                warnings.append(record.getMessage())

    sink = _Sink()
    logging.getLogger('onprem_scheduled').addHandler(sink)
    try:
        with patch.dict(jobs.JOBS, {'polite': polite_body}):
            assert asyncio.run(jobs.run_once_async('polite')) == 0
    finally:
        logging.getLogger('onprem_scheduled').removeHandler(sink)

    assert not [w for w in warnings if 'blocked the shared event loop' in w]
