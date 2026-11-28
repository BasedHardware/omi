# LIFECYCLE: one-time
# DELETE-AFTER: https://github.com/BasedHardware/omi/issues/25578
# RETIRING: legacy sync is dark in production (rollout_cohorts/_ramp legacy_sync=dark);
# the batch pipeline serves every sync upload. Do not add behaviour or route work here.
# Deletion is tracked in SCA-2965; tests/unit/test_sync_legacy_import_ratchet.py freezes it.
"""Pure default-off rollout reads; safe on async worker request paths."""

import os

from utils.sync import stage


def enabled() -> bool:
    return stage.production_stage() and os.getenv('SYNC_DURABLE_REDRIVE_GUARD', 'false').strip().lower() == 'true'


def legacy_convergence_enabled() -> bool:
    return (
        stage.production_stage() and os.getenv('SYNC_LEGACY_COMPLETION_CONVERGENCE', 'false').strip().lower() == 'true'
    )
