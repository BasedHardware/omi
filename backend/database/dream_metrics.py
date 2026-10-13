"""Count-only lease outcomes, shared by admission and pass orchestration."""

import logging

from prometheus_client import Counter, REGISTRY


def _counter(name: str, documentation: str, labels: list[str]) -> Counter:
    """Keep process-owned collectors across module eviction or concurrent imports."""
    try:
        return Counter(name, documentation, labels, registry=REGISTRY)
    except ValueError:
        # Import isolation can evict this module without unregistering collectors.
        # Reuse only the same metric shape; unrelated registration errors still fail.
        existing = getattr(REGISTRY, '_names_to_collectors', {}).get(name)
        if existing is None:
            raise
        if type(existing) is not Counter or tuple(getattr(existing, '_labelnames', ())) != tuple(labels):
            raise ValueError(f'metric {name} already registered with a different shape') from None
        return existing


PASSES = _counter('omi_dream_pass_total', 'Dream terminal pass outcomes', ['status', 'error_type'])
ABANDONED = _counter('omi_dream_abandoned_total', 'Dream abandoned leases reclaimed', ['context_mode'])
logger = logging.getLogger(__name__)


def record_reclaimed(age_s, context_mode):
    # Emit only after the admission transaction commits, never on a retry.
    PASSES.labels('failed', 'LeaseAbandoned').inc()
    ABANDONED.labels(context_mode).inc()
    logger.info('Dream lease reclaimed age_s=%d mode=%s', age_s, context_mode)
