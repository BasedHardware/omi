"""On-prem runner for the scheduled work upstream hosts as Cloud Run Jobs (ADR-0062).

Upstream runs exactly two periodic jobs, both hourly, declared in ``backend/deploy/runtime_env.yaml``
and driven by Cloud Scheduler (``scripts/validate_memory_maintenance_scheduler.py`` pins the contract
at ``0 * * * *``). Our deployment has neither Cloud Scheduler nor Cloud Run Jobs, and until this module
existed it ran **no** scheduled work at all — so two product surfaces were simply absent:

  notifications        daily notifications AND the daily summary. The summary is a PERSISTED document
                       (``daily_summaries_db.create_daily_summary``, utils/other/notifications.py), so
                       without this job ``/v1/users/daily-summaries`` stays empty forever — the feature
                       does not exist, rather than a push being missed. Also carries a weekly read-only
                       health verdict and the X connector sync (both self-gating).
  memory-maintenance   drains the canonical memory outbox, so a written memory gets its projection and
                       its vector; plus consolidation ("dreaming", needs an LLM endpoint), the
                       short-term TTL audit, and the recurrence-inbox drain. Each memory write queues
                       two outbox events; with no consumer they stay pending forever.

This module is a **runner, not a reimplementation**: it calls the same function bodies upstream's own
entrypoints call. The reason it exists at all is that those entrypoints (``backend/modal/job.py`` and
``backend/modal/memory_maintenance_job.py``) open with ``firebase_admin.initialize_app()``, which is a
Google dependency in a process we run on-prem with OIDC and no service account. Measured: the work
underneath is storage-neutral and completes with no Firebase init at all.

It lives in ``backend/jobs/`` because that is already **upstream's own** home for job code
(``short_term_lifecycle_worker.py`` sits next to it), and because the guards cover it there. It
deliberately does NOT live in ``backend/scripts/``: ADR-0023 excludes that directory from the boundary
guards while two of its modules are already reachable from the runtime import graph, so the exclusion's
premise is false there (BACKLOG L12). Nothing else in this package is touched — upstream's
``__init__.py`` stays empty.

Two drivers, one entrypoint:

  Kubernetes   a native CronJob per job (deploy/onprem/helm/.../templates/scheduled-jobs.yaml), one
               process per tick, exit code decides success.
  Compose      the same command with ``--loop``, because compose has no scheduler. The loop sleeps to
               the next top of the hour rather than sleeping a fixed 3600s, so ticks stay aligned
               across restarts and do not drift.

Usage:
    python -m jobs.onprem_scheduled --job notifications
    python -m jobs.onprem_scheduled --job memory-maintenance --loop
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
logger = logging.getLogger('onprem_scheduled')


async def _run_notifications() -> None:
    """Upstream's hourly notifications job, minus the Firebase init of backend/modal/job.py."""
    from utils.other.jobs import start_job

    await start_job()


async def _run_memory_maintenance() -> None:
    """Upstream's hourly memory maintenance, with the same two recurrence callables its job passes.

    Raises when the run reports errors, so a CronJob tick fails visibly instead of exiting 0 with a
    drained-nothing summary — the failure mode that makes a broken queue look healthy.
    """
    from utils.memory.canonical_short_term_maintenance_cron import (
        canonical_maintenance_enabled,
        run_canonical_short_term_maintenance_cron,
    )
    from utils.task_intelligence.workstream_association import (
        drain_recurrence_inbox_for_maintenance,
        persist_recurrence_signals_for_maintenance,
    )

    # MEMORY_CANONICAL_MAINTENANCE_ENABLED defaults to "false", and with it off the run returns early
    # with user_count=0 and errors=0 -- a GREEN tick that drained nothing. Found exactly that way on a
    # live stack: the outbox stayed at 2 pending across a tick the scheduler reported as successful.
    # Scheduling this job and switching its work off is a misconfiguration, so say so instead of
    # succeeding quietly; an operator who wants no maintenance disables the CronJob.
    if not canonical_maintenance_enabled():
        raise RuntimeError(
            'MEMORY_CANONICAL_MAINTENANCE_ENABLED is not true, so this job would drain nothing and '
            'still report success. Set it (alongside MEMORY_ENABLED=on) or disable the scheduled job.'
        )

    summary = await run_canonical_short_term_maintenance_cron(
        recurrence_signal_persister=persist_recurrence_signals_for_maintenance,
        recurrence_signal_consumer=drain_recurrence_inbox_for_maintenance,
    )
    logger.info(
        'memory-maintenance users=%s outbox_delivered=%s outbox_retryable=%s dead_letters=%s dreamed=%s',
        summary.user_count,
        summary.outbox_delivered_total,
        summary.outbox_retryable_failures_total,
        summary.outbox_dead_letters_total,
        summary.dreamed_users,
    )
    if summary.errors:
        raise RuntimeError(f'memory-maintenance completed with {len(summary.errors)} error(s): {summary.errors[:3]}')


async def _run_conversation_search_index() -> None:
    """Ours, not upstream's: the writer for the Typesense `conversations` collection (ADR-0064).

    Upstream fills that collection from a Firestore -> Typesense pipeline outside the codebase, so on-prem
    it stayed empty and conversation search (and the app's DATE browse, which uses the same endpoint) had
    nothing to find. Unlike the other two this is not hourly work: search freshness is user-visible, so its
    driver runs it every few minutes with ``--interval-seconds``.
    """
    from utils.conversations.search_index_sync import reconcile_conversation_search_index

    report = await asyncio.to_thread(reconcile_conversation_search_index)
    logger.info('conversation-search-index %s', report.as_log())
    if report.errors:
        raise RuntimeError(
            f'conversation-search-index completed with {len(report.errors)} error(s): {report.errors[:3]}'
        )


JOBS: Dict[str, Callable[[], Awaitable[None]]] = {
    'notifications': _run_notifications,
    'memory-maintenance': _run_memory_maintenance,
    'conversation-search-index': _run_conversation_search_index,
}


def seconds_to_next_hour(now: datetime) -> float:
    """Seconds until the next top of the hour (UTC), never 0.

    Sleeping a fixed 3600s would drift by the run duration on every tick, so a container restarted at
    :59 would settle into ticking at a random minute. Upstream's schedule is ``0 * * * *`` and the
    notifications job's own hour bucketing assumes it fires near the top of the hour.
    """
    next_hour = (now.astimezone(timezone.utc) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return max(1.0, (next_hour - now.astimezone(timezone.utc)).total_seconds())


async def run_once_async(job: str) -> int:
    """Run one tick inside an existing event loop. Returns 0/1; never raises."""
    started = time.monotonic()
    try:
        await JOBS[job]()
    except Exception:
        logger.exception('job=%s FAILED after %.1fs', job, time.monotonic() - started)
        return 1
    logger.info('job=%s ok in %.1fs', job, time.monotonic() - started)
    return 0


def run_once(job: str) -> int:
    """Run one tick as a whole process. Returns an exit code; never raises."""
    return asyncio.run(run_once_async(job))


def run_loop(
    job: str,
    *,
    sleeper: Callable[[float], None] = time.sleep,
    ticks: int | None = None,
    interval_seconds: int | None = None,
) -> int:
    """Tick forever (or ``ticks`` times, for tests).

    Without ``interval_seconds`` the cadence is the top of every hour, matching upstream's schedule. With
    it, a fixed interval — for work whose freshness a user notices (the conversation search index), where
    waiting up to an hour is the wrong trade.

    A failing tick is logged and the loop continues: one bad tick must not stop every later one. The exit
    code reports whether any tick failed, which only matters for the bounded (test) form.
    """
    failures = 0
    remaining = ticks
    while remaining is None or remaining > 0:
        if interval_seconds is None:
            delay: float = seconds_to_next_hour(datetime.now(timezone.utc))
            logger.info('job=%s sleeping %.0fs until the next hour', job, delay)
        else:
            delay = float(interval_seconds)
            logger.info('job=%s sleeping %.0fs (fixed interval)', job, delay)
        sleeper(delay)
        failures += run_once(job)
        if remaining is not None:
            remaining -= 1
    return 1 if failures else 0


HOURLY = 'hourly'


def parse_schedule(spec: str) -> Tuple[str, Optional[int]]:
    """``name=hourly`` or ``name=<seconds>`` -> (job, interval or None for top-of-hour).

    Raises ValueError with the offending text, so a typo in a compose command is a startup failure with a
    readable message rather than a job that silently never runs.
    """
    name, separator, cadence = spec.partition('=')
    name = name.strip()
    cadence = cadence.strip() or HOURLY
    if not separator:
        cadence = HOURLY
    if name not in JOBS:
        raise ValueError(f'unknown job {name!r} in --schedule {spec!r}; known: {", ".join(sorted(JOBS))}')
    if cadence == HOURLY:
        return name, None
    try:
        seconds = int(cadence)
    except ValueError:
        raise ValueError(f'bad cadence {cadence!r} in --schedule {spec!r}; use "hourly" or a number of seconds')
    if seconds < 1:
        raise ValueError(f'cadence must be >= 1 second in --schedule {spec!r}')
    return name, seconds


async def _schedule_one(
    job: str,
    interval_seconds: Optional[int],
    *,
    sleeper: Any,
    ticks: Optional[int],
) -> int:
    """One job's own loop. Sleeps first, so a restart does not stampede every job at once."""
    failures = 0
    remaining = ticks
    while remaining is None or remaining > 0:
        if interval_seconds is None:
            delay: float = seconds_to_next_hour(datetime.now(timezone.utc))
            logger.info('job=%s sleeping %.0fs until the next hour', job, delay)
        else:
            delay = float(interval_seconds)
            logger.info('job=%s sleeping %.0fs (fixed interval)', job, delay)
        await sleeper(delay)
        failures += await run_once_async(job)
        if remaining is not None:
            remaining -= 1
    return 1 if failures else 0


async def run_scheduler(
    schedules: Dict[str, Optional[int]],
    *,
    sleeper: Any = asyncio.sleep,
    ticks: Optional[int] = None,
) -> int:
    """Run several jobs on their own cadences in ONE process.

    Compose has no scheduler, and three containers for three jobs is three copies of the same image, the
    same env and the same restart policy for fifteen lines of sleeping. One process with one task per job
    is the same behaviour with a third of the surface. Kubernetes keeps a native CronJob per job instead:
    there a scheduler exists, and per-job history and retry are worth having.

    Isolation is per job: a failing tick is logged and only that job's loop continues to its next tick, so
    one broken job never stops the others.
    """
    described = ', '.join(
        f'{job}={"hourly" if interval is None else f"{interval}s"}' for job, interval in sorted(schedules.items())
    )
    logger.info('scheduler starting: %s', described)
    results = await asyncio.gather(
        *(_schedule_one(job, interval, sleeper=sleeper, ticks=ticks) for job, interval in schedules.items()),
        return_exceptions=True,
    )
    failed = 0
    for job, result in zip(schedules, results):
        if isinstance(result, BaseException):
            logger.error('job=%s loop crashed: %s', job, result)
            failed = 1
        else:
            failed = failed or result
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', choices=sorted(JOBS), help='run ONE job (once, or with --loop)')
    parser.add_argument(
        '--schedule',
        action='append',
        metavar='JOB=hourly|SECONDS[,JOB=...]',
        help='run several jobs in ONE process on their own cadences (compose; k8s uses a CronJob per job). '
        'Repeatable, and each value may be a comma-separated list — so the whole set can come from one '
        'environment variable instead of an edited command. Mutually exclusive with --job.',
    )
    parser.add_argument(
        '--loop',
        action='store_true',
        help='tick repeatedly instead of running once (compose; k8s uses a CronJob)',
    )
    parser.add_argument(
        '--interval-seconds',
        type=int,
        default=None,
        help='with --loop, tick every N seconds instead of at the top of the hour',
    )
    args = parser.parse_args(argv)
    if bool(args.job) == bool(args.schedule):
        parser.error('pass exactly one of --job or --schedule')
    if args.schedule:
        # Flatten comma-separated values so `--schedule "$OMI_SCHEDULED_JOBS"` works: the set of jobs is
        # then configuration, not a compose command with lines commented in and out.
        specs = [part.strip() for value in args.schedule for part in value.split(',') if part.strip()]
        if not specs:
            parser.error('--schedule was given no job (an empty value?)')
        try:
            schedules = dict(parse_schedule(spec) for spec in specs)
        except ValueError as exc:
            parser.error(str(exc))
        return asyncio.run(run_scheduler(schedules))
    if args.interval_seconds is not None and args.interval_seconds < 1:
        parser.error('--interval-seconds must be >= 1')
    if not args.loop:
        return run_once(args.job)
    return run_loop(args.job, interval_seconds=args.interval_seconds)


if __name__ == '__main__':
    sys.exit(main())
