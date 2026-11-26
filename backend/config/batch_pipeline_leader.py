"""Advisory maintenance switch and the always-coordinated coalescing role."""

from config.policy import kill_switch

UPLOAD_COALESCING_SCAN = 'upload_coalescing_scan'
UPLOAD_COALESCING_SCAN_TTL = 6.0


def leader_lease_enabled() -> bool:
    """Default on. Explicit false restores every replica running every maintenance tick."""
    return kill_switch('BATCH_PIPELINE_LEADER_LEASE_ENABLED')
