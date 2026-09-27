"""Cloud Run Job entrypoint for the conversation self-heal sweep.

One execution is one bounded tick: a rotated ``in_progress`` collection-group
scan that admits stale content-bearing rows into the durable finalization
outbox as SERVER_RECOVERY jobs, plus the Cloud Logging wedge detector that
optionally nudges wedged pendant users.

Modes via ``SELFHEAL_MODE``: ``off`` (default) | ``detect`` | ``nudge`` |
``heal`` — an unrecognized value fails closed to ``off``. All sweep and nudge
behavior is disabled unless the mode is explicitly set. Overlapping Scheduler
executions are safe: recovery admission is transaction-fenced, the sweep
cursor is a generation CAS, and every nudge claims its cooldown before send.
"""

from __future__ import annotations

import json
import logging
import os

import firebase_admin

from services.conversation_selfheal import run_selfheal_tick, selfheal_dry_run, selfheal_mode
from utils.env_loader import firebase_admin_options

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


def _init_firebase() -> None:
    service_account_json = os.getenv("SERVICE_ACCOUNT_JSON")
    if service_account_json:
        firebase_admin.initialize_app(
            firebase_admin.credentials.Certificate(json.loads(service_account_json)),
            options=firebase_admin_options(),
        )
    else:
        firebase_admin.initialize_app(options=firebase_admin_options())


def main() -> None:
    mode = selfheal_mode()
    logger.info("Starting conversation-selfheal-job mode=%s dry_run=%s", mode, selfheal_dry_run())
    if mode == 'off':
        run_selfheal_tick(mode=mode)
        return
    _init_firebase()
    summary = run_selfheal_tick()
    if summary.get('errors'):
        raise RuntimeError(f"conversation-selfheal-job completed with {summary['errors']} error(s)")


if __name__ == "__main__":
    main()
