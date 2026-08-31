"""Independent Cloud Run Job entrypoint for frame-request retention."""

from __future__ import annotations

import json
import logging
import os

import firebase_admin

from services.frame_request_retention import run_frame_request_retention_maintenance

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        credentials = firebase_admin.credentials.Certificate(json.loads(service_account_json))
        firebase_admin.initialize_app(credentials)  # type: ignore[reportUnknownMemberType]
    else:
        firebase_admin.initialize_app()  # type: ignore[reportUnknownMemberType]


def main() -> None:
    _init_firebase()
    logger.info("Starting frame-request-retention-job...")
    result = run_frame_request_retention_maintenance()
    if result["accounts_with_errors"]:
        raise RuntimeError(
            "frame-request-retention-job completed with "
            f"{result['accounts_with_errors']} account error(s); retry queue persisted"
        )


if __name__ == "__main__":
    main()
