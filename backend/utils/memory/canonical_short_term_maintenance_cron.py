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
from utils.memory.canonical_cohort_lifecycle import run_canonical_cohort_lifecycle
from utils.memory.memory_system import list_canonical_cohort_uids
from utils.memory.short_term_promotion import (
    CanonicalShortTermMaintenanceReport,
    run_canonical_short_term_maintenance,
)
from scripts.enrich_historical_memory_graph import MAX_PAGE_SIZE, MAX_STRUCTURED_SCAN_SIZE, run_enrichment

logger = logging.getLogger(__name__)

MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV = "MEMORY_CANONICAL_MAINTENANCE_ENABLED"
MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED_ENV = "MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED"
MEMORY_CANONICAL_GRAPH_BACKFILL_PAGE_SIZE_ENV = "MEMORY_CANONICAL_GRAPH_BACKFILL_PAGE_SIZE"
MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE_ENV = "MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE"
DEFAULT_GRAPH_BACKFILL_PAGE_SIZE = 5
# The historical planner has a hard 20-second deadline per candidate.  Keep
# the scheduled scan to a small, page-relative look-ahead so one cohort user
# cannot exhaust the Cloud Run Job's one-hour budget before later users run.
GRAPH_BACKFILL_SCAN_PAGE_MULTIPLIER = 5
DEFAULT_GRAPH_BACKFILL_SCAN_SIZE = DEFAULT_GRAPH_BACKFILL_PAGE_SIZE * GRAPH_BACKFILL_SCAN_PAGE_MULTIPLIER


def _required_memory_processor(item: MemoryItem) -> ProcessedRequiredMemory:
    return invoke_required_memory_processor(item, get_llm("memory_l2"))


def _empty_errors() -> list[str]:
    return []


def canonical_maintenance_enabled() -> bool:
    raw = os.getenv(MEMORY_CANONICAL_MAINTENANCE_ENABLED_ENV, "false")
    return raw.lower() == "true"


def canonical_graph_backfill_enabled() -> bool:
    """Keep graph migration work opt-in until the deployment contract enables it."""
    return os.getenv(MEMORY_CANONICAL_GRAPH_BACKFILL_ENABLED_ENV, "false").lower() == "true"


def canonical_graph_backfill_page_size() -> int:
    """Return the bounded per-user assertion-enrichment budget for one cron run."""
    raw = os.getenv(MEMORY_CANONICAL_GRAPH_BACKFILL_PAGE_SIZE_ENV, str(DEFAULT_GRAPH_BACKFILL_PAGE_SIZE))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_GRAPH_BACKFILL_PAGE_SIZE
    return min(MAX_PAGE_SIZE, max(1, value))


def canonical_graph_backfill_scan_size(*, page_size: int | None = None) -> int:
    """Return the cursor scan window, bounded to a small current-page multiple.

    The durable keyset cursor advances after every completed scan, so the cron
    no longer needs a corpus-sized candidate window to avoid rereading writes.
    Keep enough look-ahead to skip temporarily ineligible rows, but cap both
    the default and an explicit override at five current apply pages.  This
    bounds serial 20-second planner calls while retaining the global
    ``MAX_STRUCTURED_SCAN_SIZE`` ceiling.
    """
    current_page_size = page_size if page_size is not None else canonical_graph_backfill_page_size()
    current_page_size = min(MAX_PAGE_SIZE, max(1, current_page_size))
    maximum = min(MAX_STRUCTURED_SCAN_SIZE, current_page_size * GRAPH_BACKFILL_SCAN_PAGE_MULTIPLIER)
    raw = os.getenv(MEMORY_CANONICAL_GRAPH_BACKFILL_SCAN_SIZE_ENV, str(DEFAULT_GRAPH_BACKFILL_SCAN_SIZE))
    try:
        value = int(raw)
    except ValueError:
        value = DEFAULT_GRAPH_BACKFILL_SCAN_SIZE
    return min(maximum, max(current_page_size, value))


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
    graph_enriched_total: int = 0
    graph_enrichment_blocked_total: int = 0
    lifecycle_write_enrolled_total: int = 0
    lifecycle_backfill_read_ready_total: int = 0
    lifecycle_generation_reconciled_total: int = 0
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
    try:
        lifecycle = run_canonical_cohort_lifecycle(db_client=client)
    except Exception as exc:
        message = f"canonical_cohort_lifecycle:{type(exc).__name__}"
        logger.warning("canonical_short_term_maintenance_cron: %s", message)
        summary.errors.append(message)
    else:
        summary.lifecycle_write_enrolled_total = len(lifecycle.write_enrolled_uids)
        summary.lifecycle_backfill_read_ready_total = lifecycle.backfill.summary.read_ready_count
        summary.lifecycle_generation_reconciled_total = len(lifecycle.generation_reconciled_uids)
        for reconcile_error in lifecycle.generation_reconcile_errors:
            message = f"canonical_cohort_lifecycle:{reconcile_error}"
            logger.warning("canonical_short_term_maintenance_cron: %s", message)
            summary.errors.append(message)
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

        if not canonical_graph_backfill_enabled():
            continue
        try:
            graph_page_size = canonical_graph_backfill_page_size()
            graph_report = run_enrichment(
                uid=uid,
                # The database client is injected above; this is retained only
                # for the CLI contract and is never used by this cron path.
                firestore_project=os.getenv("GOOGLE_CLOUD_PROJECT", "canonical-memory"),
                limit=graph_page_size,
                apply=True,
                confirm_uid=uid,
                structured_only=False,
                apply_limit=graph_page_size,
                scan_limit=canonical_graph_backfill_scan_size(page_size=graph_page_size),
                db_client=client,
            )
            graph_outcomes = graph_report.get("outcomes", {})
            summary.graph_enriched_total += int(graph_outcomes.get("committed", 0))
            summary.graph_enrichment_blocked_total += sum(
                int(value) for key, value in graph_outcomes.items() if key not in {"committed", "idempotent_skip"}
            )
        except Exception as exc:
            message = f"uid={uid}: graph_enrichment:{type(exc).__name__}"
            summary.errors.append(message)
            logger.warning("canonical_short_term_maintenance_cron: %s", message)

    logger.info(
        "canonical_short_term_maintenance_cron: done run_id=%s user_count=%d routed_total=%d "
        "promoted_total=%d graph_enriched_total=%d graph_enrichment_blocked_total=%d skipped_users=%d errors=%d",
        effective_run_id,
        summary.user_count,
        summary.routed_total,
        summary.promoted_total,
        summary.graph_enriched_total,
        summary.graph_enrichment_blocked_total,
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
