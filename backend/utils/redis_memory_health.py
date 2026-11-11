"""Read-only prod Redis used_memory probe for Cloud Monitoring.

Redis Cloud Essentials omits ``maxmemory`` from INFO. Compare against the
known 12 GiB SKU ceiling. Fail-open: never fail notifications-job.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Redis Cloud Single-Zone_Persistence_12GB. INFO has no maxmemory field.
REDIS_CLOUD_MAXMEMORY_BYTES = 12 * 1024**3
THRESHOLD_RATIO = 0.90
HEALTH_LOG_MARKER = 'redis_memory_threshold'


def used_memory_ratio(used: int, cap: int = REDIS_CLOUD_MAXMEMORY_BYTES) -> float:
    if cap <= 0:
        raise ValueError('cap must be positive')
    return used / cap


def run_scheduled_check(*, redis_client: Any = None) -> None:
    try:
        client = redis_client
        if client is None:
            from database.redis_db import r as client
        info = client.info('memory')
        used = int(info['used_memory'])
        ratio = used_memory_ratio(used)
        if ratio < THRESHOLD_RATIO:
            return
        logger.warning(
            '%s threshold=90 used=%s cap=%s ratio=%.4f',
            HEALTH_LOG_MARKER,
            used,
            REDIS_CLOUD_MAXMEMORY_BYTES,
            ratio,
        )
    except Exception:
        logger.exception('redis_memory_health failed')
