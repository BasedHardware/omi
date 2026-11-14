"""Operational gates for billing ingestion and payment recovery."""

# LIFECYCLE: permanent

import os


def webhook_ledger_enabled() -> bool:
    return os.getenv('BILLING_WEBHOOK_LEDGER_ENABLED', 'false').strip().lower() == 'true'


def payment_recovery_notification_enabled() -> bool:
    """On unless set off; gates only the failed-renewal push scheduler."""
    return os.getenv('PAYMENT_RECOVERY_NOTIFICATION_ENABLED', 'true').strip().lower() not in {
        '0',
        'false',
        'off',
        'no',
    }
