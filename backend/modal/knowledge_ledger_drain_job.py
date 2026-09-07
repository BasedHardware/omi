"""Cloud Run Job entrypoint for bounded knowledge-ledger migration."""

from __future__ import annotations

import asyncio
import json
import logging
import os

import firebase_admin

from utils.memory.knowledge_ledger_drain import (
    ledger_drain_enabled_from_environment,
    ledger_drain_uid_allowlist_from_environment,
    run_knowledge_ledger_drain,
)
from utils.env_loader import firebase_admin_options

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        firebase_admin.initialize_app(firebase_admin.credentials.Certificate(json.loads(service_account_json)))
    else:
        firebase_admin.initialize_app(options=firebase_admin_options())


def main() -> None:
    if not ledger_drain_enabled_from_environment():
        logger.info("knowledge-ledger-drain-job disabled")
        return
    uid_allowlist = ledger_drain_uid_allowlist_from_environment()
    if not uid_allowlist:
        raise RuntimeError("knowledge-ledger-drain-job requires an explicit UID allowlist")
    _init_firebase()
    logger.info("Starting knowledge-ledger-drain-job...")
    summary = asyncio.run(run_knowledge_ledger_drain(uid_allowlist=uid_allowlist))
    if summary.errors:
        logger.error("knowledge-ledger-drain errors: %s", ", ".join(summary.errors))
        raise RuntimeError(f"knowledge-ledger-drain completed with {len(summary.errors)} error(s)")


if __name__ == "__main__":
    main()
