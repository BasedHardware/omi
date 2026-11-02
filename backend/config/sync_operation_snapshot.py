"""One-operation sync read reuse. Never an authorization or cross-attempt cache."""

import os
from typing import cast

from prometheus_client import Counter, REGISTRY


def _reads_avoided_counter() -> Counter:
    try:
        return Counter(
            'omi_sync_operation_snapshot_reads_avoided_total',
            'Redundant document reads avoided within one sync read operation',
            ['origin', 'operation'],
        )
    except ValueError:
        # Prometheus has no public lookup; follow the backend metric reload convention.
        return cast(
            Counter, getattr(REGISTRY, '_names_to_collectors')['omi_sync_operation_snapshot_reads_avoided_total']
        )


READS_AVOIDED = _reads_avoided_counter()


def enabled() -> bool:
    return os.getenv('SYNC_OPERATION_SNAPSHOT_ENABLED', 'true').strip().lower() not in {'false', '0', 'off', 'no'}


def avoided(operation: str) -> None:
    READS_AVOIDED.labels(origin='job:sync_operation_snapshot', operation=operation).inc()
