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
from services.frame_request_retention import run_frame_request_retention_maintenance
from utils.memory.canonical_short_term_maintenance_cron import (
    DailySweepUIDInventoryPage,
    bounded_daily_memory_sweep_uid_inventory,
    commit_daily_memory_sweep_uid_inventory,
    run_canonical_short_term_maintenance_cron,
)
from utils.memory.daily_memory_sweep import (
    daily_memory_sweep_authority_from_environment,
    firestore_daily_sweep_source_provider,
    read_daily_memory_sweep_cohort_assignment,
    reconcile_daily_memory_sweep_timezones_for_maintenance,
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
    # The inventory cursor is the fairness boundary.  A stateless page would
    # repeatedly sweep the first canonical users and starve onboarding/cold
    # starts despite the bounded union inventory.
    inventory_page = bounded_daily_memory_sweep_uid_inventory(
        default_db_client,
        limit=400,
        persist_cursor=False,
        return_page=True,
    )
    if not isinstance(inventory_page, DailySweepUIDInventoryPage):
        raise RuntimeError("daily-memory-sweep inventory page is malformed")
    inventory = inventory_page.uids
    truthy = {"1", "true", "yes", "on"}
    if os.getenv("MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED", "false").casefold() in truthy:
        reconcile_daily_memory_sweep_timezones_for_maintenance(
            inventory,
            timezone_resolver=lambda uid: get_user_time_zone(uid) or "UTC",
            db_client=default_db_client,
            authorized=True,
            max_users=400,
        )
    summary = run_daily_memory_sweep_scheduler(
        db_client=default_db_client,
        now=now,
        uid_inventory=inventory,
        source_provider=lambda uid, local_date, control, **kwargs: firestore_daily_sweep_source_provider(
            uid, local_date, control, db_client=default_db_client, timezone_name=kwargs.get("timezone_name", "UTC")
        ),
        timezone_resolver=lambda uid: get_user_time_zone(uid) or "UTC",
        # Read-only cohort evaluation; the resolver defaults closed and never
        # mutates PostHog or any user state.
        cohort_authorizer=read_daily_memory_sweep_cohort_assignment,
        authority=authority,
        max_users=400,
    )
    commit_daily_memory_sweep_uid_inventory(
        default_db_client,
        inventory_page,
        completed_uids=summary.completed_uids,
    )
    if summary.errors:
        raise RuntimeError(f"daily-memory-sweep completed with {len(summary.errors)} error(s)")


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
    errors: list[str] = []
    try:
        summary = asyncio.run(
            run_canonical_short_term_maintenance_cron(
                recurrence_signal_persister=persist_recurrence_signals_for_maintenance,
                recurrence_signal_consumer=drain_recurrence_inbox_for_maintenance,
            )
        )
        if summary.errors:
            errors.append(f"canonical={len(summary.errors)}")
            logger.error("canonical short-term maintenance reported %d error(s)", len(summary.errors))
    except Exception as exc:
        errors.append(f"canonical={type(exc).__name__}")
        logger.exception("canonical short-term maintenance failed; continuing daily sweep")

    # Daily replacement is an independent backend-authoritative lane. Legacy
    # canonical maintenance may be retired, disabled, or unhealthy without
    # suppressing this scheduler's bounded retry/cursor work.
    try:
        _run_daily_memory_sweep_if_authorized()
    except Exception as exc:
        errors.append(f"daily={type(exc).__name__}")
        logger.exception("daily-memory-sweep failed")
    if errors:
        raise RuntimeError(f"memory-maintenance-job completed with {len(errors)} error(s)")


if __name__ == "__main__":
    main()
