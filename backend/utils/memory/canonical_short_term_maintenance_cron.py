"""Scheduled canonical short-term maintenance (TTL audit + batch-or-daily promotion).

Wired into the hourly ``notifications-job`` Cloud Run job via ``utils.other.jobs``.
Disabled by default until ``MEMORY_CANONICAL_PROMOTION_CRON_ENABLED=true`` and the
canonical cohort whitelist is non-empty.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from database._client import db as default_db_client
from utils.executors import db_executor, run_blocking
from utils.memory.memory_system import list_canonical_cohort_uids
from utils.memory.short_term_promotion import (
    CanonicalShortTermMaintenanceReport,
    run_canonical_short_term_maintenance,
)

logger = logging.getLogger(__name__)

MEMORY_CANONICAL_PROMOTION_CRON_ENABLED_ENV = "MEMORY_CANONICAL_PROMOTION_CRON_ENABLED"
MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS_ENV = "MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS"
DEFAULT_CRON_INTERVAL_HOURS = 1


def _empty_errors() -> list[str]:
    return []


def canonical_promotion_cron_enabled() -> bool:
    raw = os.getenv(MEMORY_CANONICAL_PROMOTION_CRON_ENABLED_ENV, "false")
    return raw.lower() == "true"


def canonical_promotion_cron_interval_hours() -> int:
    raw = os.getenv(MEMORY_CANONICAL_PROMOTION_CRON_INTERVAL_HOURS_ENV, str(DEFAULT_CRON_INTERVAL_HOURS))
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_CRON_INTERVAL_HOURS
    return max(1, value)


def should_run_canonical_short_term_maintenance_cron(*, now: Optional[datetime] = None) -> bool:
    """Gate cron to explicit enablement, non-empty cohort, and hourly scheduler ticks."""
    if not canonical_promotion_cron_enabled():
        return False
    if not list_canonical_cohort_uids():
        return False
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return current.hour % canonical_promotion_cron_interval_hours() == 0


@dataclass
class CanonicalShortTermMaintenanceCronSummary:
    run_id: str
    user_count: int = 0
    promoted_total: int = 0
    vector_sync_failures_total: int = 0
    skipped_users: int = 0
    errors: list[str] = field(default_factory=_empty_errors)


def _coerce_run_id(run_id: Optional[str], *, now: datetime) -> str:
    if run_id:
        return run_id
    return f"cron-{now.strftime('%Y%m%d%H%M%S')}"


def _skipped_reason(report: CanonicalShortTermMaintenanceReport) -> Optional[str]:
    if report.skipped_reason:
        return report.skipped_reason
    if report.promotion and report.promotion.skipped_reason:
        return report.promotion.skipped_reason
    return None


def _promoted_count(report: CanonicalShortTermMaintenanceReport) -> int:
    if report.promotion is None:
        return 0
    return report.promotion.promoted_count


def run_canonical_short_term_maintenance_for_cohort(
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
) -> CanonicalShortTermMaintenanceCronSummary:
    """Run maintenance for every uid in ``CANONICAL_MEMORY_USERS``."""
    client = db_client if db_client is not None else default_db_client
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    effective_run_id = _coerce_run_id(run_id, now=current_time)
    uids = list_canonical_cohort_uids()

    summary = CanonicalShortTermMaintenanceCronSummary(run_id=effective_run_id, user_count=len(uids))
    logger.info(
        "canonical_short_term_maintenance_cron: start run_id=%s user_count=%d",
        effective_run_id,
        len(uids),
    )

    for uid in uids:
        try:
            report = run_canonical_short_term_maintenance(
                uid,
                db_client=client,
                now=current_time,
                run_id=effective_run_id,
            )
        except Exception as exc:
            message = f"uid={uid}: {type(exc).__name__}: {exc}"
            summary.errors.append(message)
            logger.warning("canonical_short_term_maintenance_cron: failed %s", message)
            continue

        promoted = _promoted_count(report)
        vector_sync_failures = report.promotion.vector_sync_failures if report.promotion else 0
        skipped = _skipped_reason(report)
        trigger = report.promotion.trigger_reason if report.promotion else None
        summary.promoted_total += promoted
        summary.vector_sync_failures_total += vector_sync_failures
        if promoted == 0:
            summary.skipped_users += 1

        logger.info(
            "canonical_short_term_maintenance_cron: uid=%s trigger_reason=%s promoted_count=%d "
            "vector_sync_failures=%d skipped_reason=%s",
            uid,
            trigger,
            promoted,
            vector_sync_failures,
            skipped,
        )

    logger.info(
        "canonical_short_term_maintenance_cron: done run_id=%s user_count=%d promoted_total=%d "
        "vector_sync_failures_total=%d skipped_users=%d errors=%d",
        effective_run_id,
        summary.user_count,
        summary.promoted_total,
        summary.vector_sync_failures_total,
        summary.skipped_users,
        len(summary.errors),
    )
    return summary


async def run_canonical_short_term_maintenance_cron(
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
) -> CanonicalShortTermMaintenanceCronSummary:
    """Async entrypoint: offload sync Firestore maintenance to ``db_executor``."""
    return await run_blocking(
        db_executor,
        run_canonical_short_term_maintenance_for_cohort,
        db_client=db_client,
        now=now,
        run_id=run_id,
    )
