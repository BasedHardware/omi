"""Closed outcome for a staged batch object that is already gone."""

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)
ARTIFACT_MISSING = Counter(
    'omi_batch_artifact_missing_total',
    'Batch staged artifact reads that found the object gone; the step closes instead of retrying',
    ['site'],
)


def record(site: str) -> None:
    """A generation-pinned object that is gone cannot come back; no retry can restore it."""
    ARTIFACT_MISSING.labels(site=site).inc()
    logger.error('event=batch_artifact_missing site=%s outcome=skipped', site)
