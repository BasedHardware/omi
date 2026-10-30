"""Bounded process-local clip cache, shared by sync and async extraction paths.

No audio is retained. Endpoint + model id isolates embedding spaces. Entries are
copies so centroid callers cannot mutate another pass's embedding. Failures and
invalid vectors never enter the bank; TTL also bounds model redeploy staleness.
"""

from collections import OrderedDict
import hashlib
from threading import Lock
import time

import numpy as np

MODEL_ID = 'wespeaker-resnet34:v2'
MAX_ENTRIES = 2048
TTL_SECONDS = 1800
_entries: OrderedDict[str, tuple[float, np.ndarray]] = OrderedDict()
_lock = Lock()


def key(audio: bytes, model_id: str) -> str:
    digest = hashlib.sha256(model_id.encode())
    digest.update(b'\0')
    digest.update(audio)
    return digest.hexdigest()


def get(cache_key: str) -> np.ndarray | None:
    now = time.monotonic()
    with _lock:
        # Expiry order is insertion order (hits do not extend retention).
        while _entries and next(iter(_entries.values()))[0] <= now:
            _entries.popitem(last=False)
        item = _entries.get(cache_key)
        return item[1].copy() if item is not None else None


def put(cache_key: str, embedding: np.ndarray) -> None:
    vector = np.asarray(embedding)
    if not 0 < vector.size <= 4096 or not np.isfinite(vector).all() or not np.any(vector):
        return
    with _lock:
        _entries.pop(cache_key, None)
        _entries[cache_key] = (time.monotonic() + TTL_SECONDS, vector.copy())
        while len(_entries) > MAX_ENTRIES:
            _entries.popitem(last=False)
