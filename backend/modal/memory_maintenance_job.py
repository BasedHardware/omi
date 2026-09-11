"""Cloud Run Job entrypoint for canonical short-term memory maintenance.

Concurrency: Cloud Run Jobs default to max-retries / single-execution semantics per
execution ID. Overlapping Scheduler + manual runs are still possible; maintenance
ops are designed to be idempotent (required normalization, TTL, total L2 routing,
and leased projection-outbox delivery), and
operators should prefer ``gcloud run jobs execute ... --wait`` before asserting
state. A distributed lease can be added later if overlap becomes observable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import firebase_admin

from services.frame_request_retention import run_frame_request_retention_maintenance
from utils.memory.canonical_short_term_maintenance_cron import (
    run_canonical_short_term_maintenance_cron,
)
from utils.task_intelligence.workstream_association import (
    drain_recurrence_inbox_for_maintenance,
    persist_recurrence_signals_for_maintenance,
)

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

_FATAL_ERROR_MARKERS = ("outbox_delivery_failed", "cursor_persist:")


def _fatal_job_errors(errors: list[str], *, flex_deferred: bool) -> list[str]:
    """Outbox/cursor failures always fail the job; a Flex stop does not retry the page."""
    fatal = [error for error in errors if any(marker in error for marker in _FATAL_ERROR_MARKERS)]
    if fatal:
        return fatal
    if flex_deferred:
        return []
    return list(errors)


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        service_account_info = json.loads(service_account_json)
        credentials = firebase_admin.credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credentials)  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
    else:
        firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped


def main() -> None:
    _init_firebase()
    logger.info("Starting memory-maintenance-job...")
    # Preserve the legacy cleanup path until deployment records a healthy,
    # independently scheduled retention job. The explicit env gate is switched
    # only by an operational rollout after live bucket/Scheduler proof.
    if os.getenv("FRAME_REQUEST_RETENTION_INDEPENDENT_HEALTHY", "false").strip().lower() != "true":
        try:
            run_frame_request_retention_maintenance(user_limit=250)
        except Exception:
            logger.exception("legacy frame retention safety pass failed; canonical maintenance continues")
    summary = asyncio.run(
        run_canonical_short_term_maintenance_cron(
            recurrence_signal_persister=persist_recurrence_signals_for_maintenance,
            recurrence_signal_consumer=drain_recurrence_inbox_for_maintenance,
        )
    )
    fatal_errors = _fatal_job_errors(
        list(summary.errors or []),
        flex_deferred=bool(getattr(summary, "flex_deferred", False)),
    )
    if summary.errors and not fatal_errors:
        logger.warning(
            "memory-maintenance-job: flex stop with residual errors count=%d errors=%s",
            len(summary.errors),
            summary.errors,
        )
    if fatal_errors:
        raise RuntimeError(f"memory-maintenance-job completed with {len(fatal_errors)} error(s)")


if __name__ == "__main__":
    main()
