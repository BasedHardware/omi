"""Scheduled canonical short-term maintenance (TTL audit + total L2 routing).

Hosted by the dedicated ``memory-maintenance-job`` Cloud Run Job
(``backend/modal/memory_maintenance_job.py``). Disabled by default until
``MEMORY_CANONICAL_MAINTENANCE_ENABLED=true`` and the canonical cohort
whitelist is non-empty.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Callable
from typing import Any, Optional, cast

from pydantic import ValidationError

from database._client import db as default_db_client
from models.product_memory import MemoryItem
from utils.executors import db_executor, run_blocking
from utils.log_sanitizer import sanitize_validation_error
from utils.observability.fallback import record_fallback
from utils.llm.clients import get_llm
from utils.memory.canonical_required_processing import (
    ProcessedRequiredMemory,
    invoke_required_memory_processor,
)
from utils.memory.memory_system import list_canonical_cohort_uids
from utils.memory.short_term_promotion import (
    CanonicalShortTermMaintenanceReport,
    run_canonical_short_term_maintenance,
)

logger = logging.getLogger(__name__)

MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV = "MEMORY_CANONICAL_MAINTENANCE_ENABLED"


def _required_memory_processor(item: MemoryItem) -> ProcessedRequiredMemory:
    return invoke_required_memory_processor(item, get_llm("memory_l2"))


def _empty_errors() -> list[str]:
    return []


def canonical_maintenance_enabled() -> bool:
    raw = os.getenv(MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "false")
    return raw.lower() == "true"


@dataclass
class CanonicalShortTermMaintenanceCronSummary:
    run_id: str
    user_count: int = 0
    routed_total: int = 0
    promoted_total: int = 0
    skipped_users: int = 0
    recurrence_candidates_total: int = 0
    outbox_delivered_total: int = 0
    outbox_retryable_failures_total: int = 0
    outbox_dead_letters_total: int = 0
    outbox_ack_failures_total: int = 0
    errors: list[str] = field(default_factory=_empty_errors)


def _coerce_run_id(run_id: Optional[str], *, now: datetime) -> str:
    if run_id:
        return run_id
    return f"cron-{now.strftime('%Y%m%d%H%M%S')}"


def _skipped_reason(report: CanonicalShortTermMaintenanceReport) -> Optional[str]:
    if report.skipped_reason:
        return report.skipped_reason
    if report.consolidation and report.consolidation.skipped_reason:
        return report.consolidation.skipped_reason
    return None


def _promoted_count(report: CanonicalShortTermMaintenanceReport) -> int:
    return report.promoted_count


def _safe_maintenance_error(uid: str, exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return f"uid={uid}: ValidationError: {sanitize_validation_error(cast(Any, exc))}"
    return f"uid={uid}: {type(exc).__name__}"


def run_canonical_short_term_maintenance_for_cohort(
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
    recurrence_signal_persister: Optional[Callable[..., int]] = None,
    recurrence_signal_consumer: Optional[Callable[..., int]] = None,
) -> CanonicalShortTermMaintenanceCronSummary:
    """Run maintenance for every uid in ``CANONICAL_MEMORY_USERS``.

    Enablement and empty-cohort gates live here so the dedicated job entrypoint
    can call this runner directly. Cloud Scheduler owns cadence; this process
    owns only explicit enablement and the canonical cohort.
    """
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    maintenance_now = current_time if now is not None else None
    effective_run_id = _coerce_run_id(run_id, now=current_time)
    if not canonical_maintenance_enabled():
        logger.info(
            "canonical_short_term_maintenance_cron: disabled run_id=%s",
            effective_run_id,
        )
        return CanonicalShortTermMaintenanceCronSummary(run_id=effective_run_id, user_count=0)

    client = db_client if db_client is not None else default_db_client
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
                now=maintenance_now,
                run_id=effective_run_id,
                recurrence_signal_sink=recurrence_signal_persister,
                required_processor=_required_memory_processor,
            )
        except Exception as exc:
            message = _safe_maintenance_error(uid, exc)
            summary.errors.append(message)
            logger.warning("canonical_short_term_maintenance_cron: failed %s", message)
            continue

        promoted = _promoted_count(report)
        skipped = _skipped_reason(report)
        trigger = report.consolidation.trigger_reason if report.consolidation else None
        summary.routed_total += report.routed_count
        summary.promoted_total += promoted
        outbox = report.outbox or {}
        outbox_delivered = int(outbox.get("delivered_count") or 0)
        outbox_retryable = int(outbox.get("retryable_failure_count") or 0)
        outbox_dead_letters = int(outbox.get("dead_letter_count") or 0)
        outbox_ack_failures = int(outbox.get("ack_failed_count") or 0)
        raw_outbox_errors = outbox.get("errors")
        outbox_error_count = (
            len(cast(list[object], raw_outbox_errors))
            if isinstance(raw_outbox_errors, list)
            else int(bool(raw_outbox_errors))
        )
        summary.outbox_delivered_total += outbox_delivered
        summary.outbox_retryable_failures_total += outbox_retryable
        summary.outbox_dead_letters_total += outbox_dead_letters
        summary.outbox_ack_failures_total += outbox_ack_failures
        required_processing = report.required_processing
        required_processing_failures = required_processing.failed_memory_ids if required_processing is not None else []
        if required_processing is not None and required_processing_failures:
            retryable_count = len(required_processing.retryable_memory_ids)
            quarantined_count = len(required_processing.quarantined_memory_ids)
            summary.errors.append(
                f"uid={uid}: required_processing_failed:"
                f"failed={len(required_processing_failures)}:"
                f"retryable={retryable_count}:"
                f"quarantined={quarantined_count}"
            )
        consolidation_errors = report.consolidation.errors if report.consolidation is not None else []
        consolidation_blocked = bool(report.consolidation and report.consolidation.watermark_blocked)
        if consolidation_blocked or consolidation_errors:
            retryable_count = len(report.consolidation.retryable_memory_ids) if report.consolidation is not None else 0
            quarantined_count = (
                len(report.consolidation.quarantined_memory_ids) if report.consolidation is not None else 0
            )
            summary.errors.append(
                f"uid={uid}: consolidation_failed:"
                f"blocked={int(consolidation_blocked)}:"
                f"retryable={retryable_count}:"
                f"quarantined={quarantined_count}:"
                f"errors={len(consolidation_errors)}"
            )
        if outbox_retryable or outbox_dead_letters or outbox_ack_failures or outbox_error_count:
            summary.errors.append(
                f"uid={uid}: outbox_delivery_failed:"
                f"retryable={outbox_retryable}:"
                f"dead_letter={outbox_dead_letters}:"
                f"ack={outbox_ack_failures}:"
                f"errors={outbox_error_count}"
            )
        if recurrence_signal_consumer is not None and report.consolidation is not None:
            try:
                summary.recurrence_candidates_total += recurrence_signal_consumer(
                    uid,
                    report.consolidation.recurrence_signals,
                    firestore_client=client,
                )
            except Exception as exc:
                message = f"uid={uid}: recurrence_consumer:{type(exc).__name__}"
                summary.errors.append(message)
                logger.warning("canonical_short_term_maintenance_cron: %s", message)
                record_fallback(
                    component="other",
                    from_mode="recurrence_maintenance",
                    to_mode="recurrence_inbox_retry",
                    reason="other",
                    outcome="degraded",
                )
        if report.routed_count == 0:
            summary.skipped_users += 1

        logger.info(
            "canonical_short_term_maintenance_cron: uid=%s trigger_reason=%s routed_count=%d "
            "promoted_count=%d skipped_reason=%s",
            uid,
            trigger,
            report.routed_count,
            promoted,
            skipped,
        )

    logger.info(
        "canonical_short_term_maintenance_cron: done run_id=%s user_count=%d routed_total=%d "
        "promoted_total=%d skipped_users=%d errors=%d",
        effective_run_id,
        summary.user_count,
        summary.routed_total,
        summary.promoted_total,
        summary.skipped_users,
        len(summary.errors),
    )
    return summary


async def run_canonical_short_term_maintenance_cron(
    *,
    db_client: Any = None,
    now: Optional[datetime] = None,
    run_id: Optional[str] = None,
    recurrence_signal_persister: Optional[Callable[..., int]] = None,
    recurrence_signal_consumer: Optional[Callable[..., int]] = None,
) -> CanonicalShortTermMaintenanceCronSummary:
    """Async entrypoint: offload sync Firestore maintenance to ``db_executor``."""
    return await run_blocking(
        db_executor,
        run_canonical_short_term_maintenance_for_cohort,
        db_client=db_client,
        now=now,
        run_id=run_id,
        recurrence_signal_persister=recurrence_signal_persister,
        recurrence_signal_consumer=recurrence_signal_consumer,
    )
