"""Non-waiting, process-local admission for queued/running custody PCM only."""

from dataclasses import dataclass
import os
import threading

# ceil(20 MiB * 4/3): an enabled live lane must admit even the largest
# protocol-valid socket window when otherwise idle. A contract test pins this
# to BUFFERED_AUDIO_MAX_BYTES without importing the metrics-heavy protocol here.
MIN_STORAGE_PCM_BUDGET_MB = 27


def storage_pcm_budget_bytes() -> int:
    # Deployment validation rejects malformed values. Keep the runtime kill
    # switch safe for older/unvalidated environments too.
    try:
        value = int(os.getenv('PUSHER_STORAGE_PCM_BUDGET_MB', '0'))
        return value * 1024 * 1024 if value >= MIN_STORAGE_PCM_BUDGET_MB else 0
    except ValueError:
        return 0


class StoragePcmBudget:
    def __init__(self, limit: int):
        self.limit = limit
        self.live_limit = limit - limit // 4
        self.used = 0
        self._lock = threading.RLock()

    def admit(self, size: int, *, tail: bool = False) -> bool:
        """Roll back a failed acquire, including an error after mutation."""
        with self._lock:
            before = self.used
            try:
                return self.acquire(size, tail=tail)
            except Exception:
                self.used = before
                raise

    def settle(self, size: int) -> None:
        """Retire exactly this reservation even if release raises."""
        with self._lock:
            before = self.used
            try:
                self.release(size)
            finally:
                self.used = max(0, before - size)

    def acquire(self, size: int, *, tail: bool = False) -> bool:
        if self.limit == 0:
            return True
        with self._lock:
            if self.used + size > (self.limit if tail else self.live_limit):
                return False
            self.used += size
            return True

    def release(self, size: int) -> None:
        if self.limit:
            with self._lock:
                self.used -= size


@dataclass
class RetainedPcmWindow:
    """Original socket buffers, moved without copying at a refused boundary.

    They remain charged to that socket's existing 20 MiB ByteBudget. Owner,
    timestamps and exact frame checkpoints cannot follow a conversation switch.
    """

    payload: bytearray
    frames: list[dict]
    conversation_id: str | None
    start: float | None
