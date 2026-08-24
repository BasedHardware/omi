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

from utils.memory.canonical_short_term_maintenance_cron import (
    run_canonical_short_term_maintenance_cron,
)
from utils.task_intelligence.workstream_association import (
    drain_recurrence_inbox_for_maintenance,
    persist_recurrence_signals_for_maintenance,
)
from services.frame_request_retention import run_frame_request_retention_maintenance

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


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
    # Temporary frame pixels have an independent retention loop.  It is not
    # gated by frame-request delivery or the product rollout, so a disabled
    # cohort cannot strand previously uploaded ephemeral objects.
    try:
        # Frame pixels are an independent bounded convergence concern. A
        # Firestore/GCS outage must not prevent canonical memory maintenance
        # from running for the account population.
        run_frame_request_retention_maintenance()
    except Exception:
        logger.exception("frame retention maintenance failed; canonical maintenance continues")
    summary = asyncio.run(
        run_canonical_short_term_maintenance_cron(
            recurrence_signal_persister=persist_recurrence_signals_for_maintenance,
            recurrence_signal_consumer=drain_recurrence_inbox_for_maintenance,
        )
    )
    if summary.errors:
        raise RuntimeError(f"memory-maintenance-job completed with {len(summary.errors)} error(s)")


if __name__ == "__main__":
    main()
