"""Bounded memo for verified GCS reads within one authorized operation."""

from operator import itemgetter
import threading

from cachetools import LRUCache
from prometheus_client import Counter

CALLS_AVOIDED = Counter(
    'omi_gcs_read_calls_avoided_total',
    'GCS calls skipped by verified read reuse, before replacement calls',
    ('change', 'method'),
)
PAYLOAD_BYTES_AVOIDED = Counter(
    'omi_gcs_read_payload_bytes_avoided_total',
    'Previously measured GCS object payload bytes skipped by read reuse',
    ('change',),
)
REPLACEMENT_CALLS = Counter(
    'omi_gcs_read_replacement_calls_total',
    'Additional GCS calls for verifying known keys or recovering stale metadata',
    ('change', 'method'),
)


def avoided(change, method, *, payload_bytes=0):
    CALLS_AVOIDED.labels(change, method).inc()
    if payload_bytes:
        PAYLOAD_BYTES_AVOIDED.labels(change).inc(payload_bytes)


class ReadMemo:
    """The caller owns its lifetime. Only successful, immutable proofs enter."""

    def __init__(self, max_bytes=16 * 1024 * 1024):
        self._cache = LRUCache(maxsize=max_bytes, getsizeof=itemgetter(1))
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            entry = self._cache.get(key)
        return entry[0] if entry is not None else None

    def put(self, key, value, retained_bytes):
        # Even entries with no payload consume memory for their key and bookkeeping.
        weight = retained_bytes + 512
        if weight <= self._cache.maxsize:
            with self._lock:
                self._cache[key] = (value, weight)
