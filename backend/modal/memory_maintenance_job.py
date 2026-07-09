"""Cloud Run Job entrypoint for canonical short-term memory maintenance."""

from __future__ import annotations

import asyncio
import json
import logging
import os

import firebase_admin

from utils.memory.canonical_short_term_maintenance_cron import (
    run_canonical_short_term_maintenance_cron,
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


def main() -> None:
    _init_firebase()
    logger.info("Starting memory-maintenance-job...")
    asyncio.run(run_canonical_short_term_maintenance_cron())


if __name__ == "__main__":
    main()
