"""Cloud Run Job entrypoint for X (Twitter) connector incremental sync.

Scheduler owns the 6h cadence (``x-connector-sync-6h``). This entrypoint always
runs ``run_x_sync_job()`` — do not reintroduce hour-modulo gating here.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

import firebase_admin

from utils.x_connector import is_oauth_configured, raise_if_x_sync_job_failed, run_x_sync_job

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
    # Credential gate: without an X OAuth app configured every per-user token
    # refresh is a guaranteed 400 and the RapidAPI fallback a guaranteed
    # failure, so the sweep would walk the whole connected-user registry for
    # nothing. An unconfigured deployment is a healthy no-op, not a failure.
    if not is_oauth_configured():
        logger.info("x-connector-sync-job skipped: no X OAuth app configured")
        return
    logger.info("Starting x-connector-sync-job...")
    summary = asyncio.run(run_x_sync_job())
    logger.info("x-connector-sync-job summary: %s", summary)
    raise_if_x_sync_job_failed(summary)


if __name__ == "__main__":
    main()
