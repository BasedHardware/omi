"""Low-cardinality metrics for Firestore read-through caches.

This module intentionally lives under ``database/`` so database modules can
record metrics without importing upward from ``utils``. ``prometheus_client``
uses a global registry, so these metrics are exported automatically by the
existing /metrics endpoint.
"""

from prometheus_client import Counter, Histogram

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
    FIRESTORE_CACHE_REQUESTS.labels(namespace=namespace, result=result).inc()


def observe_fetch(namespace: str, seconds: float) -> None:
    FIRESTORE_CACHE_FETCH_SECONDS.labels(namespace=namespace).observe(seconds)


def observe_payload(namespace: str, payload_bytes: int) -> None:
    FIRESTORE_CACHE_PAYLOAD_BYTES.labels(namespace=namespace).observe(payload_bytes)
