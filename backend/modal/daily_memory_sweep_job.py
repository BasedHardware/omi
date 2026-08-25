"""Independent Cloud Run Job entrypoint for the daily memory replacement.

This job deliberately owns no legacy canonical-maintenance imports or control
flags. Its image and Scheduler trigger can remain deployed while the legacy
short-term maintenance job is retired.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os

import firebase_admin

from database._client import db as default_db_client
from database.notifications import get_user_time_zone
from utils.memory.daily_memory_sweep import (
    daily_memory_sweep_authority_from_environment,
    firestore_daily_sweep_source_provider,
    read_daily_memory_sweep_cohort_assignment,
    reconcile_daily_memory_sweep_timezone,
    run_daily_memory_sweep_scheduler,
)
from utils.memory.daily_memory_sweep_inventory import (
    DailySweepUIDInventoryPage,
    bounded_daily_memory_sweep_uid_inventory,
    commit_daily_memory_sweep_uid_inventory,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        firebase_admin.initialize_app(firebase_admin.credentials.Certificate(json.loads(service_account_json)))
    else:
        firebase_admin.initialize_app()


def run_daily_memory_sweep_job() -> None:
    # Keep the deployed scheduler completely dark until the backend-owned
    # authority is explicitly open.  In particular, do not inventory users or
    # enter the scheduler's lifecycle janitor while the flag is disabled,
    # killed, malformed, or otherwise unavailable.  ``getattr`` is deliberate:
    # an unavailable authority provider must fail closed rather than allowing
    # a newly deployed job to perform any user/data work.
    try:
        authority = daily_memory_sweep_authority_from_environment()
        authority_open = getattr(authority, "may_write", False) is True
    except Exception:
        authority_open = False
    if not authority_open:
        logger.info("daily-memory-sweep job closed by backend authority; exiting before inventory")
        return
    page = bounded_daily_memory_sweep_uid_inventory(
        default_db_client,
        limit=400,
        persist_cursor=False,
        return_page=True,
    )
    if not isinstance(page, DailySweepUIDInventoryPage):
        raise RuntimeError("daily-memory-sweep inventory page is malformed")
    inventory = page.uids
    now = datetime.now(timezone.utc)
    truthy = {"1", "true", "yes", "on"}
    timezone_reconciler = None
    if os.getenv("MEMORY_DAILY_MEMORY_SWEEP_TIMEZONE_RECONCILIATION_ENABLED", "false").casefold() in truthy:
        timezone_reconciler = lambda uid, timezone_name: reconcile_daily_memory_sweep_timezone(
            uid,
            timezone_name,
            db_client=default_db_client,
            reconciliation_authorized=True,
        )
    summary = run_daily_memory_sweep_scheduler(
        db_client=default_db_client,
        now=now,
        uid_inventory=inventory,
        source_provider=lambda uid, local_date, control, **kwargs: firestore_daily_sweep_source_provider(
            uid, local_date, control, db_client=default_db_client, timezone_name=kwargs.get("timezone_name", "UTC")
        ),
        timezone_resolver=lambda uid: get_user_time_zone(uid) or "UTC",
        cohort_authorizer=read_daily_memory_sweep_cohort_assignment,
        timezone_reconciler=timezone_reconciler,
        authority=authority,
        max_users=400,
    )
    commit_daily_memory_sweep_uid_inventory(
        default_db_client,
        page,
        completed_uids=summary.completed_uids,
        failed_uids=summary.failed_uids,
        advance_page=summary.attempted_users > 0,
    )
    if summary.errors:
        raise RuntimeError(f"daily-memory-sweep completed with {len(summary.errors)} error(s)")


def main() -> None:
    _init_firebase()
    logger.info("Starting daily-memory-sweep-job...")
    run_daily_memory_sweep_job()


if __name__ == "__main__":
    main()
