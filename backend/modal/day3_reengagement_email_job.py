"""Independent Cloud Run Job entrypoint for EXP-001's day-3 re-engagement email.

Modeled on ``daily_memory_sweep_job.py``: a thin entrypoint that resolves its
own authority before touching any user data, then delegates every decision to
``utils.email.day3_reengagement``. See
``backend/docs/experiments/EXP-001-day3-reengagement.md`` for the experiment
this job runs.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os

import firebase_admin

from database._client import db as default_db_client
from database.auth import get_user_from_uid
from utils.email.day3_reengagement import (
    authority_from_environment,
    collect_day3_candidates,
    run_day3_reengagement,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        firebase_admin.initialize_app(firebase_admin.credentials.Certificate(json.loads(service_account_json)))
    else:
        firebase_admin.initialize_app()


def _display_name_for(uid: str) -> str | None:
    user = get_user_from_uid(uid)
    return (user or {}).get("display_name")


def run_day3_reengagement_email_job() -> None:
    # Keep the deployed job completely dark until the backend-owned authority
    # is explicitly open. In particular, do not select candidates or send any
    # mail while the flag is disabled, killed, malformed, or otherwise
    # unavailable. ``getattr`` is deliberate: an unavailable authority
    # provider must fail closed rather than allowing a newly deployed job to
    # perform any user work.
    try:
        authority = authority_from_environment()
        authority_open = getattr(authority, "may_send", False) is True
    except Exception:
        logger.info("day3-reengagement-email job closed by backend authority; exiting before candidate selection")
        return
    if not authority_open:
        logger.info("day3-reengagement-email job closed by backend authority; exiting before candidate selection")
        return

    now = datetime.now(timezone.utc)
    candidates = collect_day3_candidates(now=now, firestore_client=default_db_client)
    summary = run_day3_reengagement(
        candidates=candidates,
        now=now,
        authority=authority,
        display_name_for=_display_name_for,
        firestore_client=default_db_client,
    )
    if summary.failed:
        raise RuntimeError(f"day3-reengagement-email completed with {summary.failed} failure(s)")


def main() -> None:
    _init_firebase()
    logger.info("Starting day3-reengagement-email-job...")
    run_day3_reengagement_email_job()


if __name__ == "__main__":
    main()
