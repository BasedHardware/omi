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
from datetime import datetime, timezone
import json
import logging
import os

import firebase_admin

from database._client import db as default_db_client
from database.notifications import get_user_time_zone

from utils.memory.canonical_short_term_maintenance_cron import (
    bounded_canonical_memory_uid_inventory,
    run_canonical_short_term_maintenance_cron,
)
from utils.memory.daily_memory_sweep import (
    daily_memory_sweep_authority_from_environment,
    firestore_daily_sweep_source_provider,
    run_daily_memory_sweep_scheduler,
)
from utils.task_intelligence.workstream_association import (
    drain_recurrence_inbox_for_maintenance,
    persist_recurrence_signals_for_maintenance,
)

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


def _run_daily_memory_sweep_if_authorized() -> None:
    """Run the bounded daily adaptor only when its separate backend seam opens."""

    authority = daily_memory_sweep_authority_from_environment()
    if not authority.may_write:
        logger.info("daily-memory-sweep disabled by backend authority")
        return
    now = datetime.now(timezone.utc)
    inventory = bounded_canonical_memory_uid_inventory(default_db_client, limit=400, persist_cursor=False)
    summary = run_daily_memory_sweep_scheduler(
        db_client=default_db_client,
        now=now,
        uid_inventory=inventory,
        source_provider=lambda uid, local_date, control: firestore_daily_sweep_source_provider(
            uid, local_date, control, db_client=default_db_client
        ),
        timezone_resolver=lambda uid: get_user_time_zone(uid) or "UTC",
        authority=authority,
        max_users=400,
    )
    if summary.errors:
        raise RuntimeError(f"daily-memory-sweep completed with {len(summary.errors)} error(s)")


def main() -> None:
    _init_firebase()
    logger.info("Starting memory-maintenance-job...")
    summary = asyncio.run(
        run_canonical_short_term_maintenance_cron(
            recurrence_signal_persister=persist_recurrence_signals_for_maintenance,
            recurrence_signal_consumer=drain_recurrence_inbox_for_maintenance,
        )
    )
    if summary.errors:
        raise RuntimeError(f"memory-maintenance-job completed with {len(summary.errors)} error(s)")
    _run_daily_memory_sweep_if_authorized()


if __name__ == "__main__":
    main()
