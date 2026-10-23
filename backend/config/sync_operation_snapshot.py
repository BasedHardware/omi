"""One-operation sync read reuse. Never an authorization or cross-attempt cache."""

import os

from prometheus_client import Counter

READS_AVOIDED = Counter(
    'omi_sync_operation_snapshot_reads_avoided_total',
    'Redundant document reads avoided within one sync read operation',
    ['origin', 'operation'],
)


def enabled() -> bool:
    return os.getenv('SYNC_OPERATION_SNAPSHOT_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


def avoided(operation: str) -> None:
    READS_AVOIDED.labels(origin='job:sync_operation_snapshot', operation=operation).inc()
