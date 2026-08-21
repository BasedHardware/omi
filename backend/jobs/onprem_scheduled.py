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
from typing import Awaitable, Callable, Dict

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


JOBS: Dict[str, Callable[[], Awaitable[None]]] = {
    'notifications': _run_notifications,
    'memory-maintenance': _run_memory_maintenance,
}


def seconds_to_next_hour(now: datetime) -> float:
    """Seconds until the next top of the hour (UTC), never 0.

    Sleeping a fixed 3600s would drift by the run duration on every tick, so a container restarted at
    :59 would settle into ticking at a random minute. Upstream's schedule is ``0 * * * *`` and the
    notifications job's own hour bucketing assumes it fires near the top of the hour.
    """
    next_hour = (now.astimezone(timezone.utc) + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return max(1.0, (next_hour - now.astimezone(timezone.utc)).total_seconds())


def run_once(job: str) -> int:
    """Run one tick. Returns a process exit code; never raises."""
    started = time.monotonic()
    try:
        asyncio.run(JOBS[job]())
    except Exception:
        logger.exception('job=%s FAILED after %.1fs', job, time.monotonic() - started)
        return 1
    logger.info('job=%s ok in %.1fs', job, time.monotonic() - started)
    return 0


def run_loop(job: str, *, sleeper: Callable[[float], None] = time.sleep, ticks: int | None = None) -> int:
    """Tick at the top of every hour, forever (or ``ticks`` times, for tests).

    A failing tick is logged and the loop continues: one bad hour must not stop every later hour. The
    exit code reports whether any tick failed, which only matters for the bounded (test) form.
    """
    failures = 0
    remaining = ticks
    while remaining is None or remaining > 0:
        delay = seconds_to_next_hour(datetime.now(timezone.utc))
        logger.info('job=%s sleeping %.0fs until the next hour', job, delay)
        sleeper(delay)
        failures += run_once(job)
        if remaining is not None:
            remaining -= 1
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True, choices=sorted(JOBS), help='which scheduled job to run')
    parser.add_argument(
        '--loop',
        action='store_true',
        help='tick at the top of every hour instead of running once (compose; k8s uses a CronJob)',
    )
    args = parser.parse_args(argv)
    return run_loop(args.job) if args.loop else run_once(args.job)


if __name__ == '__main__':
    sys.exit(main())
