"""Cloud Run Job entrypoint for bounded knowledge-ledger migration."""

from __future__ import annotations

import asyncio
import json
import logging
import os

import firebase_admin

from utils.memory.knowledge_ledger_drain import run_knowledge_ledger_drain

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        firebase_admin.initialize_app(firebase_admin.credentials.Certificate(json.loads(service_account_json)))
    else:
        firebase_admin.initialize_app()


def main() -> None:
    _init_firebase()
    logger.info("Starting knowledge-ledger-drain-job...")
    summary = asyncio.run(run_knowledge_ledger_drain())
    if summary.errors:
        logger.error("knowledge-ledger-drain errors: %s", ", ".join(summary.errors))
        raise RuntimeError(f"knowledge-ledger-drain completed with {len(summary.errors)} error(s)")


if __name__ == "__main__":
    main()
