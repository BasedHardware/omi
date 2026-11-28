"""Low-cardinality metrics for Firestore read-through caches.

This module intentionally lives under database/ so database modules can
record metrics without importing upward from utils. prometheus_client
uses a global registry, so these metrics are exported automatically by the
existing /metrics endpoint.
"""

import logging
import math

from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

FIRESTORE_CACHE_REQUESTS = Counter(
    'firestore_cache_requests_total',
    'Firestore cache requests by namespace and result',
    ['namespace', 'result'],
)

FIRESTORE_CACHE_FETCH_SECONDS = Histogram(
    'firestore_cache_fetch_seconds',
    'Time spent fetching Firestore cache misses from the source of truth',
    ['namespace'],
)

FIRESTORE_CACHE_PAYLOAD_BYTES = Histogram(
    'firestore_cache_payload_bytes',
    'Serialized Firestore cache payload size in bytes',
    ['namespace'],
    buckets=(128, 512, 1024, 4096, 16384, 65536, 262144, 1048576),
)


def record_request(namespace: str, result: str) -> None:
    """Record one cache lookup or update event.

    Must never raise: a metrics failure must not break the cache path it is
    observing, so any error is logged at warning and swallowed.
    """
    try:
        ns = str(namespace) if namespace is not None else 'unknown'
        res = str(result) if result is not None else 'unknown'
        FIRESTORE_CACHE_REQUESTS.labels(namespace=ns, result=res).inc()
    except Exception:
        logger.warning('record_request failed namespace=%s result=%s', namespace, result, exc_info=True)


def observe_fetch(namespace: str, seconds: float) -> None:
    """Observe duration of source-of-truth fetch.

    Must never raise: invalid durations or client errors are safely handled.
    """
    try:
        ns = str(namespace) if namespace is not None else 'unknown'
        sec = float(seconds)
        if math.isnan(sec) or math.isinf(sec) or sec < 0:
            return
        FIRESTORE_CACHE_FETCH_SECONDS.labels(namespace=ns).observe(sec)
    except Exception:
        logger.warning('observe_fetch failed namespace=%s seconds=%s', namespace, seconds, exc_info=True)


def observe_payload(namespace: str, payload_bytes: int) -> None:
    """Observe payload size in bytes.

    Must never raise: negative sizes or client errors are safely handled.
    """
    try:
        ns = str(namespace) if namespace is not None else 'unknown'
        p_bytes = int(payload_bytes)
        if p_bytes < 0:
            return
        FIRESTORE_CACHE_PAYLOAD_BYTES.labels(namespace=ns).observe(p_bytes)
    except Exception:
        logger.warning('observe_payload failed namespace=%s payload_bytes=%s', namespace, payload_bytes, exc_info=True)
