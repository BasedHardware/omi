"""Cloud Run Job entrypoint for X (Twitter) connector incremental sync.

Scheduler owns the 6h cadence (``x-connector-sync-6h``). This entrypoint always
runs ``run_x_sync_job()`` — do not reintroduce hour-modulo gating here.
"""

from __future__ import annotations

import asyncio
import logging

import firebase_admin

from database.firestore_read_origin import read_origin
from utils.env_loader import firebase_admin_options
from utils.x_connector import is_oauth_configured, raise_if_x_sync_job_failed, run_x_sync_job

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    # ADC selects the attached runtime SA; the customer project stays explicit.
    firebase_admin.initialize_app(options=firebase_admin_options())  # type: ignore[reportUnknownMemberType]  # firebase_admin untyped


@read_origin('job:x_connector_sync')
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
