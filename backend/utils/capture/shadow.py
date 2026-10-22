"""Bounded capture refactor comparisons; no identifiers or speech in telemetry."""

import logging

from prometheus_client import Counter

logger = logging.getLogger(__name__)
SHADOW = Counter('omi_capture_dedupe_shadow_total', 'Capture dedupe shadow comparisons', ['path', 'outcome'])


def compare(path: str, outcome: str) -> None:
    SHADOW.labels(path=path, outcome=outcome).inc()
    logger.info('event=refactor_shadow lane=L1 check=%s outcome=%s', path, outcome)
