"""Low-cardinality metrics for Firestore read-through caches.

This module intentionally lives under ``database/`` so database modules can
record metrics without importing upward from ``utils``. ``prometheus_client``
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

VALID_RESULTS = frozenset({
    'disabled',
    'hit',
    'miss',
    'stale',
    'set',
    'set_error',
    'invalidate',
    'invalidate_error',
    'redis_error',
    'decode_error',
    'payload_too_large',
})


def _sanitize_namespace(namespace: str) -> str:
    if not isinstance(namespace, str) or not namespace.strip():
        raise ValueError("namespace must be a non-empty string")
    return namespace.strip().lower()


def record_request(namespace: str, result: str) -> None:
    try:
        ns = _sanitize_namespace(namespace)
        if not isinstance(result, str) or not result.strip():
            raise ValueError("result must be a non-empty string")
        res = result.strip().lower()
        if res not in VALID_RESULTS:
            # Fall back to 'unknown' to prevent unconstrained high-cardinality label explosion
            res = 'unknown'
        FIRESTORE_CACHE_REQUESTS.labels(namespace=ns, result=res).inc()
    except (ValueError, TypeError) as exc:
        logger.debug("Invalid metric label for record_request: %s", exc)


def observe_fetch(namespace: str, seconds: float) -> None:
    try:
        ns = _sanitize_namespace(namespace)
        if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
            raise ValueError("seconds must be a number")
        sec = float(seconds)
        if math.isnan(sec) or math.isinf(sec) or sec < 0.0:
            raise ValueError("seconds must be a non-negative finite number")
        FIRESTORE_CACHE_FETCH_SECONDS.labels(namespace=ns).observe(sec)
    except (ValueError, TypeError) as exc:
        logger.debug("Invalid observation in observe_fetch: %s", exc)


def observe_payload(namespace: str, payload_bytes: int) -> None:
    try:
        ns = _sanitize_namespace(namespace)
        if not isinstance(payload_bytes, int) or isinstance(payload_bytes, bool) or payload_bytes < 0:
            raise ValueError("payload_bytes must be a non-negative integer")
        FIRESTORE_CACHE_PAYLOAD_BYTES.labels(namespace=ns).observe(payload_bytes)
    except (ValueError, TypeError) as exc:
        logger.debug("Invalid observation in observe_payload: %s", exc)
