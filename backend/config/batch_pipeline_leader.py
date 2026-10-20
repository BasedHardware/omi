"""Batch maintenance single-owner lease switch. Pure env read at the call boundary."""

from config.policy import kill_switch


def leader_lease_enabled() -> bool:
    """Default on. Explicit false restores every replica running every maintenance tick."""
    return kill_switch('BATCH_PIPELINE_LEADER_LEASE_ENABLED')
