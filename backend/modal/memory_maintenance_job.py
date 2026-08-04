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
from typing import Any

import firebase_admin

from utils.memory.canonical_short_term_maintenance_cron import (
    run_canonical_short_term_maintenance_cron,
)
from utils.task_intelligence.workstream_association import (
    drain_recurrence_inbox_for_maintenance,
    persist_recurrence_signals_for_maintenance,
)

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

HISTORICAL_GRAPH_ENRICHMENT_UID = "HISTORICAL_GRAPH_ENRICHMENT_UID"


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        service_account_info = json.loads(service_account_json)
        credentials = firebase_admin.credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(credentials)  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped
    else:
        firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped


def _historical_graph_enrichment_from_env() -> dict[str, Any] | None:
    """Run a separately invoked, bounded historical page; disabled by default."""
    uid = os.getenv(HISTORICAL_GRAPH_ENRICHMENT_UID, "").strip()
    if not uid:
        return None
    from scripts.enrich_historical_memory_graph import MAX_PAGE_SIZE, run_enrichment

    firestore_project = os.getenv("HISTORICAL_GRAPH_ENRICHMENT_FIRESTORE_PROJECT", "").strip()
    if not firestore_project:
        raise RuntimeError("historical graph enrichment requires an explicit Firestore project")
    try:
        limit = int(os.getenv("HISTORICAL_GRAPH_ENRICHMENT_LIMIT", "1"))
        apply_limit = int(os.getenv("HISTORICAL_GRAPH_ENRICHMENT_APPLY_LIMIT", "1"))
    except ValueError as exc:
        raise RuntimeError("historical graph enrichment limits must be integers") from exc
    if not 1 <= limit <= MAX_PAGE_SIZE or not 1 <= apply_limit <= MAX_PAGE_SIZE:
        raise RuntimeError(f"historical graph enrichment limits must be between 1 and {MAX_PAGE_SIZE}")
    apply = os.getenv("HISTORICAL_GRAPH_ENRICHMENT_APPLY", "false").lower() == "true"
    structured_only = os.getenv("HISTORICAL_GRAPH_ENRICHMENT_STRUCTURED_ONLY", "false").lower() == "true"
    return run_enrichment(
        uid=uid,
        firestore_project=firestore_project,
        limit=limit,
        apply=apply,
        confirm_uid=os.getenv("HISTORICAL_GRAPH_ENRICHMENT_CONFIRM_UID"),
        structured_only=structured_only,
        apply_limit=apply_limit,
    )


def main() -> None:
    _init_firebase()
    historical_report = _historical_graph_enrichment_from_env()
    if historical_report is not None:
        logger.info(
            "Historical canonical graph enrichment completed: %s", json.dumps(historical_report, sort_keys=True)
        )
        if any(key.startswith("apply_") for key in historical_report["outcomes"]):
            raise RuntimeError("historical graph enrichment apply failed")
        return
    logger.info("Starting memory-maintenance-job...")
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
