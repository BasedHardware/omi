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
from utils.env_loader import firebase_admin_options
from utils.jit_rollout import JITDecisionStage, TriState, resolve_jit_rollout_sync
from utils.memory.daily_memory_sweep import (
    DailySweepCohortDecision,
    daily_memory_sweep_authority_from_environment,
    firestore_daily_sweep_source_provider,
    reconcile_daily_memory_sweep_timezone,
    run_daily_memory_sweep_scheduler,
    qa_sweep_cohort_authorizer,
    qa_sweep_run_id_from_environment,
    validate_qa_sweep_environment,
    write_qa_sweep_run_receipt,
)
from utils.memory.daily_memory_sweep_inventory import (
    DailySweepUIDInventoryPage,
    bounded_daily_memory_sweep_uid_inventory,
    commit_daily_memory_sweep_uid_inventory,
    explicit_jit_qa_daily_sweep_uid_inventory,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def jit_admission_cohort_authorizer(uid: str, _cohort_name: str = "") -> DailySweepCohortDecision:
    """Admit sweep users with the same JIT helper as processing and ledger paths."""

    decision = resolve_jit_rollout_sync(uid, stage=JITDecisionStage.READ_ONLY)
    if decision.permits_work:
        return DailySweepCohortDecision.enabled
    if decision.effective == TriState.UNKNOWN:
        return DailySweepCohortDecision.unavailable
    return DailySweepCohortDecision.disabled


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        firebase_admin.initialize_app(firebase_admin.credentials.Certificate(json.loads(service_account_json)))
    else:
        firebase_admin.initialize_app(options=firebase_admin_options())


def run_daily_memory_sweep_job() -> None:
    # Keep the deployed scheduler completely dark until the backend-owned
    # authority is explicitly open.  In particular, do not inventory users or
    # enter the scheduler's lifecycle janitor while the flag is disabled,
    # killed, malformed, or otherwise unavailable.  ``getattr`` is deliberate:
    # an unavailable authority provider must fail closed rather than allowing
    # a newly deployed job to perform any user/data work.
    truthy = {"1", "true", "yes", "on"}
    try:
        authority = daily_memory_sweep_authority_from_environment()
        authority_open = getattr(authority, "may_write", False) is True
    except Exception:
        logger.info("daily-memory-sweep job closed by backend authority; exiting before inventory")
        return
    if not authority_open:
        logger.info("daily-memory-sweep job closed by backend authority; exiting before inventory")
        return
    qa_run_id = qa_sweep_run_id_from_environment()
    if qa_run_id is not None:
        validate_qa_sweep_environment()
    qa_allowlist = os.getenv("OMI_JIT_QA_UID_ALLOWLIST", "").strip()
    if os.getenv("OMI_JIT_QA_AUTH_ONLY", "false").strip().casefold() in truthy:
        page = explicit_jit_qa_daily_sweep_uid_inventory(qa_allowlist.split(","))
    else:
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
            uid,
            local_date,
            control,
            db_client=default_db_client,
            timezone_name=kwargs.get("timezone_name", "UTC"),
            qa_run_id=kwargs.get("qa_run_id"),
        ),
        timezone_resolver=lambda uid: get_user_time_zone(uid) or "UTC",
        cohort_authorizer=qa_sweep_cohort_authorizer if qa_run_id is not None else jit_admission_cohort_authorizer,
        timezone_reconciler=timezone_reconciler,
        authority=authority,
        max_users=400,
        qa_run_id=qa_run_id,
    )
    commit_daily_memory_sweep_uid_inventory(
        default_db_client,
        page,
        completed_uids=summary.completed_uids,
        failed_uids=summary.failed_uids,
        advance_page=summary.attempted_users > 0,
    )
    if summary.errors:
        # The summary already bounds this tuple to 16 entries of
        # `uid=<uid>:<reason-or-exception-type>` (or a scheduler-level token),
        # with no memory, transcript, or prompt content. Without this line the
        # job reports only a count, and a single account failing every hourly
        # run is undiagnosable from logs.
        logger.error("daily-memory-sweep errors: %s", ", ".join(summary.errors))
        if qa_run_id is not None:
            write_qa_sweep_run_receipt(default_db_client, run_id=qa_run_id, summary=summary)
        raise RuntimeError(f"daily-memory-sweep completed with {len(summary.errors)} error(s)")
    if qa_run_id is not None:
        write_qa_sweep_run_receipt(default_db_client, run_id=qa_run_id, summary=summary)


def main() -> None:
    _init_firebase()
    logger.info("Starting daily-memory-sweep-job...")
    run_daily_memory_sweep_job()


if __name__ == "__main__":
    main()
