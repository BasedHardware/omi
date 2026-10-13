"""Count-only lease outcomes, shared by admission and pass orchestration."""

import logging

from prometheus_client import Counter

PASSES = Counter('omi_dream_pass_total', 'Dream terminal pass outcomes', ['status', 'error_type'])
ABANDONED = Counter('omi_dream_abandoned_total', 'Dream abandoned leases reclaimed', ['context_mode'])
logger = logging.getLogger(__name__)


def record_reclaimed(age_s, context_mode):
    # Emit only after the admission transaction commits, never on a retry.
    PASSES.labels('failed', 'LeaseAbandoned').inc()
    ABANDONED.labels(context_mode).inc()
    logger.info('Dream lease reclaimed age_s=%d mode=%s', age_s, context_mode)
