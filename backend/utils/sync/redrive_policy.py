"""Pure default-off rollout reads; safe on async worker request paths."""

import os

from utils.sync import stage


def enabled() -> bool:
    return stage.production_stage() and os.getenv('SYNC_DURABLE_REDRIVE_GUARD', 'false').strip().lower() == 'true'


def legacy_convergence_enabled() -> bool:
    return (
        stage.production_stage() and os.getenv('SYNC_LEGACY_COMPLETION_CONVERGENCE', 'false').strip().lower() == 'true'
    )
