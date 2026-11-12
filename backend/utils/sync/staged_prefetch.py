"""Disposable, bounded byte cache. No job, content, or conversation ownership.

The consumer still downloads metadata to validate the bucket and generation.
Cancellation may leave a storage leaf alive, but it can only populate this
bounded cache; it never writes another job's local paths or shared state.
"""

from collections import OrderedDict
from dataclasses import dataclass
import threading
import time

from config.sync_owner_concurrency import preparation_width

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_OWNER_BYTES = 8 * 1024 * 1024
MAX_CACHE_BYTES = 32 * 1024 * 1024
MAX_CACHE_ENTRIES = 128
CACHE_SECONDS = 120
MAX_PREPARERS = 2  # One owner can occupy only one, leaving room for a second.


@dataclass(frozen=True)
class StagedBytes:
    data: bytes
    bucket: str
    generation: int


class StagedPrefetch:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries: OrderedDict[str, tuple[str, float, StagedBytes]] = OrderedDict()
        self._owners: dict[str, object] = {}

    def _expire(self):
        now = time.monotonic()
        for path, (_, deadline, _) in list(self._entries.items()):
            if deadline <= now:
                del self._entries[path]

    def acquire(self, uid: str) -> object | None:
        with self._lock:
            if uid in self._owners or len(self._owners) >= MAX_PREPARERS:
                return None
            token = object()
            self._owners[uid] = token
            return token

    def release(self, uid: str, token: object):
        with self._lock:
            if self._owners.get(uid) is token:
                del self._owners[uid]

    def put(self, uid: str, token: object, path: str, value: StagedBytes) -> bool:
        with self._lock:
            self._expire()
            if self._owners.get(uid) is not token or len(value.data) > MAX_FILE_BYTES:
                return False
            if path in self._entries:
                return False
            total = sum(len(entry.data) for _, _, entry in self._entries.values())
            own = sum(len(entry.data) for owner, _, entry in self._entries.values() if owner == uid)
            if (
                len(self._entries) >= MAX_CACHE_ENTRIES
                or total + len(value.data) > MAX_CACHE_BYTES
                or own + len(value.data) > MAX_OWNER_BYTES
            ):
                return False
            self._entries[path] = (uid, time.monotonic() + CACHE_SECONDS, value)
            return True

    def take(self, path: str) -> StagedBytes | None:
        with self._lock:
            self._expire()
            entry = self._entries.pop(path, None)
            return entry[2] if entry and preparation_width() > 1 else None

    def contains(self, path: str) -> bool:
        with self._lock:
            self._expire()
            return path in self._entries


staged_prefetch = StagedPrefetch()
