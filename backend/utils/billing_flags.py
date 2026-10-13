"""Operational rollout gate for billing ingestion; default off on every host."""

# LIFECYCLE: permanent

import os


def webhook_ledger_enabled() -> bool:
    return os.getenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'false').strip().lower() == 'true'
