"""Batch maintenance single-owner lease switch. Pure env read at the call boundary."""

import os


def leader_lease_enabled() -> bool:
    """Default on. Explicit false restores every replica running every maintenance tick."""
    return os.getenv('BATCH_PIPELINE_LEADER_LEASE_ENABLED', 'true').strip().lower() != 'false'
