"""The on-prem scheduled-job runner: dispatch, hour alignment, failure surfacing, and no Firebase.

Until this runner existed our stack ran no scheduled work at all, so two product surfaces were absent:
daily summaries (a persisted document, not just a push) and the canonical memory outbox drain (each
memory write queues two events that nothing consumed). Upstream's own entrypoints could not be reused
because they begin with ``firebase_admin.initialize_app()`` — a Google dependency in a process we run
with OIDC and no service account. That is the assertion this suite exists to hold.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from jobs import onprem_scheduled


def test_both_upstream_jobs_are_dispatchable():
    assert sorted(onprem_scheduled.JOBS) == ['memory-maintenance', 'notifications']


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
    monkeypatch.setattr(onprem_scheduled, 'run_loop', lambda job: seen.append((job, True)) or 0)
    assert onprem_scheduled.main(['--job', 'notifications']) == 0
    assert seen == [('notifications', False)]
    assert onprem_scheduled.main(['--job', 'notifications', '--loop']) == 0
    assert seen[-1] == ('notifications', True)
